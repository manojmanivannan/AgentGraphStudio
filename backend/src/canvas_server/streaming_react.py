import logging
import uuid

import dspy

from canvas_server.exceptions import RunAbortedError

logger = logging.getLogger("canvas_server.streaming_react")


class StreamingReAct(dspy.ReAct):
    """A dspy.ReAct subclass that emits events at each iteration of the ReAct loop.

    Register callbacks via ``on_event(callback)`` where the callback is an async
    callable accepting a single dict argument.
    """

    def __init__(self, signature, tools, max_iters=10):
        super().__init__(signature, tools, max_iters)
        self._event_callbacks = []

    def on_event(self, callback):
        self._event_callbacks.append(callback)

    async def _emit(self, event: dict):
        for cb in self._event_callbacks:
            try:
                await cb(event)
            except RunAbortedError:
                raise
            except Exception:
                logger.exception("Event callback failed")

    async def aforward(self, **input_args):
        trajectory = {}
        max_iters = input_args.pop("max_iters", self.max_iters)
        get_client_response = input_args.pop("get_client_response", None)

        for idx in range(max_iters):
            pred = await self._async_call_with_potential_trajectory_truncation(
                self.react, trajectory, **input_args
            )

            trajectory[f"thought_{idx}"] = pred.next_thought
            trajectory[f"tool_name_{idx}"] = pred.next_tool_name
            trajectory[f"tool_args_{idx}"] = pred.next_tool_args

            await self._emit({"type": "thought", "content": pred.next_thought})

            if pred.next_tool_name == "finish":
                break

            await self._emit(
                {"type": "tool_start", "tool": pred.next_tool_name}
            )

            # Check if this tool requires approval
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
                        "output": str(observation),
                    }
                )
                continue

            try:
                observation = await self.tools[pred.next_tool_name].acall(
                    **pred.next_tool_args
                )
            except RunAbortedError:
                raise
            except Exception as err:
                observation = f"Execution error in {pred.next_tool_name}: {err}"
                logger.exception("Tool call failed")

            trajectory[f"observation_{idx}"] = observation

            await self._emit(
                {
                    "type": "tool_result",
                    "tool": pred.next_tool_name,
                    "output": str(observation),
                }
            )

        extract = await self._async_call_with_potential_trajectory_truncation(
            self.extract, trajectory, **input_args
        )

        return dspy.Prediction(trajectory=trajectory, **extract)
