"""Approval enforcement + redaction at the HITL seam (ticket #140, spec §5.3/§5.4).

* §5.3: an MCP tool with ``requires_approval=True`` MUST NOT silently execute
  when no client-response callback is wired (runs without a UI). The seam
  blocks at call time with an observation naming the tool — silent execution
  becomes impossible while the grant stays visible. Author tools keep their
  pre-#140 no-callback behavior (legacy silent-approve posture, unchanged).
* §5.4: the tool-error observation fed to the ``tool_result`` event and to
  MLflow autolog trajectories passes the MCP redaction pass — configured
  credential values and endpoint URLs are absent from event text.

Zero new event types: everything rides ``thought``/``tool_start``/
``tool_result``/``tool_approval_request``.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import mcp.types as mcp_types
from dspy.adapters.types.tool import Tool as DspyTool
from dspy.utils.mcp import convert_mcp_tool

from canvas_server.streaming_react import StreamingReAct
from tests.test_mcp_redaction import ServerCache, make_server

# Event types that existed before the MCP epic (frontend
# ExecutionEvent union, pre-#116): the §5 paths may not introduce new ones.
PRE_EXISTING_EVENT_TYPES = {
    "run_start",
    "agent_start",
    "thought",
    "tool_start",
    "tool_result",
    "handoff",
    "final_answer",
    "run_complete",
    "run_aborted",
    "error",
    "warning",
    "human_input_request",
    "tool_approval_request",
    "attachment_produced",
    "attachment_consumed",
    "human_input_response",
    "tool_approval_response",
    "interrupt_response",
    "conversation_renamed",
    "run_queued",
}


def make_prediction(tool_name="finish", thought="", args=None):
    pred = MagicMock()
    pred.next_thought = thought
    pred.next_tool_name = tool_name
    pred.next_tool_args = args or {}
    return pred


async def drive(agent, predictions, **input_args):
    with patch.object(
        agent, "_async_call_with_potential_trajectory_truncation"
    ) as mock_call:
        mock_call.side_effect = predictions
        return await agent.aforward(**input_args)


def make_result(*texts):
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=t) for t in texts]
    )


class RecordingSession:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments))
        return self.result


class ExplodingSession:
    """A transport/SDK-style failure that echoes config values (#140 §5.4)."""

    def __init__(self, error):
        self.error = error

    async def call_tool(self, name, arguments=None):
        raise self.error


def mcp_tool(session, name="add", requires_approval=True):
    """A real MCP descriptor carrying the metadata the HITL seam reads."""
    descriptor = convert_mcp_tool(
        session,
        mcp_types.Tool(
            name=name,
            description="Add two integers.",
            inputSchema={
                "type": "object",
                "properties": {"a": {"type": "integer"}},
                "required": ["a"],
            },
        ),
    )
    original = descriptor.func
    original.__name__ = name
    original.requires_approval = requires_approval
    original.mcp_origin = True
    original.node_id = uuid.uuid4()
    return DspyTool(
        func=original, name=name, desc="Add two integers.",
        args=descriptor.args, arg_types=descriptor.arg_types,
        arg_desc=descriptor.arg_desc,
    )


def author_tool(name="summarize", requires_approval=True):
    async def fn(*_a, **_k):
        """Author tool."""
        return "manual result"

    fn.__name__ = name
    fn.requires_approval = requires_approval
    return DspyTool(
        func=fn, name=name, desc="Author tool.", args={},
        arg_types={}, arg_desc={},
    )


class TestApprovalEnforcementGuarantee:
    async def test_requiring_mcp_tool_without_wired_callback_is_blocked(self):
        session = RecordingSession(make_result("3"))
        tool = mcp_tool(session, name="add", requires_approval=True)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        result = await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="call"),
                make_prediction("finish", thought="done"),
                {"process_result": "Blocked."},
            ],
        )

        # Silent execution is impossible: the session is never called.
        assert session.calls == []
        observation = result.trajectory["observation_0"]
        assert "add" in observation  # names the tool
        assert "approval" in observation.lower()
        assert "not executed" in observation.lower()

    async def test_blocked_call_emits_only_pre_existing_event_types(self):
        session = RecordingSession(make_result("3"))
        tool = mcp_tool(session, name="add", requires_approval=True)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="call"),
                make_prediction("finish", thought="done"),
                {"process_result": "Blocked."},
            ],
        )

        types = {e["type"] for e in events}
        # Zero new event types (spec §4.1): the §5.3 path rides the existing
        # tool_result machinery.
        assert types <= PRE_EXISTING_EVENT_TYPES
        tool_result = [e for e in events if e["type"] == "tool_result"][0]
        assert tool_result["tool"] == "add"
        assert "approval" in tool_result["output"].lower()

    async def test_wired_callback_still_governs_the_approval_path(self):
        # With a callback wired, the existing pause→approve flow is unchanged.
        session = RecordingSession(make_result("3"))
        tool = mcp_tool(session, name="add", requires_approval=True)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="call"),
                make_prediction("finish", thought="done"),
                {"process_result": "Approved."},
            ],
            get_client_response=AsyncMock(return_value={"approved": True}),
        )

        assert session.calls == [("add", {"a": 1})]
        assert any(e["type"] == "tool_approval_request" for e in events)
        tool_result = [e for e in events if e["type"] == "tool_result"][0]
        assert "3" in tool_result["output"]

    async def test_wired_callback_deny_still_denies(self):
        session = RecordingSession(make_result("3"))
        tool = mcp_tool(session, name="add", requires_approval=True)
        agent = StreamingReAct(MagicMock(), tools=[tool])

        result = await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="call"),
                make_prediction("finish", thought="done"),
                {"process_result": "Denied."},
            ],
            get_client_response=AsyncMock(return_value={"approved": False}),
        )

        assert session.calls == []
        assert result.trajectory["observation_0"] == "Tool execution denied by user."

    async def test_author_tool_keeps_pre_140_no_callback_behavior(self):
        # The legacy in-canvas no-callback posture is deliberately preserved
        # (approved default); only MCP-origin tools get the call-time block.
        tool = author_tool(name="summarize", requires_approval=True)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        result = await drive(
            agent,
            [
                make_prediction("summarize", args={}, thought="go"),
                make_prediction("finish", thought="done"),
                {"process_result": "Done."},
            ],
        )

        assert result.trajectory["observation_0"] == "manual result"
        tool_result = [e for e in events if e["type"] == "tool_result"][0]
        assert tool_result["output"] == "manual result"


