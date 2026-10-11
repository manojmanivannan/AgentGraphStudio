"""Spec-level guard: zero new execution event types (mcp-client-support).

Spec §4.1/§4.5/§4.6 pin the event vocabulary — MCP tooling (#138/#139/#140)
must ride the existing ``tool_start`` / ``tool_result`` / ``warning`` / other
documented shapes, never invent new ones. This test scans the backend source
for every emitted wire event (``_event("<type>", ...)`` calls and
``{"type": "<type>", ...} payload dicts``) and asserts each is in the
documented protocol set (docs/ARCHITECTURE.md "Execution Events" wire
protocol) or is the documentation's ``new_type`` placeholder.
"""

import re
from pathlib import Path

# Documented wire-protocol event types (docs/ARCHITECTURE.md) plus the durable
# conversation-message event_type values that ride the same vocabulary.
DOCUMENTED_EVENT_TYPES = {
    "run_start",
    "agent_start",
    "thought",
    "tool_start",
    "tool_result",
    "tool_approval_request",
    "human_input_request",
    "handoff",
    "final_answer",
    "run_complete",
    "run_queued",
    "run_aborted",
    "error",
    "warning",
    "attachment_consumed",
    "attachment_produced",
    "conversation_renamed",
}

_SRC = Path(__file__).resolve().parents[1] / "src" / "canvas_server"

_EVENT_CALL = re.compile(r"_event\(\s*['\"]([a-z_]+)['\"]")
_TYPE_KEY = re.compile(r"['\"]type['\"]\s*:\s*['\"]([a-z_]+)['\"]")


def _collected_types() -> set[str]:
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        found.update(_EVENT_CALL.findall(text))
        found.update(_TYPE_KEY.findall(text))
    return found


def test_no_undocumented_execution_event_types_are_emitted():
    found = _collected_types()
    found.discard("new_type")  # the protocol doc's own placeholder
    undeclared = found - DOCUMENTED_EVENT_TYPES
    assert not undeclared, (
        "Undocumented execution event types found in src/canvas_server "
        f"(spec: zero new event types): {sorted(undeclared)}"
    )


def test_mcp_flag_notes_ride_warning_not_new_types():
    """#139's staleness/degradation/collision surfacing must use 'warning'."""
    from canvas_server.runner.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._record_flag("stale_tools", None, "demo message")
    registry._record_flag("degraded_server", None, "demo message")
    registry._record_flag("collision", None, "demo message")

    for flag in registry.drain_flags():
        assert set(flag) <= {"kind", "node_id", "message"}  # payload-only note
        # kind is metadata for tests, not a wire event type — the runner
        # emits {"type": "warning", ...}, asserted by the runner suites.