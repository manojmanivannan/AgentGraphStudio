"""Tests for named MLflow agent spans around agent execution strategies.

Each strategy's ``agent.aforward(...)`` call must run inside an
``agent_span`` named after the real agent so DSPy autolog spans nest under a
readable parent instead of generic ``Predict.forward`` names.

These tests use a recorder context manager monkeypatched over
``execution.agent_span`` so no real MLflow backend is needed; the recorder
also exposes an ``active`` flag so fakes can assert the span was actually
entered around the ``aforward`` call.
"""

import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from canvas_server.exceptions import LLMConfigurationError
from canvas_server.runner.config import RunContext
from canvas_server.runner.execution import (
    ChainExecution,
    RouterExecution,
    StrategyServices,
    WorkerExecution,
)


def make_span_recorder():
    """Builds a recorder plus a drop-in ``agent_span`` replacement."""
    rec = SimpleNamespace(calls=[], active=False)

    @contextmanager
    def agent_span(agent_name, node_id=None, agent_type=None, canvas_name=None):
        rec.calls.append(
            {
                "agent_name": agent_name,
                "node_id": node_id,
                "agent_type": agent_type,
                "canvas_name": canvas_name,
            }
        )
        rec.active = True
        try:
            yield SimpleNamespace(name=f"agent: {agent_name}")
        finally:
            rec.active = False

    return rec, agent_span


class FakeAgent:
    """Minimal DSPy agent stand-in recording whether a span was active."""

    def __init__(self, recorder, exc=None):
        self._recorder = recorder
        self._exc = exc
        self.forward_kwargs = None
        self.span_active_during_forward = None

    async def aforward(self, **kwargs):
        self.forward_kwargs = kwargs
        self.span_active_during_forward = self._recorder.active
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(process_result="hello", trajectory=None)


def make_services(recorder, *, agent_name="WeatherAgent", agent_type="worker", with_canvas=True):
    """Builds a StrategyServices wired around a single fake agent node."""
    agent_id = uuid.uuid4()
    fake_agent = FakeAgent(recorder)
    node = SimpleNamespace(id=agent_id, name=agent_name, agent_type=agent_type)
    conversation_service = SimpleNamespace(persist_message=AsyncMock())

    run_state_kwargs = {
        "get_or_build_agent": AsyncMock(return_value=fake_agent),
        "get_client_response": None,
        "node_map": {agent_id: node},
        "agents": {agent_id: fake_agent},
        "agent_factory": SimpleNamespace(
            needs_history=lambda n: True,
            build_worker_prompt=lambda prompt, *extra: prompt,
        ),
        "conversation_service": conversation_service,
        "handoff_tool_builder": None,
        "tool_registry": SimpleNamespace(),
        "attach_events": lambda *a, **k: None,
        "send_event": AsyncMock(),
        "user_prompt": "",
        "history_text": "",
        "dspy_history": None,
    }
    if with_canvas:
        run_state_kwargs["canvas"] = SimpleNamespace(name="Demo canvas")

    run_state = SimpleNamespace(**run_state_kwargs)
    services = StrategyServices(run_state, edge_graph=None, memory_manager=None)
    return SimpleNamespace(
        agent_id=agent_id,
        fake_agent=fake_agent,
        node=node,
        services=services,
        conversation_service=conversation_service,
    )


@pytest.fixture
def recorder(monkeypatch):
    """Patches ``agent_span`` at the import site with the recorder version."""
    rec, agent_span = make_span_recorder()
    # raising=False: before implementation the module has no ``agent_span``
    # name yet, and the assertions below drive the red phase instead.
    monkeypatch.setattr(
        "canvas_server.runner.execution.agent_span", agent_span, raising=False
    )
    return rec


@pytest.mark.asyncio
async def test_worker_execution_opens_named_agent_span_around_aforward(recorder):
    harness = make_services(recorder)
    ctx = RunContext(
        user_prompt="what is the weather?",
        send_event=AsyncMock(),
        target_agent_id=harness.agent_id,
        dspy_history=object(),
    )

    result = await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

    assert result == "hello"
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["agent_name"] == "WeatherAgent"
    assert call["node_id"] == harness.agent_id
    assert call["agent_type"] == "worker"
    assert call["canvas_name"] == "Demo canvas"
    # The span must actually be open while the DSPy ReAct loop runs.
    assert harness.fake_agent.span_active_during_forward is True
    assert harness.fake_agent.forward_kwargs["history"] is ctx.dspy_history
    assert recorder.active is False
    # Persist / event behavior unchanged.
    harness.conversation_service.persist_message.assert_awaited_once_with(
        role="assistant",
        content="hello",
        agent_name="WeatherAgent",
        node_id=harness.agent_id,
        event_type="final_answer",
    )


