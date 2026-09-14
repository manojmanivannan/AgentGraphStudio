"""PROTOTYPE — throwaway logic for issue #81 (Runtime representation &
consumption of attachment instances).

Part of the wayfinder map for file attachments (#75). Not production code —
see prototype_runtime_representation/tui.py for the interactive shell, and
the map/ticket for how this gets captured once the design is locked.

Question being prototyped
--------------------------
How does a stored AttachmentInstance (data model per #76, storage per #79)
get consumed at runtime by a downstream agent that declares it as an input —
how is its content represented to the LLM, and does the same mechanism cover
materializing it as a file inside the Docker sandbox for coding-enabled
agents? And symmetrically: when a coding-enabled agent computes a large file
inside the sandbox, how does that become a stored *output* attachment instance
without the LM having to re-type the whole payload through #78's
`output_attachments` OutputField?

Three candidate policies are modeled side by side, each answering all four
axes from the ticket consistently, so reacting to one gives a full answer:

  ALWAYS_INLINE     Every input attachment is unconditionally injected as text
                     (readable types, truncated) or a multimodal image block
                     (image type) directly into the prompt. Binary/pdf gets a
                     text placeholder only. *Any* coding-enabled agent also
                     gets the raw bytes written into the sandbox before the
                     ReAct loop starts, for every declared input attachment,
                     regardless of type or size — belt and suspenders. On the
                     output side, an `output_attachments` entry whose
                     `content` looks like a `sandbox://<path>` reference is
                     read out of the sandbox session and stored as bytes,
                     rather than requiring the LM to paste the payload —
                     generalizing the existing `/api/plots/{id}`-shaped
                     special case from #78.

  TOOL_MEDIATED      Nothing is inlined except a one-line manifest (name,
                     type, size) per declared input attachment. Content is
                     only available if the agent calls `read_attachment(name)`
                     — which returns text for readable types, a multimodal
                     image block for images, or a materialized sandbox path
                     for anything a coding-enabled agent wants to open with
                     pandas/PIL/etc. Sandbox materialization is lazy: it only
                     happens inside that tool call, not before the loop
                     starts. Output capture is symmetric: a coding-enabled
                     agent calls a tool-call-time `emit_attachment_from_file`
                     (mirrors today's `generate_plot`) instead of using #78's
                     OutputField for sandbox-sourced files — the OutputField
                     stays reserved for small, LM-authored content.

  SIZE_AWARE_HYBRID  Type- and size-dependent inlining: small readable text
                     (under a threshold) is inlined in full; large readable
                     text gets a truncated preview + manifest; image is
                     always a multimodal block (small or large); binary/pdf
                     is manifest-only. Sandbox materialization is eager and
                     unconditional for coding-enabled agents (same as
                     ALWAYS_INLINE), decoupled from what got inlined for the
                     LLM. Output capture supports *both* literal content
                     (small, LM-authored) and a `sandbox://<path>` reference
                     in the same `output_attachments` field, distinguished by
                     a prefix check — same generalization as ALWAYS_INLINE,
                     combined with size-aware inlining on the input side.

  PATH_REFERENCE     (added mid-reaction session, from live feedback) Content
                     is never expanded into the prompt at all for a
                     coding-enabled agent — the LLM only ever sees the
                     materialized sandbox path as a short string, regardless
                     of type or size (even binary/pdf/image). There's no
                     dedicated `read_attachment` tool: *any* of the agent's
                     own already-wired custom Python tool nodes can accept
                     that path as a plain string argument and do whatever it
                     wants with the file (`pd.read_csv(path)`, extract text
                     from a pdf, load an image with PIL, etc.) — the
                     attachment mechanism doesn't need to know what "reading"
                     means for a given type, because tool authorship already
                     owns that. Sandbox materialization is eager and
                     unconditional (same timing as ALWAYS_INLINE), since the
                     path is worthless without the file behind it. For a
                     chat-only agent with no sandbox, a path is meaningless,
                     so this policy falls back per type: image → multimodal
                     block, small readable text → inline, everything else →
                     opaque manifest note (same fallback as the other three
                     policies use for that case).

RESOLUTION (live reaction session, same day): PATH_REFERENCE was the winning
shape, refined by two follow-up answers:

  - `delivery_method` (`inline` | `file_path`) becomes a **new per-Attachment-
    node field** (canvas designer's preference, like `file_type` — extends
    #76's node fields the same way #80 added `description`), not a global
    automatic policy. The framework still auto-falls-back per consumer when
    the node's preference isn't actually usable for that agent (no sandbox →
    `file_path` degrades to the inline/multimodal/manifest ladder above;
    binary/pdf can never truly go `inline` regardless of preference).
  - `image` type is special-cased to always be **dual** for a coding-enabled
    consumer: both the multimodal image block AND the sandbox path are
    injected together, regardless of the node's `delivery_method` — path
    alone would lose vision reasoning, inline alone would lose tool access.

This module is pure: no I/O, no terminal control codes, importable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Threshold (chars) above which "readable" text content is not inlined in
# full — used by SIZE_AWARE_HYBRID; ALWAYS_INLINE and TOOL_MEDIATED ignore it
# (they inline unconditionally or not at all).
INLINE_CHAR_THRESHOLD = 500
PREVIEW_CHARS = 120

READABLE_TYPES = {"csv", "json", "text", "yaml", "python"}
UNREADABLE_TYPES = {"binary", "pdf"}
SANDBOX_REF_PREFIX = "sandbox://"


class Policy(str, Enum):
    ALWAYS_INLINE = "always_inline"
    TOOL_MEDIATED = "tool_mediated"
    SIZE_AWARE_HYBRID = "size_aware_hybrid"
    PATH_REFERENCE = "path_reference"


class LLMContentKind(str, Enum):
    TEXT_INLINE = "text_inline"          # full/truncated text in the prompt
    TEXT_PREVIEW = "text_preview"         # short preview + "more via tool" note
    IMAGE_BLOCK = "image_block"           # multimodal image content block
    MANIFEST_ONLY = "manifest_only"       # name/type/size line, no content
    TOOL_RESULT = "tool_result"           # returned only from a tool call
    PATH_STRING = "path_string"           # bare sandbox path, no content at all


@dataclass(frozen=True)
class InputAttachment:
    """A stored AttachmentInstance declared as input to a consuming agent."""

    name: str
    file_type: str
    content_text: str  # empty string for binary/pdf/image in this prototype
    size_bytes: int


@dataclass(frozen=True)
class ConsumingAgent:
    name: str
    coding_enabled: bool  # has run_code / generate_plot-style sandbox tools


@dataclass
class InputRepresentationPlan:
    llm_content_kind: LLMContentKind
    llm_content_preview: str
    sandbox_write: bool
    sandbox_path: str | None
    sandbox_timing: str  # "before ReAct loop starts" | "lazy, on tool call" | "n/a"
    notes: list[str]


def plan_input_representation(
    policy: Policy, attachment: InputAttachment, agent: ConsumingAgent
) -> InputRepresentationPlan:
    is_image = attachment.file_type == "image"
    is_unreadable = attachment.file_type in UNREADABLE_TYPES
    sandbox_path = f"/workspace/attachments/{attachment.name}" if agent.coding_enabled else None
    notes: list[str] = []

    if policy is Policy.ALWAYS_INLINE:
        if is_image:
            kind = LLMContentKind.IMAGE_BLOCK
            preview = "<multimodal image content block>"
        elif is_unreadable:
            kind = LLMContentKind.MANIFEST_ONLY
            preview = f"[{attachment.file_type} attachment, {attachment.size_bytes}B — not inlinable as text]"
        else:
            kind = LLMContentKind.TEXT_INLINE
            preview = attachment.content_text
        sandbox_write = agent.coding_enabled  # unconditional, any type/size
        timing = "before ReAct loop starts" if sandbox_write else "n/a (agent has no sandbox)"
        if sandbox_write and kind == LLMContentKind.TEXT_INLINE:
            notes.append(
                "Content is both inlined in full AND written to the sandbox — "
                "the LM never needs to re-type it into code, but tokens are spent twice."
            )
        if sandbox_write and is_unreadable:
            notes.append(
                "Binary/pdf can't be inlined as text but still lands on disk for code to open "
                "(e.g. PyPDF2, a video codec) — sandbox materialization is the only way this "
                "type becomes usable at all."
            )

    elif policy is Policy.TOOL_MEDIATED:
        kind = LLMContentKind.MANIFEST_ONLY
        preview = f"{attachment.name} ({attachment.file_type}, {attachment.size_bytes}B) — call read_attachment to view"
        sandbox_write = False  # nothing written until the tool is actually called
        timing = "lazy, on tool call" if agent.coding_enabled else "n/a (agent has no sandbox)"
        notes.append(
            "Manifest costs a fixed few tokens regardless of attachment size or count — "
            "cheapest prompt, but every consumption costs an extra ReAct iteration."
        )
        if not agent.coding_enabled and is_unreadable:
            notes.append(
                "Agent has no sandbox and the type is unreadable as text: read_attachment can "
                "only return a manifest note, never real content — this attachment is effectively "
                "opaque to a non-coding agent under any policy, not just this one."
            )

    elif policy is Policy.SIZE_AWARE_HYBRID:
        if is_image:
            kind = LLMContentKind.IMAGE_BLOCK
            preview = "<multimodal image content block>"
        elif is_unreadable:
            kind = LLMContentKind.MANIFEST_ONLY
            preview = f"[{attachment.file_type} attachment, {attachment.size_bytes}B — not inlinable as text]"
        elif len(attachment.content_text) <= INLINE_CHAR_THRESHOLD:
            kind = LLMContentKind.TEXT_INLINE
            preview = attachment.content_text
        else:
            kind = LLMContentKind.TEXT_PREVIEW
            preview = attachment.content_text[:PREVIEW_CHARS] + "… [truncated — full content on disk / via read_attachment]"
        sandbox_write = agent.coding_enabled  # eager, decoupled from what got inlined
        timing = "before ReAct loop starts" if sandbox_write else "n/a (agent has no sandbox)"
        if kind == LLMContentKind.TEXT_PREVIEW and sandbox_write:
            notes.append(
                "Prompt only carries a preview; the full payload is on disk for code to read — "
                "avoids ever re-typing large content through the LM, at the cost of a policy "
                "decision the other two mechanisms don't need (the threshold itself)."
            )

    elif policy is Policy.PATH_REFERENCE:
        if agent.coding_enabled:
            kind = LLMContentKind.PATH_STRING
            preview = f"Attachment {attachment.name!r} available at {sandbox_path}"
            sandbox_write = True  # unconditional — the path is worthless without the file
            timing = "before ReAct loop starts"
            notes.append(
                "No dedicated read_attachment tool needed — any of the agent's own wired "
                "custom Python tools that accept a path string can open this file however "
                "it likes (pd.read_csv, PDF text extraction, PIL, etc.). Cheapest possible "
                "prompt cost regardless of type or size, including binary/pdf/image."
            )
        elif is_image:
            kind = LLMContentKind.IMAGE_BLOCK
            preview = "<multimodal image content block>"
            sandbox_write = False
            timing = "n/a (agent has no sandbox)"
        elif is_unreadable:
            kind = LLMContentKind.MANIFEST_ONLY
            preview = f"[{attachment.file_type} attachment, {attachment.size_bytes}B — not inlinable as text]"
            sandbox_write = False
            timing = "n/a (agent has no sandbox)"
            notes.append(
                "No sandbox and no path is meaningful outside one — falls back to the same "
                "opaque-manifest case every other policy hits for a non-coding agent."
            )
        else:
            kind = LLMContentKind.TEXT_INLINE
            preview = attachment.content_text
            sandbox_write = False
            timing = "n/a (agent has no sandbox)"

    return InputRepresentationPlan(
        llm_content_kind=kind,
        llm_content_preview=preview,
        sandbox_write=sandbox_write,
        sandbox_path=sandbox_path if sandbox_write else None,
        sandbox_timing=timing,
        notes=notes,
    )


@dataclass(frozen=True)
class OutputAttachmentDraft:
    """A raw `output_attachments` entry as produced by #78's mechanism, before
    this ticket's decision about how `content` gets resolved into stored bytes.
    """

    name: str
    file_type: str
    content: str  # either literal content, or a sandbox:// reference


@dataclass
class OutputCaptureOutcome:
    resolved: bool
    stored_content_source: str  # "lm-authored literal" | "sandbox file read" | "rejected"
    notes: list[str]


def plan_output_capture(policy: Policy, draft: OutputAttachmentDraft) -> OutputCaptureOutcome:
    is_sandbox_ref = draft.content.startswith(SANDBOX_REF_PREFIX)

    if policy is Policy.TOOL_MEDIATED:
        # This policy never uses #78's OutputField for sandbox-sourced files —
        # it expects a dedicated per-iteration `emit_attachment_from_file` tool
        # call instead, so a sandbox:// reference arriving via output_attachments
        # is a modeling error under this policy.
        if is_sandbox_ref:
            return OutputCaptureOutcome(
                resolved=False,
                stored_content_source="rejected",
                notes=[
                    "TOOL_MEDIATED expects sandbox-sourced output to arrive via a mid-loop "
                    "emit_attachment_from_file tool call, not a sandbox:// reference in "
                    "output_attachments — this conflicts with #78's already-locked decision "
                    "that extraction is post-loop only, via the OutputField.",
                ],
            )
        return OutputCaptureOutcome(
            resolved=True,
            stored_content_source="lm-authored literal",
            notes=["Small, LM-authored content stored as-is — no sandbox involvement."],
        )

    # ALWAYS_INLINE and SIZE_AWARE_HYBRID both generalize the existing
    # /api/plots/{id}-shaped special case from #78 to any sandbox:// reference.
    if is_sandbox_ref:
        path = draft.content[len(SANDBOX_REF_PREFIX):]
        return OutputCaptureOutcome(
            resolved=True,
            stored_content_source="sandbox file read",
            notes=[
                f"Framework reads {path!r} out of the sandbox session's filesystem and stores "
                "those bytes — the LM never re-types a large payload, matching how an "
                "/api/plots/{id} reference is already treated as 'already stored — link it.'",
            ],
        )
    return OutputCaptureOutcome(
        resolved=True,
        stored_content_source="lm-authored literal",
        notes=["No sandbox:// prefix — treated as small, LM-authored literal content."],
    )
