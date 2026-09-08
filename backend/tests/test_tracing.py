"""Tests for the named MLflow span helpers in ``canvas_server.runner.tracing``.

MLflow's DSPy autolog integration names spans after module classes
(``Predict.forward``, ``LM.__call__``), which makes trace hierarchies
unreadable. The helpers here wrap each agent execution in a span named after
the real agent so all DSPy spans nest under a readable label.
"""

import uuid

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from canvas_server.runner import tracing


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    """Point MLflow at a disposable sqlite backend and experiment.

    The cwd is moved into ``tmp_path`` so MLflow's default artifact layout
    (created alongside the sqlite backend) stays in the temp directory.
    """
    monkeypatch.chdir(tmp_path)
    # Async trace export flushes at process exit and loses the artifact-location
    # tag mid-test; sync logging makes traces immediately readable.
    monkeypatch.setenv("MLFLOW_ENABLE_ASYNC_TRACE_LOGGING", "false")
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("tracing-tests")
    yield mlflow
    mlflow.set_tracking_uri(None)


def _span_names(trace):
    return {span.name for span in trace.data.spans}


def _find_span(trace, name):
    return next(span for span in trace.data.spans if span.name == name)


def test_agent_span_is_named_after_the_agent(trace_store):
    with mlflow.start_span(name="canvas_run"), tracing.agent_span("WeatherAgent") as span:
        trace_id = span.trace_id

    trace = MlflowClient().get_trace(trace_id)
    assert "agent: WeatherAgent" in _span_names(trace)


def test_agent_span_carries_agent_attributes(trace_store):
    node_id = uuid.uuid4()
    with tracing.agent_span(
        "WeatherAgent",
        node_id=node_id,
        agent_type="worker",
        canvas_name="Demo canvas",
    ) as span:
        trace_id = span.trace_id

    trace = MlflowClient().get_trace(trace_id)
    agent_span_ = _find_span(trace, "agent: WeatherAgent")
    assert agent_span_.attributes["agent_node_id"] == str(node_id)
    assert agent_span_.attributes["agent_type"] == "worker"
    assert agent_span_.attributes["canvas_name"] == "Demo canvas"


def test_dspy_style_child_spans_nest_under_agent_span(trace_store):
    with tracing.agent_span("WeatherAgent") as span:
        trace_id = span.trace_id
        with mlflow.start_span(name="Predict.forward"):
            pass

    trace = MlflowClient().get_trace(trace_id)
    predict = _find_span(trace, "Predict.forward")
    agent_span_ = _find_span(trace, "agent: WeatherAgent")
    assert predict.parent_id == agent_span_.span_id


def test_agent_span_defaults_to_unknown_span_type_when_unlabeled(trace_store):
    with tracing.agent_span("WeatherAgent") as span:
        trace_id = span.trace_id

    trace = MlflowClient().get_trace(trace_id)
    agent_span_ = _find_span(trace, "agent: WeatherAgent")
    assert agent_span_.span_type == tracing.AGENT_SPAN_TYPE


def test_agent_span_is_skipped_when_mlflow_is_disabled(monkeypatch):
    monkeypatch.setattr(tracing.settings, "mlflow_enabled", False)

    with tracing.agent_span("WeatherAgent") as span:
        assert span is None


def test_agent_span_survives_tracing_failures(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no mlflow server")

    monkeypatch.setattr(mlflow, "start_span", boom)

    with tracing.agent_span("WeatherAgent") as span:
        assert span is None


def test_agent_span_propagates_body_exceptions(trace_store):
    with pytest.raises(ValueError, match="agent exploded"), tracing.agent_span("WeatherAgent") as span:
        trace_id = span.trace_id
        raise ValueError("agent exploded")

    trace = MlflowClient().get_trace(trace_id)
    agent_span_ = _find_span(trace, "agent: WeatherAgent")
    assert agent_span_.status.status_code.name == "ERROR"