@pytest.mark.asyncio
async def test_router_execution_opens_named_agent_span_around_aforward(recorder):
    harness = make_services(
        recorder, agent_name="Orchestrator", agent_type="router"
    )
    ctx = RunContext(
        user_prompt="do the thing",
        send_event=AsyncMock(),
        target_agent_id=harness.agent_id,
    )

    result = await RouterExecution(harness.services).execute(harness.agent_id, ctx)

    assert result == "hello"
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["agent_name"] == "Orchestrator"
    assert call["node_id"] == harness.agent_id
    assert call["agent_type"] == "router"
    assert call["canvas_name"] == "Demo canvas"
    assert harness.fake_agent.span_active_during_forward is True
    assert recorder.active is False
    harness.conversation_service.persist_message.assert_awaited_once_with(
        role="assistant",
        content="hello",
        agent_name="Orchestrator",
        node_id=harness.agent_id,
        event_type="final_answer",
    )


@pytest.mark.asyncio
async def test_chain_execution_opens_agent_span_per_worker(recorder):
    harness = make_services(recorder)
    harness.services.edge_graph = SimpleNamespace(
        build_handoff_map=lambda ids: {}
    )
    ctx = RunContext(
        user_prompt="chain prompt",
        send_event=AsyncMock(),
        target_agent_id=harness.agent_id,
    )

    result = await ChainExecution(harness.services).execute(harness.agent_id, ctx)

    assert result == "hello"
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["agent_name"] == "WeatherAgent"
    assert call["node_id"] == harness.agent_id
    assert call["agent_type"] == "worker"
    assert harness.fake_agent.span_active_during_forward is True


@pytest.mark.asyncio
async def test_agent_span_omits_canvas_name_when_not_available(recorder):
    harness = make_services(recorder, with_canvas=False)
    ctx = RunContext(
        user_prompt="hi",
        send_event=AsyncMock(),
        target_agent_id=harness.agent_id,
    )

    await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

    assert recorder.calls[0]["canvas_name"] is None


@pytest.mark.asyncio
async def test_terminal_llm_error_still_propagates_inside_span(recorder):
    boom = LLMConfigurationError("no api key configured")
    harness = make_services(recorder)
    harness.fake_agent._exc = boom
    ctx = RunContext(
        user_prompt="hi",
        send_event=AsyncMock(),
        target_agent_id=harness.agent_id,
    )

    with pytest.raises(LLMConfigurationError):
        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

    assert len(recorder.calls) == 1
    assert harness.fake_agent.span_active_during_forward is True
    assert recorder.active is False
    # Terminal errors must NOT be persisted as friendly final answers.
    harness.conversation_service.persist_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_terminal_llm_error_still_propagates_inside_span(recorder):
    boom = LLMConfigurationError("no api key configured")
    harness = make_services(
        recorder, agent_name="Orchestrator", agent_type="router"
    )
    harness.fake_agent._exc = boom
    ctx = RunContext(
        user_prompt="hi",
        send_event=AsyncMock(),
        target_agent_id=harness.agent_id,
    )

    with pytest.raises(LLMConfigurationError):
        await RouterExecution(harness.services).execute(harness.agent_id, ctx)

    assert len(recorder.calls) == 1
    assert recorder.active is False
    harness.conversation_service.persist_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_agent_failure_keeps_friendly_error_path(recorder):
    harness = make_services(recorder)
    harness.fake_agent._exc = ValueError("something broke")
    send_event = AsyncMock()
    ctx = RunContext(
        user_prompt="hi",
        send_event=send_event,
        target_agent_id=harness.agent_id,
    )

    result = await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

    assert result is None
    assert len(recorder.calls) == 1
    assert recorder.active is False
    harness.conversation_service.persist_message.assert_awaited_once_with(
        role="assistant",
        content="something broke",
        agent_name="WeatherAgent",
        node_id=harness.agent_id,
        event_type="final_answer",
    )
    send_event.assert_awaited_once()
    payload = send_event.await_args.args[0]
    assert payload["type"] == "final_answer"
    assert payload["content"] == "something broke"
    assert payload["node_id"] == str(harness.agent_id)
