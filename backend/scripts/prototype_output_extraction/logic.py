"""PROTOTYPE — throwaway logic for issue #78 (Output-extraction mechanism / "final block").

Part of the wayfinder map for file attachments (#75). Not production code —
see prototype_output_extraction/tui.py for the interactive shell, and the
map/ticket for how this gets captured once the design is locked.

Question being prototyped
--------------------------
How does an agent signal that part of its output should be stripped out and
stored as an attachment instance (per the data model decided in #76), and how
does the framework extract + validate it?

Three candidate mechanisms are modeled side by side so they can be compared
against the *same* conceptual scenarios:

  TAGGED_BLOCK  Agent's final answer text contains an
                <attachment name="..." type="...">...</attachment> block.
                Framework parses/strips it post-hoc from `process_result`,
                after the ReAct loop's `extract` step finishes — i.e. once,
                on the whole final answer.

  OUTPUT_FIELD  A second structured DSPy OutputField (`output_attachments`)
                the LM fills in alongside `process_result`. No text parsing
                is needed; DSPy's own structured-output validation does the
                work of keeping it separate from the prose. Also resolved
                post-loop, at the `extract` step.

  TOOL_CALL     The agent invokes an `emit_attachment(name, file_type,
                content)` tool mid-reasoning — the same shape as today's
                `generate_plot`. The tool stores the content immediately,
                *inside* the ReAct loop (per-iteration, not post-loop), and
                returns a short reference token the agent must preserve
                verbatim in its final answer — mirroring the existing
                "preserve this markdown link" system-prompt rule used for
                plots today.

This module is pure: no I/O, no terminal control codes, importable on its own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum


class Mechanism(str, Enum):
    TAGGED_BLOCK = "tagged_block"
    OUTPUT_FIELD = "output_field"
    TOOL_CALL = "tool_call"


@dataclass(frozen=True)
class AttachmentSlot:
    """A declared *output* Attachment node wired to this agent (data model per #76)."""

    name: str
    file_type: str


@dataclass(frozen=True)
class AttachmentDraft:
    """An attachment instance extracted from raw agent output, not yet validated."""

    name: str
    file_type: str
    content: str
    origin: str  # "text-block" | "field" | "tool-call"


@dataclass
class ExtractionOutcome:
    remaining_answer: str
    drafts: list[AttachmentDraft] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    when: str = ""  # when extraction/validation happens relative to the ReAct loop


_TAG_RE = re.compile(
    r'<attachment\s+name="(?P<name>[^"]+)"\s+type="(?P<type>[^"]+)"\s*>'
    r"(?P<body>.*?)</attachment>",
    re.DOTALL,
)


def extract_tagged_block(final_answer: str) -> ExtractionOutcome:
    drafts = [
        AttachmentDraft(
            name=m.group("name"),
            file_type=m.group("type"),
            content=m.group("body").strip(),
            origin="text-block",
        )
        for m in _TAG_RE.finditer(final_answer)
    ]
    remaining = _TAG_RE.sub("", final_answer).strip()
    errors = []
    if "<attachment" in remaining:
        errors.append(
            "Unclosed/malformed <attachment> tag left in the text — fell through as plain prose."
        )
    return ExtractionOutcome(
        remaining_answer=remaining,
        drafts=drafts,
        errors=errors,
        when="post-loop: parsed out of process_result after extract()",
    )


def extract_output_field(
    process_result: str, output_attachments: list[dict] | None
) -> ExtractionOutcome:
    drafts = []
    errors = []
    for item in output_attachments or []:
        name, file_type, content = item.get("name"), item.get("file_type"), item.get("content")
        if not name or not file_type:
            errors.append(f"Malformed structured attachment entry (missing name/file_type): {item!r}")
            continue
        drafts.append(AttachmentDraft(name=name, file_type=file_type, content=content or "", origin="field"))
    return ExtractionOutcome(
        remaining_answer=process_result,
        drafts=drafts,
        errors=errors,
        when="post-loop: dedicated OutputField read directly after extract() — no text parsing",
    )


def extract_tool_call_ledger(final_answer: str, tool_calls: list[dict]) -> ExtractionOutcome:
    drafts = []
    errors = []
    for call in tool_calls:
        if call.get("tool") != "emit_attachment":
            continue
        args = call.get("args", {})
        name, file_type, content = args.get("name", ""), args.get("file_type", ""), args.get("content", "")
        ref = call.get("ref", f"[[attachment:{name}]]")
        drafts.append(AttachmentDraft(name=name, file_type=file_type, content=content, origin="tool-call"))
        if ref not in final_answer:
            errors.append(f"Agent did not preserve reference {ref!r} for {name!r} in its final answer.")
    return ExtractionOutcome(
        remaining_answer=final_answer,
        drafts=drafts,
        errors=errors,
        when="per-iteration: stored at tool-call time inside the ReAct loop (like generate_plot today)",
    )


def validate_against_slots(outcome: ExtractionOutcome, slots: list[AttachmentSlot]) -> ExtractionOutcome:
    """Runtime type-check against the agent's configured output Attachment node(s) (#76)."""
    slot_by_name = {s.name: s for s in slots}
    errors = list(outcome.errors)
    for draft in outcome.drafts:
        slot = slot_by_name.get(draft.name)
        if slot is None:
            errors.append(f"{draft.name!r} does not match any declared output Attachment node on this agent.")
            continue
        if slot.file_type != draft.file_type:
            errors.append(
                f"{draft.name!r} is wired as {slot.file_type!r} on the canvas but the agent emitted "
                f"{draft.file_type!r}."
            )
            continue
        if slot.file_type == "json":
            try:
                json.loads(draft.content)
            except Exception:
                errors.append(f"{draft.name!r} declared json but content is not valid JSON.")
    return ExtractionOutcome(
        remaining_answer=outcome.remaining_answer,
        drafts=outcome.drafts,
        errors=errors,
        when=outcome.when,
    )


def run(mechanism: Mechanism, scenario: dict, slots: list[AttachmentSlot]) -> ExtractionOutcome:
    """Dispatch to the right extractor for `mechanism`, then validate against `slots`."""
    if mechanism is Mechanism.TAGGED_BLOCK:
        outcome = extract_tagged_block(scenario["tagged_block_final_answer"])
    elif mechanism is Mechanism.OUTPUT_FIELD:
        outcome = extract_output_field(
            scenario["output_field_final_answer"], scenario.get("output_field_attachments")
        )
    else:
        outcome = extract_tool_call_ledger(
            scenario["tool_call_final_answer"], scenario.get("tool_calls", [])
        )
    return validate_against_slots(outcome, slots)


def raw_view(mechanism: Mechanism, scenario: dict) -> str:
    """Renders the mechanism-specific raw material fed into `run()`, for display."""
    if mechanism is Mechanism.TAGGED_BLOCK:
        return f"process_result (raw) =\n{scenario['tagged_block_final_answer']!r}"
    if mechanism is Mechanism.OUTPUT_FIELD:
        return (
            f"process_result =\n{scenario['output_field_final_answer']!r}\n\n"
            f"output_attachments (structured field) =\n"
            f"{json.dumps(scenario.get('output_field_attachments'), indent=2)}"
        )
    return (
        f"process_result =\n{scenario['tool_call_final_answer']!r}\n\n"
        f"tool_calls (ReAct trajectory) =\n"
        f"{json.dumps(scenario.get('tool_calls', []), indent=2)}"
    )
