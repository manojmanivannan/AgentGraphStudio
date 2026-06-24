import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from canvas_server.runner.run_state import CanvasRunState


class FakeAgent:
    def __init__(self):
        self._callback = None

    def on_event(self, callback):
        self._callback = callback


@pytest.mark.asyncio
async def test_attach_events_persists_tool_result_as_tool_role_with_tool_node_id():
    worker_id = uuid.uuid4()
    tool_id = uuid.uuid4()

    fake_agent = FakeAgent()
    conversation_service = SimpleNamespace(persist_message=AsyncMock())
    tool_registry = SimpleNamespace(_tool_name_to_id={"get_weather": tool_id})

    run_state = CanvasRunState(
        canvas=SimpleNamespace(),
        agent_factory=SimpleNamespace(),
        conversation_service=conversation_service,
        tool_registry=tool_registry,
    )
    run_state.node_map = {
        worker_id: SimpleNamespace(name="WeatherAgent"),
    }
    run_state.agents = {worker_id: fake_agent}
    run_state.send_event = AsyncMock()

    run_state.attach_events(worker_id)
    assert fake_agent._callback is not None

    await fake_agent._callback(
        {
            "type": "tool_result",
            "tool": "get_weather",
            "output": "Sunny",
        }
    )

    conversation_service.persist_message.assert_awaited_once_with(
        role="tool",
        content="Sunny",
        agent_name="get_weather",
        node_id=tool_id,
        event_type="tool_result",
    )

    run_state.send_event.assert_awaited_once()
    payload = run_state.send_event.await_args.args[0]
    assert payload["type"] == "tool_result"
    assert payload["node_id"] == str(tool_id)


@pytest.mark.asyncio
async def test_attach_events_persists_tool_approval_request():
    worker_id = uuid.uuid4()
    tool_id = uuid.uuid4()

    fake_agent = FakeAgent()
    conversation_service = SimpleNamespace(persist_message=AsyncMock())
    tool_registry = SimpleNamespace(_tool_name_to_id={"get_weather": tool_id})

    run_state = CanvasRunState(
        canvas=SimpleNamespace(),
        agent_factory=SimpleNamespace(),
        conversation_service=conversation_service,
        tool_registry=tool_registry,
    )
    run_state.node_map = {
        worker_id: SimpleNamespace(name="WeatherAgent"),
    }
    run_state.agents = {worker_id: fake_agent}
    run_state.send_event = AsyncMock()

    run_state.attach_events(worker_id)
    assert fake_agent._callback is not None

    await fake_agent._callback(
        {
            "type": "tool_approval_request",
            "request_id": "req-123",
            "tool": "get_weather",
            "args": {"city": "Paris"},
            "node_id": str(tool_id),
        }
    )

    conversation_service.persist_message.assert_awaited_once_with(
        role="tool",
        content="Tool approval required: get_weather",
        agent_name="WeatherAgent",
        node_id=str(tool_id),
        event_type="tool_approval_request",
    )
