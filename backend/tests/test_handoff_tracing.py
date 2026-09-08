"""Tests for agent tracing spans opened by HandoffToolBuilder handoff tools."""

import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from canvas_server.runner.handoff import HandoffToolBuilder


def make_recorder(recorded, active):
    """Build a stand-in for ``agent_span`` that records each span it opens."""

    @contextmanager
    def recorder(agent_name, node_id=None, agent_type=None, canvas_name=None):
        span = SimpleNamespace(
            name=f"agent: {agent_name}",
            agent_name=agent_name,
            node_id=node_id,
            agent_type=agent_type,
            canvas_name=canvas_name,
        )
        recorded.append(span)
        token = (agent_name, node_id, agent_type)
        active.append(token)
        try:
            yield span
        finally:
            active.remove(token)

    return recorder


class FakeRunState:
    """Minimal run_state stand-in matching HandoffToolBuilder's usage."""

    def __init__(self, node_map, agents):
        self.node_map = node_map
        self.agents = agents
        self.agent_factory = SimpleNamespace(
            build_worker_prompt=lambda task, history: f"prompt: {task}",
            needs_history=lambda node: False,
        )
        self.conversation_service = SimpleNamespace(persist_message=AsyncMock())
        self.get_client_response = AsyncMock(return_value="ok")
        self.send_event = AsyncMock()

    async def get_or_build_agent(self, target_id, task=None):
        return self.agents[target_id]


def make_agent(answer="Answer!", fail=None, active=None, snapshots=None):
    """Build a fake agent whose ``aforward`` snapshots the open spans when called."""

    async def aforward(**kwargs):
        if snapshots is not None:
            snapshots.append(list(active))
        if fail is not None:
            raise fail
        return SimpleNamespace(process_result=answer)

    return SimpleNamespace(aforward=AsyncMock(side_effect=aforward))


@pytest.mark.asyncio
async def test_handoff_tool_opens_agent_span_around_aforward(monkeypatch):
    recorded = []
    active = []
    snapshots = []
    monkeypatch.setattr(
        "canvas_server.runner.handoff.agent_span",
        make_recorder(recorded, active),
    )

    target_id = uuid.uuid4()
    target_node = SimpleNamespace(name="WeatherAgent", agent_type="worker", role=None)
    agent = make_agent("Sunny", active=active, snapshots=snapshots)

    run_state = FakeRunState(
        node_map={target_id: target_node}, agents={target_id: agent}
    )
    builder = HandoffToolBuilder(run_state)

    tool = builder.make_handoff_tool(target_id, "Router", AsyncMock(), history="")
    result = await tool("what is the weather?")

    assert result == "Sunny"
    assert len(recorded) == 1
    span = recorded[0]
    assert span.name == "agent: WeatherAgent"
    assert span.node_id == target_id
    assert span.agent_type == "worker"

    # the aforward call ran while the span was open
    agent.aforward.assert_awaited_once()
    assert snapshots == [[("WeatherAgent", target_id, "worker")]]
    # and the span was closed again by the time the tool returned
    assert active == []


@pytest.mark.asyncio
async def test_parallel_handoff_opens_one_span_per_target(monkeypatch):
    recorded = []
    active = []
    monkeypatch.setattr(
        "canvas_server.runner.handoff.agent_span",
        make_recorder(recorded, active),
    )

    target_a_id = uuid.uuid4()
    target_b_id = uuid.uuid4()
    node_map = {
        target_a_id: SimpleNamespace(name="WorkerA", agent_type="worker", role=None),
        target_b_id: SimpleNamespace(name="WorkerB", agent_type="worker", role=None),
    }
    agents = {
        target_a_id: make_agent("Result A"),
        target_b_id: make_agent("Result B"),
    }

    run_state = FakeRunState(node_map=node_map, agents=agents)
    builder = HandoffToolBuilder(run_state)

    parallel_tool = builder.make_parallel_handoff_tool(
        [target_a_id, target_b_id], "Router", AsyncMock(), history=""
    )
    result = await parallel_tool(
        [
            {"agent_name": "WorkerA", "task": "task 1"},
            {"agent_name": "WorkerB", "task": "task 2"},
        ]
    )

    assert "Agent 'WorkerA' findings:\nResult A" in result
    assert "Agent 'WorkerB' findings:\nResult B" in result

    span_names = {span.name for span in recorded}
    assert span_names == {"agent: WorkerA", "agent: WorkerB"}
    span_nodes = {span.node_id for span in recorded}
    assert span_nodes == {target_a_id, target_b_id}
    assert all(span.agent_type == "worker" for span in recorded)
    # all spans closed by the time the parallel tool returned
    assert active == []


@pytest.mark.asyncio
async def test_handoff_agent_exception_still_returns_error_string(monkeypatch):
    recorded = []
    active = []
    monkeypatch.setattr(
        "canvas_server.runner.handoff.agent_span",
        make_recorder(recorded, active),
    )

    target_id = uuid.uuid4()
    target_node = SimpleNamespace(name="BrokenAgent", agent_type="worker", role=None)
    agent = make_agent(fail=ValueError("boom"))
    run_state = FakeRunState(
        node_map={target_id: target_node}, agents={target_id: agent}
    )
    builder = HandoffToolBuilder(run_state)

    tool = builder.make_handoff_tool(target_id, "Router", AsyncMock(), history="")
    result = await tool("do the thing")

    # existing behavior: the exception is converted to the "Error: {e}" answer
    assert result == "Error: boom"
    run_state.conversation_service.persist_message.assert_awaited_with(
        role="assistant",
        content="Error: boom",
        agent_name="BrokenAgent",
        node_id=target_id,
        event_type="final_answer",
    )

    # the span was still opened (and closed) around the failing execution
    assert len(recorded) == 1
    assert recorded[0].name == "agent: BrokenAgent"
    assert active == []
