"""Named MLflow span helpers for agent executions.

MLflow's DSPy autolog integration names spans after DSPy module classes
(``Predict.forward``, ``ChainOfThought.forward``, ``LM.__call__``), which makes
the trace hierarchy unreadable — every agent on the canvas looks identical.
Wrapping each agent execution in a span named after the real agent gives all
of its DSPy autolog spans a readable parent.

Tracing is best-effort: the helpers must never raise or alter execution
behavior when MLflow is disabled or unreachable.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import mlflow

from canvas_server.config import settings

logger = logging.getLogger("canvas_server.runner.tracing")

AGENT_SPAN_TYPE = "AGENT"


@contextmanager
def agent_span(
    agent_name: str,
    node_id=None,
    agent_type: str | None = None,
    canvas_name: str | None = None,
) -> Iterator[mlflow.entities.Span | None]:
    """Open a span named ``agent: <agent_name>`` around an agent execution.

    DSPy autolog spans opened inside this context nest beneath it, so the
    trace shows ``agent: WeatherAgent -> Predict.forward -> LM.__call__``
    instead of a flat list of generic module names.

    Args:
        agent_name: The canvas node's display name for the agent.
        node_id: The agent node UUID, recorded as the ``agent_node_id``
            attribute when provided.
        agent_type: The agent type (``worker`` / ``router``), if known.
        canvas_name: The canvas name, if known.

    Yields:
        The active MLflow span, or ``None`` when tracing is disabled or
        unavailable. Never raises for tracing failures — only exceptions
        raised by the caller's body propagate.
    """
    if not settings.mlflow_enabled:
        yield None
        return

    attributes: dict[str, str] = {}
    if node_id is not None:
        attributes["agent_node_id"] = str(node_id)
    if agent_type:
        attributes["agent_type"] = agent_type
    if canvas_name:
        attributes["canvas_name"] = canvas_name

    try:
        span_cm = mlflow.start_span(
            name=f"agent: {agent_name}",
            span_type=AGENT_SPAN_TYPE,
            attributes=attributes or None,
        )
    except Exception:
        logger.debug(
            "MLflow tracing unavailable; skipping agent span for %s", agent_name
        )
        yield None
        return

    with span_cm as span:
        yield span
