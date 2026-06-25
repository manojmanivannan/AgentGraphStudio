import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_server.runner.agent_factory import AgentFactory
from canvas_server.streaming_react import StreamingReAct


class FakeAgentNode:
    def __init__(self, id=None, name="Agent", agent_type="worker", enable_hitl=False):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = "You are a helpful assistant"
        self.instructions = ""
        self.model_name = "ollama:llama3.1"
        self.agent_type = agent_type
        self.enable_hitl = enable_hitl
        self.is_entry_point = False
        self.position_x = 0
        self.position_y = 0


class FakeToolNode:
    def __init__(self, id=None, name="Tool", requires_approval=False):
        self.id = id or uuid.uuid4()
        self.name = name
        self.code = "def Tool(): pass"
        self.dependencies = []
        self.args = []
        self.requires_approval = requires_approval
        self.position_x = 0
        self.position_y = 0


@pytest.mark.asyncio
async def test_ask_human_tool_registration():
    # Test that ask_human tool is added only when enable_hitl=True
    node_with_hitl = FakeAgentNode(enable_hitl=True)
    node_without_hitl = FakeAgentNode(enable_hitl=False)

    factory = AgentFactory(
        lm=MagicMock(),
        tool_registry=MagicMock(),
        memory_manager=MagicMock(),
        edges=[],
    )

    # Mock build_signature
    with patch.object(factory, "build_signature", return_value=MagicMock()):
        agent_with_hitl = await factory.build_worker(node_with_hitl)
        agent_without_hitl = await factory.build_worker(node_without_hitl)

        # Check tools
        tools_with_hitl = [getattr(t, "__name__", str(t)) for t in agent_with_hitl.tools]
        tools_without_hitl = [getattr(t, "__name__", str(t)) for t in agent_without_hitl.tools]

        assert "ask_human" in tools_with_hitl
        assert "ask_human" not in tools_without_hitl


@pytest.mark.asyncio
async def test_tool_approval_intercept_approve():
    # Test that tool execution succeeds when approved
    class FakeTool:
        async def acall(self, **kwargs):
            return "Success"

    fake_tool = FakeTool()
    fake_tool.requires_approval = True
    fake_tool.node_id = uuid.uuid4()
    # Mock name for key registry lookup
    fake_tool.__name__ = "FakeTool"

    sig = MagicMock()
    # Create StreamingReAct, register FakeTool in tools map
    agent = StreamingReAct(sig, tools=[])
    agent.tools = {"FakeTool": fake_tool}

    get_client_response = AsyncMock(return_value={"approved": True})

    # Mock the react prediction step to call the tool
    pred_react = MagicMock(next_thought="Call tool", next_tool_name="FakeTool", next_tool_args={})
    pred_extract = MagicMock(process_result="Done!")

    with patch.object(agent, "_async_call_with_potential_trajectory_truncation") as mock_call:
        # First call to ReAct, second call is finish, third call is extract
        pred_finish = MagicMock(next_thought="Finish", next_tool_name="finish", next_tool_args={})
        mock_call.side_effect = [pred_react, pred_finish, pred_extract]

        result = await agent.aforward(get_client_response=get_client_response)

        # Verify get_client_response was called
        get_client_response.assert_awaited_once()
        assert result.trajectory["observation_0"] == "Success"


@pytest.mark.asyncio
async def test_tool_approval_intercept_deny():
    # Test that tool execution is skipped when denied
    class FakeTool:
        async def acall(self, **kwargs):
            return "Should not run"

    fake_tool = FakeTool()
    fake_tool.requires_approval = True
    fake_tool.node_id = uuid.uuid4()
    # Mock name for key registry lookup
    fake_tool.__name__ = "FakeTool"

    sig = MagicMock()
    # Create StreamingReAct, register FakeTool in tools map
    agent = StreamingReAct(sig, tools=[])
    agent.tools = {"FakeTool": fake_tool}

    get_client_response = AsyncMock(return_value={"approved": False})

    # Mock the react prediction step to call the tool
    pred_react = MagicMock(next_thought="Call tool", next_tool_name="FakeTool", next_tool_args={})
    pred_extract = MagicMock(process_result="Done!")

    with patch.object(agent, "_async_call_with_potential_trajectory_truncation") as mock_call:
        pred_finish = MagicMock(next_thought="Finish", next_tool_name="finish", next_tool_args={})
        mock_call.side_effect = [pred_react, pred_finish, pred_extract]

        result = await agent.aforward(get_client_response=get_client_response)

        # Verify get_client_response was called and tool observation is denied string
        get_client_response.assert_awaited_once()
        assert result.trajectory["observation_0"] == "Tool execution denied by user."


def test_ask_human_prompt_instructions():
    # Test that ask_human prompt instructions are added when enable_hitl=True
    node_with_hitl = FakeAgentNode(enable_hitl=True)
    node_without_hitl = FakeAgentNode(enable_hitl=False)

    factory = AgentFactory(
        lm=MagicMock(),
        tool_registry=MagicMock(),
        memory_manager=MagicMock(),
        edges=[],
    )

    sig_with_hitl = factory.build_signature(node_with_hitl)
    sig_without_hitl = factory.build_signature(node_without_hitl)

    assert "ask_human" in sig_with_hitl.__doc__
    assert "ask_human" not in sig_without_hitl.__doc__


@pytest.mark.asyncio
async def test_streaming_react_propagates_run_aborted_error():
    from canvas_server.exceptions import RunAbortedError

    # 1. Test event callback abort propagation
    sig = MagicMock()
    agent = StreamingReAct(sig, tools=[])

    async def aborting_callback(event):
        raise RunAbortedError("Abort from callback")

    agent.on_event(aborting_callback)

    with pytest.raises(RunAbortedError):
        await agent._emit({"type": "thought", "content": "test"})

    # 2. Test get_client_response abort propagation in aforward tool approval
    class FakeTool:
        async def acall(self, **kwargs):
            return "Success"

    fake_tool = FakeTool()
    fake_tool.requires_approval = True
    fake_tool.node_id = uuid.uuid4()
    fake_tool.__name__ = "FakeTool"

    agent = StreamingReAct(sig, tools=[])
    agent.tools = {"FakeTool": fake_tool}

    async def get_client_response_abort(request_id, response_type):
        raise RunAbortedError("Abort from client response")

    pred_react = MagicMock(next_thought="Call tool", next_tool_name="FakeTool", next_tool_args={})
    pred_extract = MagicMock(process_result="Done!")

    with patch.object(agent, "_async_call_with_potential_trajectory_truncation") as mock_call:
        mock_call.side_effect = [pred_react, pred_extract]
        with pytest.raises(RunAbortedError):
            await agent.aforward(get_client_response=get_client_response_abort)

    # 3. Test tool call abort propagation in aforward tool execution
    class AbortingTool:
        async def acall(self, **kwargs):
            raise RunAbortedError("Abort during tool run")

    aborting_tool = AbortingTool()
    aborting_tool.requires_approval = False
    aborting_tool.node_id = uuid.uuid4()
    aborting_tool.__name__ = "AbortingTool"

    agent = StreamingReAct(sig, tools=[])
    agent.tools = {"AbortingTool": aborting_tool}

    pred_react_tool = MagicMock(next_thought="Call aborting tool", next_tool_name="AbortingTool", next_tool_args={})

    with patch.object(agent, "_async_call_with_potential_trajectory_truncation") as mock_call:
        mock_call.side_effect = [pred_react_tool, pred_extract]
        with pytest.raises(RunAbortedError):
            await agent.aforward()

