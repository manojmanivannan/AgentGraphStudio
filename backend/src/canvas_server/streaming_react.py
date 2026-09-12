import logging
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import dspy
import mlflow
from mlflow.entities import LiveSpan

from canvas_server.config import settings
from canvas_server.events import EventCallback, EventPayload
from canvas_server.exceptions import RunAbortedError

logger = logging.getLogger("canvas_server.streaming_react")

REACT_ITERATION_SPAN_TYPE = "STEP"


@contextmanager
def iteration_span(iteration: int) -> Iterator[LiveSpan | None]:
    """Open a span named ``react: iteration <n>`` around one ReAct iteration.

    DSPy autolog only emits generic span names (``Predict.forward``,
    ``LM.__call__``), so wrapping each ReAct iteration gives the trace a
    readable per-iteration structure.

    Best-effort: yields ``None`` when MLflow is disabled or unavailable and
    never raises for tracing failures — only exceptions raised by the caller's
    body propagate.

    Args:
        iteration: 1-based iteration number within the ReAct loop.
    """
    if not settings.mlflow_enabled:
        yield None
        return

    try:
        span_cm = mlflow.start_span(
            name=f"react: iteration {iteration}",
            span_type=REACT_ITERATION_SPAN_TYPE,
        )
    except Exception:
        logger.debug(
            "MLflow tracing unavailable; skipping ReAct iteration span %d",
            iteration,
        )
        yield None
        return

    with span_cm as span:
        yield span


def set_span_attributes(span: LiveSpan | None, attributes: dict[str, Any]) -> None:
    """Best-effort attribute update on an MLflow span; never raises."""
    if span is None:
        return
    try:
        span.set_attributes(attributes)
    except Exception:
        logger.debug("Failed to set MLflow span attributes", exc_info=True)


class StreamingReAct(dspy.ReAct):
    """A dspy.ReAct subclass that emits events at each iteration of the ReAct loop.

    This class intercepts the internal ReAct loop to stream intermediate steps
    (thoughts, tool starts, tool results) back to the UI in real-time. It also
    handles Human-in-the-Loop (HITL) tool approvals by pausing execution until
    a client response is received.

    Args:
        signature: The DSPy signature defining the inputs and outputs.
        tools: A list of callable tools available to the agent.
        max_iters (int, optional): Maximum number of ReAct loop iterations. Defaults to 10.
    """

    def __init__(
        self,
        signature: type[dspy.Signature],
        tools: list[Callable[..., Any]],
        max_iters: int = 10,
    ) -> None:
        super().__init__(signature, tools, max_iters)
        self._event_callbacks: list[EventCallback] = []

    def on_event(self, callback: EventCallback) -> None:
        """Registers a callback function to receive streaming events.

        Args:
            callback: An async callable that accepts a single dictionary
                representing the event payload.
        """
        self._event_callbacks.append(callback)

    async def _emit(self, event: EventPayload):
        """Emits an event to all registered callbacks.

        Args:
            event (dict): The event payload to emit.

        Raises:
            RunAbortedError: If the run is aborted via the UI.
        """
        for cb in self._event_callbacks:
            try:
                await cb(event)
            except RunAbortedError:
                raise
            except Exception:
                logger.exception("Event callback failed")

    async def aforward(self, **input_args: Any) -> dspy.Prediction:
        """Executes the asynchronous ReAct loop.

        This method overrides the default DSPy `aforward` to inject event emission
        and handle tool approval workflows.

        Args:
            **input_args: Keyword arguments representing the inputs to the agent
                (e.g., user_request, history). `get_client_response` can also be
                passed here to support HITL tool approvals.

        Returns:
            dspy.Prediction: The final prediction containing the result and trajectory.

        Raises:
            RunAbortedError: If the run is cooperatively aborted.
        """
        trajectory = {}
        max_iters = input_args.pop("max_iters", self.max_iters)

        # Extract the client response callback, used to block and wait for UI approval
        get_client_response = input_args.pop("get_client_response", None)

        for idx in range(max_iters):
            with iteration_span(idx + 1) as span:
                pred = await self._async_call_with_potential_trajectory_truncation(
                    self.react, trajectory, **input_args
                )

                trajectory[f"thought_{idx}"] = pred.next_thought
                trajectory[f"tool_name_{idx}"] = pred.next_tool_name
                trajectory[f"tool_args_{idx}"] = pred.next_tool_args

                await self._emit({"type": "thought", "content": pred.next_thought})

                if pred.next_tool_name == "finish":
                    break

                # This iteration invokes a tool — label the span with its name.
                set_span_attributes(span, {"tool": pred.next_tool_name})

                tool_input = pred.next_tool_args if isinstance(pred.next_tool_args, dict) else {}

                await self._emit(
                    {"type": "tool_start", "tool": pred.next_tool_name, "input": tool_input}
                )

                # Check if this tool requires human approval before executing
                tool_obj = self.tools[pred.next_tool_name]
                original_fn = getattr(tool_obj, "func", getattr(tool_obj, "fn", tool_obj))
                requires_approval = getattr(original_fn, "requires_approval", False)
                tool_node_id = getattr(original_fn, "node_id", None)

                approved = True
                if requires_approval and get_client_response:
                    request_id = str(uuid.uuid4())
                    await self._emit({
                        "type": "tool_approval_request",
                        "request_id": request_id,
                        "tool": pred.next_tool_name,
                        "args": pred.next_tool_args,
                        "node_id": str(tool_node_id) if tool_node_id else None,
                    })
                    try:
                        # Block execution and wait for the client to approve or deny via websocket
                        res = await get_client_response(request_id, "tool_approval_response")
                        approved = res.get("approved", False)
                    except RunAbortedError:
                        raise
                    except Exception:
                        approved = False

                if not approved:
                    observation = "Tool execution denied by user."
                    trajectory[f"observation_{idx}"] = observation
                    await self._emit(
                        {
                            "type": "tool_result",
                            "tool": pred.next_tool_name,
                            "input": tool_input,
                            "output": str(observation),
                        }
                    )
                    continue

                try:
                    # Execute the actual tool function
                    observation = await self.tools[pred.next_tool_name].acall(
                        **pred.next_tool_args
                    )
                except RunAbortedError:
                    raise
                except Exception as err:
                    # Catch tool execution failures (e.g. syntax errors, timeouts) and feed them
                    # back to the LLM as an observation so it can attempt to correct the error.
                    observation = f"Execution error in {pred.next_tool_name}: {err}"
                    logger.exception("Tool call failed")

                trajectory[f"observation_{idx}"] = observation

                await self._emit(
                    {
                        "type": "tool_result",
                        "tool": pred.next_tool_name,
                        "input": tool_input,
                        "output": str(observation),
                    }
                )

        # Extract the final answer based on the accumulated trajectory
        extract = await self._async_call_with_potential_trajectory_truncation(
            self.extract, trajectory, **input_args
        )

        return dspy.Prediction(trajectory=trajectory, **extract)