class TestRedactionOnToolFailure:
    async def test_failure_echoing_credential_and_url_is_redacted(self):
        server = make_server(
            url="https://mcp.corp.internal/sse",
            credential_value="sk-corp-secret-123",
        )
        error = ConnectionError(
            "ConnectError: auth failed for https://mcp.corp.internal/sse"
            " with key sk-corp-secret-123"
        )
        tool = mcp_tool(ExplodingSession(error), name="add", requires_approval=False)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(server),
        ):
            result = await drive(
                agent,
                [
                    make_prediction("add", args={"a": 1}, thought="try"),
                    make_prediction("finish", thought="done"),
                    {"process_result": "Reported the failure."},
                ],
            )

        observation = result.trajectory["observation_0"]
        assert "Execution error in add" in observation
        # MLflow-facing trajectory text and the emitted event carry neither
        # the configured endpoint URL nor the credential value.
        assert "https://mcp.corp.internal/sse" not in observation
        assert "sk-corp-secret-123" not in observation
        assert "[REDACTED]" in observation
        tool_result = [e for e in events if e["type"] == "tool_result"][0]
        assert "sk-corp-secret-123" not in str(tool_result["output"])
        assert "https://mcp.corp.internal/sse" not in str(tool_result["output"])

    async def test_failure_redaction_reads_configured_servers(self):
        # The pass keys off the mcp_config cache — no servers configured →
        # no redaction markers (behavior guard for accidental masking).
        error = ConnectionError("connect to https://other.host failed")
        tool = mcp_tool(ExplodingSession(error), name="add", requires_approval=False)
        agent = StreamingReAct(MagicMock(), tools=[tool])

        result = await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="try"),
                make_prediction("finish", thought="done"),
                {"process_result": "Reported the failure."},
            ],
        )

        assert "https://other.host" in result.trajectory["observation_0"]


class TestSpecZeroNewEventTypes:
    """Spec-level assertion (#140): none of the §5 paths introduce new event
    types — the untrusted-framed observation, the denied approval, the
    blocked-without-callback flow, and the redacted failure all ride the
    pre-existing event machinery."""

    async def test_successful_framed_observation_flow(self):
        session = RecordingSession(make_result("3"))
        tool = mcp_tool(session, name="add", requires_approval=False)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="call"),
                make_prediction("finish", thought="done"),
                {"process_result": "5."},
            ],
        )

        assert {e["type"] for e in events} <= PRE_EXISTING_EVENT_TYPES

    async def test_redacted_failure_flow(self):
        error = ConnectionError("connect to some.host failed")
        tool = mcp_tool(ExplodingSession(error), name="add", requires_approval=False)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="try"),
                make_prediction("finish", thought="done"),
                {"process_result": "Reported."},
            ],
        )

        assert {e["type"] for e in events} <= PRE_EXISTING_EVENT_TYPES

    async def test_denied_approval_flow(self):
        session = RecordingSession(make_result("3"))
        tool = mcp_tool(session, name="add", requires_approval=True)
        agent = StreamingReAct(MagicMock(), tools=[tool])
        events = []
        agent.on_event(events.append)

        await drive(
            agent,
            [
                make_prediction("add", args={"a": 1}, thought="call"),
                make_prediction("finish", thought="done"),
                {"process_result": "Denied."},
            ],
            get_client_response=AsyncMock(return_value={"approved": False}),
        )

        assert {e["type"] for e in events} <= PRE_EXISTING_EVENT_TYPES
