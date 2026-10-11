"""MCP results ride the existing ``tool_result`` event payload (ticket #138).

Zero new event types: the JSON-safe content-block structure captured by the
MCP callables (``mcp_tools.format_mcp_result``, spec §4.5) is persisted on
the existing ``tool_result`` event — only when the invoked tool provides it,
so non-MCP event shapes are untouched (the untrusted-framing/redaction pass
is #140's scope).
"""

from unittest.mock import MagicMock, patch

from dspy.adapters.types.tool import Tool as DspyTool

from canvas_server.streaming_react import StreamingReAct


def make_agent(tool):
    agent = StreamingReAct(MagicMock(), tools=[tool])
    return agent


def make_prediction(tool_name="finish", thought="", args=None):
    pred = MagicMock()
    pred.next_thought = thought
    pred.next_tool_name = tool_name
    pred.next_tool_args = args or {}
    return pred


async def drive(agent, predictions):
    with patch.object(
        agent, "_async_call_with_potential_trajectory_truncation"
    ) as mock_call:
        mock_call.side_effect = predictions
        return await agent.aforward()


def raw_tool(observation, raw):
    async def fn(*_a, **_k):
        """Reference tool."""
        fn.last_raw_content_blocks = raw
        return observation

    fn.last_raw_content_blocks = None
    return DspyTool(func=fn, name="add", desc="Reference tool.", args={}, arg_types={}, arg_desc={})


def plain_tool(observation="ok"):
    async def fn(*_a, **_k):
        """Plain author tool."""
        observation2 = observation
        return observation2

    return DspyTool(func=fn, name="plain", desc="Plain author tool.", args={}, arg_types={}, arg_desc={})


async def test_tool_result_event_carries_raw_content_blocks():
    raw = [{"type": "text", "text": "3"}]
    tool = raw_tool("3", raw)
    agent = make_agent(tool)
    events = []
    agent.on_event(events.append)

    await drive(
        agent,
        [
            make_prediction("add", args={"a": 1, "b": 2}, thought="call"),
            make_prediction("finish", thought="done"),
            {"process_result": "Done!"},
        ],
    )

    event = [e for e in events if e["type"] == "tool_result"][0]
    assert event["tool"] == "add"
    assert event["output"] == "3"
    assert event["raw_content"] == raw


async def test_plain_tools_do_not_gain_a_raw_content_key():
    tool = plain_tool("plain output")
    agent = make_agent(tool)
    events = []
    agent.on_event(events.append)

    await drive(
        agent,
        [
            make_prediction("plain", args={}, thought="call"),
            make_prediction("finish", thought="done"),
            {"process_result": "Done!"},
        ],
    )

    event = [e for e in events if e["type"] == "tool_result"][0]
    assert event["output"] == "plain output"
    assert "raw_content" not in event


async def test_failed_call_does_not_leak_previous_raw_blocks():
    tool = raw_tool("3", [{"type": "text", "text": "3"}])
    agent = make_agent(tool)
    events = []
    agent.on_event(events.append)

    # First call succeeds and frames raw content; second call raises.
    async def failing(*_a, **_k):
        """Reference tool."""
        raise RuntimeError("boom")

    tool.func = failing

    await drive(
        agent,
        [
            make_prediction("add", args={}, thought="call"),
            make_prediction("add", args={}, thought="call again"),
            make_prediction("finish", thought="done"),
            {"process_result": "Done!"},
        ],
    )

    results = [e for e in events if e["type"] == "tool_result"]
    assert results[-1]["output"].startswith("Execution error in add")
    assert "raw_content" not in results[-1]
