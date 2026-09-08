"""Tests for MLflow span enrichment in the ReAct loop and canvas runs.

MLflow's DSPy autolog integration only produces generic spans
(``Predict.forward``, ``LM.__call__``), so ``StreamingReAct.aforward`` opens a
``react: iteration <n>`` span around each ReAct iteration (with a ``tool``
attribute when the iteration invokes a tool), and ``CanvasRunner.run`` enriches
the active ``canvas_run`` span with canvas metadata (``canvas_name``,
``canvas_id``, ``num_agents``, ``entry_agent``).

Both seams are best-effort: tracing failures must never alter execution.
These tests monkeypatch ``mlflow.start_span`` and
``mlflow.get_current_active_span`` with recorders so no real MLflow backend is
involved.
"""

import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import mlflow
import pytest

from canvas_server.config import settings
from canvas_server.runner import CanvasRunner
from canvas_server.streaming_react import StreamingReAct

# ---------------------------------------------------------------------------
# Shared recorders / fakes
# ---------------------------------------------------------------------------


class FakeSpan:
    """Minimal mlflow span stand-in recording attribute updates."""

    def __init__(self, name, span_type=None, attributes=None):
        self.name = name
        self.span_type = span_type
        self.attributes = dict(attributes or {})
        self.attribute_updates = []

    def set_attributes(self, attrs):
        self.attribute_updates.append(dict(attrs))
        self.attributes.update(attrs)


def _span_context(span):
    @contextmanager
    def entered():
        yield span

    return entered()


def make_start_span_recorder():
    """Builds a span list plus a drop-in ``mlflow.start_span`` replacement."""
    spans = []

    def start_span(name=None, span_type=None, attributes=None, **kwargs):
        span = FakeSpan(name, span_type=span_type, attributes=attributes)
        spans.append(span)
        return _span_context(span)

    return spans, start_span


class FakeTool:
    def __init__(self, name="FakeTool", result="ok"):
        self.__name__ = name
        self._result = result

    async def acall(self, **kwargs):
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


# ---------------------------------------------------------------------------
# StreamingReAct — react: iteration <n> spans
# ---------------------------------------------------------------------------


@pytest.fixture
def recorded_spans(monkeypatch):
    monkeypatch.setattr(settings, "mlflow_enabled", True)
    spans, start_span = make_start_span_recorder()
    monkeypatch.setattr(mlflow, "start_span", start_span)
    return spans


@pytest.mark.asyncio
async def test_aforward_opens_one_span_per_react_iteration(recorded_spans):
    agent = make_agent(FakeTool())
    pred_tool = make_prediction(tool_name="FakeTool", thought="use the tool")
    pred_finish = make_prediction(tool_name="finish", thought="done")
    pred_extract = {"process_result": "Done!"}

    result = await drive_aforward(agent, [pred_tool, pred_finish, pred_extract])

    assert result.process_result == "Done!"
    # One span per ReAct iteration (the extract step gets no span), 1-based.
    assert [span.name for span in recorded_spans] == [
        "react: iteration 1",
        "react: iteration 2",
    ]


@pytest.mark.asyncio
async def test_iteration_span_records_invoked_tool_name(recorded_spans):
    agent = make_agent(FakeTool(name="Weather"))
    pred_tool_a = make_prediction(tool_name="Weather")
    pred_tool_b = make_prediction(tool_name="Weather")
    pred_finish = make_prediction(tool_name="finish")
    pred_extract = {"process_result": "Done!"}

    await drive_aforward(agent, [pred_tool_a, pred_tool_b, pred_finish, pred_extract])

    assert recorded_spans[0].attributes["tool"] == "Weather"
    assert recorded_spans[1].attributes["tool"] == "Weather"
    # The finish iteration does not invoke a tool, so no tool attribute.
    assert "tool" not in recorded_spans[2].attributes


@pytest.mark.asyncio
async def test_iteration_spans_use_step_span_type(recorded_spans):
    agent = make_agent()
    pred_finish = make_prediction(tool_name="finish")
    pred_extract = {"process_result": "Done!"}

    await drive_aforward(agent, [pred_finish, pred_extract])

    assert all(span.span_type == "STEP" for span in recorded_spans)


@pytest.mark.asyncio
async def test_iteration_spans_skipped_when_mlflow_disabled(monkeypatch):
    monkeypatch.setattr(settings, "mlflow_enabled", False)
    spans, start_span = make_start_span_recorder()
    monkeypatch.setattr(mlflow, "start_span", start_span)

    agent = make_agent(FakeTool())
    pred_tool = make_prediction(tool_name="FakeTool")
    pred_finish = make_prediction(tool_name="finish")
    pred_extract = {"process_result": "Done!"}

    result = await drive_aforward(agent, [pred_tool, pred_finish, pred_extract])

    assert result.process_result == "Done!"
    assert spans == []


