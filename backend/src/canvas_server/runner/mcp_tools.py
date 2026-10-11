"""MCP tool descriptor pipeline (ticket #138, spec §4.1–4.2, §4.5).

Turns one server ``tools/list`` entry into a DSPy-ready async callable that
carries ``__name__`` / ``__doc__`` / ``requires_approval`` / ``node_id``
exactly like a compiled author tool — so DSPy wrapping, the StreamingReAct
HITL approval seam, ``tool_start``/``tool_result`` enrichment, and
graceful-failure conversion are unchanged (no new execution path, no new
event types).

Descriptor build reuses DSPy's own MCP adapter (``dspy.utils.mcp``) so
server ``inputSchema`` types are preserved verbatim (no coarsening, no
host-side coercion). Callables invoke the per-run ``ClientSession`` from
``McpSessionRegistry`` (#137) directly and frame the result per spec §4.5:
text blocks joined, non-text blocks summarized as a placeholder note, a
50k-char cap with a truncation note, and ``isError`` results passed through
as ordinary observations (the call never raises for tool errors — which also
sidesteps DSPy 3.4.0's RuntimeError-on-isError quirk).
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

import mcp.types as mcp_types
from dspy.adapters.types.tool import Tool as DspyTool
from dspy.utils.mcp import convert_mcp_tool

from canvas_server.config import settings
from canvas_server.runner.mcp_sessions import is_stale_session_error

logger = logging.getLogger("canvas_server.runner.mcp_tools")

# Spec §4.5 / #122 §2: the 50k-char result cap is the only truncation.
MCP_RESULT_MAX_CHARS = 50_000

_TRUNCATION_NOTE = (
    f"[truncated: MCP tool result exceeded {MCP_RESULT_MAX_CHARS:,} characters]"
)

# First-occurrence-ordered counts of non-text content blocks, used for the
# placeholder note (spec §4.5: ``[1 image block returned, 3 text blocks]``).
_BLOCK_TYPE_LABELS: dict[type, str] = {
    mcp_types.ImageContent: "image",
    mcp_types.AudioContent: "audio",
}

_ILLEGAL_NAME_CHARS = re.compile(r"[^A-Za-z0-9_]")


def sanitize_tool_name(name: str) -> str:
    """Reduce a server tool name to a DSPy-legal identifier.

    MCP catalogs freely contain ``-``/``.``/spaces/unicode; DSPy tool names
    become function-call identifiers for the LLM. The sanitized name is what
    the model sees and calls; the session is always invoked with the
    original server name.
    """
    cleaned = _ILLEGAL_NAME_CHARS.sub("_", (name or "").strip())
    if not cleaned:
        return "mcp_tool"
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def _block_label(block: Any) -> str:
    for block_type, label in _BLOCK_TYPE_LABELS.items():
        if isinstance(block, block_type):
            return label
    return "resource"


def _block_summary(block: Any) -> dict[str, Any]:
    try:
        return block.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — raw structure is best-effort (#140 redacts)
        return {"type": type(block).__name__}


def format_mcp_result(result: Any) -> tuple[str, list[dict[str, Any]]]:
    """Frame a ``CallToolResult`` per spec §4.5.

    Returns ``(observation, raw_blocks)``:

    * text blocks joined with newlines (a single block stays a plain string);
    * each non-text block type summarized in one placeholder note appended to
      the observation — e.g. ``[1 image block returned, 3 text blocks]``;
    * ``isError`` results **never raise**: the server's error text is the
      observation (dspy 3.4.0 raises ``RuntimeError`` on ``isError`` — that
      quirk is deliberately not on this path);
    * the observation is capped at 50k chars with a truncation note —
      the only truncation (spec §5.2);
    * ``raw_blocks`` are JSON-safe dumps of every content block, persisted
      with the ``tool_result`` event payload for UI rendering.
    """
    text_parts: list[str] = []
    non_text_counts: dict[str, int] = {}
    raw_blocks: list[dict[str, Any]] = []

    for block in result.content or []:
        raw_blocks.append(_block_summary(block))
        if isinstance(block, mcp_types.TextContent):
            text_parts.append(block.text)
        else:
            label = _block_label(block)
            non_text_counts[label] = non_text_counts.get(label, 0) + 1

    observation = "\n".join(text_parts)
    if non_text_counts:
        segments = [
            f"{count} {label} block{'s' if count != 1 else ''} returned"
            for label, count in non_text_counts.items()
        ]
        if text_parts:
            segments.append(
                f"{len(text_parts)} text block{'s' if len(text_parts) != 1 else ''}"
            )
        note = "[" + ", ".join(segments) + "]"
        observation = f"{observation}\n{note}" if observation else note

    if len(observation) > MCP_RESULT_MAX_CHARS:
        observation = observation[:MCP_RESULT_MAX_CHARS] + "\n" + _TRUNCATION_NOTE

    return observation, raw_blocks


def _make_failed_stub(
    name: str,
    error: Exception,
    node_id: uuid.UUID,
) -> DspyTool:
    """A DSPy-ready stub that raises *error* at call time → observation.

    Same posture as ``ToolRegistry``'s failed-compile stub: the run continues
    and the agent can reason about (and report) the failure (#118/#132).
    """
    return make_unavailable_stub(name, error, node_id)


def make_unavailable_stub(
    name: str,
    error: BaseException,
    node_id: uuid.UUID,
) -> DspyTool:
    """A DSPy-ready stub for an MCP tool that cannot be served by the run.

    Raises *error* at call time → StreamingReAct converts it to the standard
    execution-error observation; the run continues degraded (#132, spec
    §4.6).
    """

    async def failed_tool(*args, **kwargs):
        """This MCP tool is unavailable for this run. Call this tool to see the failure details."""
        raise error

    failed_tool.__name__ = name
    failed_tool.requires_approval = False
    failed_tool.node_id = node_id
    return DspyTool(
        func=failed_tool, name=name, desc=failed_tool.__doc__,
        args={}, arg_types={}, arg_desc={},
    )


def build_mcp_tool(
    session: Any,
    server_tool: mcp_types.Tool,
    *,
    node_id: uuid.UUID,
    requires_approval: bool,
    session_registry: Any | None = None,
    server_id: uuid.UUID | None = None,
) -> DspyTool:
    """Build the per-run DSPy tool for one granted server tool.

    *session* is the run's ``mcp.ClientSession`` (from ``McpSessionRegistry``,
    #137). Descriptor build reuses ``dspy.utils.mcp.convert_mcp_tool`` so
    server ``inputSchema`` types are preserved verbatim (spec §4.2); a schema
    the adapter cannot process falls back to the failed-tool stub that raises
    at call time. The public tool name is sanitized; the session is always
    called with the server's original tool name.

    When *session_registry*/*server_id* are provided (#139, spec §4.6), a
    mid-run stale session (404 / "Session terminated") triggers exactly ONE
    re-handshake via the registry and a single retry; any other failure
    (transport, auth, tool error, timeout) never retries — it propagates to
    StreamingReAct's execution-error observation seam.

    The callable carries ``requires_approval`` / ``node_id`` (HITL seam,
    event enrichment) and ``last_raw_content_blocks`` (JSON-safe content
    structure persisted with each ``tool_result`` event payload).
    """
    node_id = uuid.UUID(str(node_id)) if not isinstance(node_id, uuid.UUID) else node_id
    display_name = sanitize_tool_name(server_tool.name)
    try:
        descriptor = convert_mcp_tool(session, server_tool)
    except Exception as e:  # noqa: BLE001 — bad schema → failed stub, never a failed run
        logger.warning(
            "MCP tool %r could not be converted to a DSPy descriptor: %s",
            server_tool.name,
            e,
        )
        return _make_failed_stub(display_name, e, node_id)

    args = dict(descriptor.args or {})
    arg_types = dict(descriptor.arg_types or {})
    arg_desc = dict(descriptor.arg_desc or {})
    original_name = server_tool.name
    description = server_tool.description or f"MCP tool {display_name}."
    # Cell (not a plain closure var): the session can be swapped for a fresh
    # one after a mid-run re-handshake (#139's stale-session retry).
    current = {"session": session}

    async def invoke_with_timeout(timeout: float, arguments: dict):
        """One bounded ``call_tool`` attempt against the current session.

        Spec §4.4: the timeout is re-read per call (tests override it via the
        settings seam). A hang surfaces as ``TimeoutError("timed out after
        <n>s")`` → StreamingReAct's standard execution-error observation; the
        session itself stays usable (the hung request is cancelled).
        """
        try:
            return await asyncio.wait_for(
                current["session"].call_tool(original_name, arguments=arguments),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise TimeoutError(f"timed out after {timeout:g}s") from exc

    async def mcp_tool_call(*_positional, **kwargs):
        """Invoke the run's MCP session; frame the result per spec §4.5."""
        try:
            result = await invoke_with_timeout(
                settings.mcp_tool_call_timeout_seconds, kwargs
            )
        except BaseException as call_error:  # noqa: BLE001 — re-raised below
            # Spec §4.6 retry-then-degrade: ONLY a dead server-side session
            # earns one re-handshake + one retry; everything else propagates
            # to the observation seam untouched.
            if (
                session_registry is None
                or server_id is None
                or not is_stale_session_error(call_error)
            ):
                raise
            logger.warning(
                "MCP tool %r hit a stale session (server %s) — re-handshaking "
                "once and retrying",
                original_name,
                server_id,
            )
            fresh = await session_registry.rehandshake(server_id)
            if fresh is None:
                raise call_error
            current["session"] = fresh
            result = await invoke_with_timeout(
                settings.mcp_tool_call_timeout_seconds, kwargs
            )
        observation, raw_blocks = format_mcp_result(result)
        mcp_tool_call.last_raw_content_blocks = raw_blocks
        return observation

    mcp_tool_call.__name__ = display_name
    mcp_tool_call.__doc__ = description
    mcp_tool_call.requires_approval = requires_approval
    mcp_tool_call.node_id = node_id
    mcp_tool_call.last_raw_content_blocks = None

    return DspyTool(
        func=mcp_tool_call,
        name=display_name,
        desc=description,
        args=args,
        arg_types=arg_types,
        arg_desc=arg_desc,
    )
