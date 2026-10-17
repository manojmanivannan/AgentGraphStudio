"""Tests for the ReAct loop's unknown-tool guard (spec mcp-client-support §4.7).

The ReAct loop previously looked the LLM-selected tool name up in its tools
map unguarded (``self.tools[name]``), outside the try block that converts tool
failures into observations. Renamed or unknown tool names then raised out of
the loop and failed the whole run.

These tests drive the public ``aforward`` seam with staged fake LM
predictions (same pattern as ``test_streaming_react_tracing.py``) and assert
the loop continues with the standard ``Execution error in <tool>`` observation
instead of raising.
"""

from unittest.mock import MagicMock, patch

import pytest

from canvas_server.streaming_react import StreamingReAct


class FakeTool:
    def __init__(self, name="FakeTool", result="ok"):
        self.__name__ = name
        self._result = result
        self.calls = []

    async def acall(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


def make_agent(tool=None):
    agent = StreamingReAct(MagicMock(), tools=[])
    if tool is not None:
        agent.tools = {tool.__name__: tool}
    return agent


def make_prediction(tool_name="finish", thought="", args=None):
    pred = MagicMock()
    pred.next_thought = thought
    pred.next_tool_name = tool_name
    pred.next_tool_args = args or {}
    return pred


async def drive_aforward(agent, predictions):
    with patch.object(
        agent, "_async_call_with_potential_trajectory_truncation"
    ) as mock_call:
        mock_call.side_effect = predictions
        return await agent.aforward()


@pytest.mark.asyncio
async def test_unknown_tool_name_yields_execution_error_observation_and_continues():
    agent = make_agent(FakeTool())
    pred_unknown = make_prediction(
        tool_name="Renamed_Unknown_Too1", thought="call the renamed tool"
    )
    pred_finish = make_prediction(tool_name="finish", thought="done")
    pred_extract = {"process_result": "Done!"}

    events = []
    agent.on_event(events.append)

    result = await drive_aforward(agent, [pred_unknown, pred_finish, pred_extract])

    # The run completed rather than raising.
    assert result.process_result == "Done!"

    tool_result_events = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_result_events) == 1
    event = tool_result_events[0]
    assert event["tool"] == "Renamed_Unknown_Too1"
    assert event["output"].startswith("Execution error in Renamed_Unknown_Too1:")
    assert "Unknown tool" in event["output"]

    # The failure observation is fed back to the LLM as part of the trajectory.
    assert result.trajectory["observation_0"].startswith(
        "Execution error in Renamed_Unknown_Too1:"
    )


@pytest.mark.asyncio
async def test_unknown_tool_does_not_invoke_any_tool():
    tool = FakeTool()
    agent = make_agent(tool)
    pred_unknown = make_prediction(tool_name="Does_Not_Exist", thought="hmm")
    pred_recover = make_prediction(tool_name="FakeTool", args={"q": "x"}, thought="retry real tool")
    pred_finish = make_prediction(tool_name="finish", thought="done")
    pred_extract = {"process_result": "Recovered!"}

    await drive_aforward(agent, [pred_unknown, pred_recover, pred_finish, pred_extract])

    assert tool.calls == [{"q": "x"}]


@pytest.mark.asyncio
async def test_known_tool_invocation_still_works():
    tool = FakeTool(result="tool output")
    agent = make_agent(tool)
    pred_tool = make_prediction(tool_name="FakeTool", args={"q": "y"}, thought="use tool")
    pred_finish = make_prediction(tool_name="finish", thought="done")
    pred_extract = {"process_result": "Done!"}

    events = []
    agent.on_event(events.append)

    result = await drive_aforward(agent, [pred_tool, pred_finish, pred_extract])

    assert result.trajectory["observation_0"] == "tool output"
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["output"] == "tool output"