@pytest.mark.asyncio
async def test_aforward_survives_start_span_failures(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no mlflow server")

    monkeypatch.setattr(settings, "mlflow_enabled", True)
    monkeypatch.setattr(mlflow, "start_span", boom)

    agent = make_agent(FakeTool())
    pred_tool = make_prediction(tool_name="FakeTool")
    pred_finish = make_prediction(tool_name="finish")
    pred_extract = {"process_result": "Done!"}

    result = await drive_aforward(agent, [pred_tool, pred_finish, pred_extract])

    assert result.process_result == "Done!"
    assert result.trajectory["observation_0"] == "ok"


@pytest.mark.asyncio
async def test_aforward_survives_attribute_failures(recorded_spans):
    def boom(attrs):
        raise RuntimeError("span went away")

    for span in recorded_spans:
        span.set_attributes = boom

    agent = make_agent(FakeTool())
    pred_tool = make_prediction(tool_name="FakeTool")
    pred_finish = make_prediction(tool_name="finish")
    pred_extract = {"process_result": "Done!"}

    result = await drive_aforward(agent, [pred_tool, pred_finish, pred_extract])

    assert result.process_result == "Done!"


# ---------------------------------------------------------------------------
# CanvasRunner — canvas_run span attributes
# ---------------------------------------------------------------------------


class RecordingSpan:
    def __init__(self):
        self.attributes = {}
        self.attribute_updates = []

    def set_attributes(self, attrs):
        self.attribute_updates.append(dict(attrs))
        self.attributes.update(attrs)


class FakeCanvas:
    def __init__(self, id=None, name="Demo canvas", agent_nodes=None):
        self.id = id or uuid.uuid4()
        self.name = name
        self.agent_nodes = agent_nodes or []
        self.tool_nodes = []
        self.edges = []


class FakeAgentNode:
    def __init__(self, id=None, name="", agent_type="worker", is_entry_point=False):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = ""
        self.instructions = ""
        self.model_name = "ollama:llama3.1"
        self.agent_type = agent_type
        self.is_entry_point = is_entry_point
        self.position_x = 0
        self.position_y = 0


def _make_prediction(process_result=""):
    return MagicMock(
        process_result=process_result,
        trajectory={
            "thought_0": "",
            "tool_name_0": "finish",
            "tool_args_0": {},
        },
    )


def _make_agent_mock(text="Done!"):
    pred = _make_prediction(process_result=text)
    agent = AsyncMock(return_value=pred)
    agent.aforward = AsyncMock(return_value=pred)
    return agent


def make_runner(canvas):
    runner = CanvasRunner(canvas)
    runner.setup = AsyncMock()
    entry = canvas.agent_nodes[0]
    runner.node_map[entry.id] = entry
    runner.agents[entry.id] = _make_agent_mock("The answer is 42")
    return runner


@pytest.fixture
def active_span(monkeypatch):
    monkeypatch.setattr(settings, "mlflow_enabled", True)
    span = RecordingSpan()
    monkeypatch.setattr(mlflow, "get_current_active_span", lambda: span)
    return span


@pytest.mark.asyncio
async def test_run_enriches_canvas_run_span(active_span):
    entry = FakeAgentNode(name="EntryAgent", is_entry_point=True)
    worker = FakeAgentNode(name="HelperAgent")
    canvas = FakeCanvas(agent_nodes=[entry, worker])

    runner = make_runner(canvas)
    result = await runner.run("test prompt", AsyncMock())

    assert result == "The answer is 42"
    assert active_span.attributes == {
        "canvas_id": str(canvas.id),
        "canvas_name": "Demo canvas",
        "num_agents": 2,
        "entry_agent": "EntryAgent",
    }


@pytest.mark.asyncio
async def test_run_enrichment_defaults_entry_agent_to_first_node(active_span):
    worker = FakeAgentNode(name="OnlyAgent")
    canvas = FakeCanvas(agent_nodes=[worker])

    runner = make_runner(canvas)
    await runner.run("test prompt", AsyncMock())

    assert active_span.attributes["entry_agent"] == "OnlyAgent"
    assert active_span.attributes["num_agents"] == 1


@pytest.mark.asyncio
async def test_run_enrichment_skipped_when_mlflow_disabled(monkeypatch):
    monkeypatch.setattr(settings, "mlflow_enabled", False)
    calls = []

    def spy():
        calls.append(1)
        return RecordingSpan()

    monkeypatch.setattr(mlflow, "get_current_active_span", spy)

    canvas = FakeCanvas(agent_nodes=[FakeAgentNode(name="Solo")])
    runner = make_runner(canvas)
    await runner.run("test prompt", AsyncMock())

    assert calls == []


@pytest.mark.asyncio
async def test_run_enrichment_skipped_for_empty_canvas(active_span):
    canvas = FakeCanvas(agent_nodes=[])

    runner = CanvasRunner(canvas)
    runner.setup = AsyncMock()
    await runner.run("test prompt", AsyncMock())

    assert active_span.attribute_updates == []


@pytest.mark.asyncio
async def test_run_does_not_raise_without_active_span(monkeypatch):
    monkeypatch.setattr(settings, "mlflow_enabled", True)
    monkeypatch.setattr(mlflow, "get_current_active_span", lambda: None)

    canvas = FakeCanvas(agent_nodes=[FakeAgentNode(name="Solo")])
    runner = make_runner(canvas)

    result = await runner.run("test prompt", AsyncMock())
    assert result == "The answer is 42"


@pytest.mark.asyncio
async def test_run_survives_attribute_failures(monkeypatch):
    class ExplodingSpan:
        def set_attributes(self, attrs):
            raise RuntimeError("span went away")

    monkeypatch.setattr(settings, "mlflow_enabled", True)
    monkeypatch.setattr(mlflow, "get_current_active_span", lambda: ExplodingSpan())

    canvas = FakeCanvas(agent_nodes=[FakeAgentNode(name="Solo")])
    runner = make_runner(canvas)

    result = await runner.run("test prompt", AsyncMock())
    assert result == "The answer is 42"
