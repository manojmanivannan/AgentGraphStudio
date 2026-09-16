"""Execution strategies for the different agent execution modes.

Three strategies, each extracted from the three-way branch in the original
``CanvasRunner.run()``:

* **WorkerExecution** — run a single worker agent (with ``target_agent_id``)
* **RouterExecution** — build and run a router agent that hands off to sub-agents
* **ChainExecution** — legacy sequential chain of workers via handoff edges
  (deprecated — the frontend now always sends ``target_agent_id``)
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import dspy

from canvas_server.exceptions import (
    AttachmentTooLargeError,
    LLMConfigurationError,
    RAGEmbeddingError,
)
from canvas_server.output_extraction import (
    declared_output_nodes,
    extract_output_attachments,
    file_type_to_format,
)
from canvas_server.runner.attachment_events import announce_attachment_produced
from canvas_server.runner.config import RunContext
from canvas_server.runner.input_attachment_delivery import (
    deliver_and_announce_input_attachments,
)
from canvas_server.runner.sandbox_output_capture import read_sandbox_file
from canvas_server.runner.tracing import agent_span
from canvas_server.sandbox import NETWORK_POOL_DEFAULT, NETWORK_POOL_NETWORKED

if TYPE_CHECKING:
    from canvas_server.models.canvas import AgentNode
    from canvas_server.runner.agent_factory import AgentFactory
    from canvas_server.runner.conversation import ConversationService
    from canvas_server.runner.edge_graph import EdgeGraph
    from canvas_server.runner.handoff import HandoffToolBuilder
    from canvas_server.runner.memory import MemoryManager
    from canvas_server.runner.run_state import CanvasRunState
    from canvas_server.runner.tool_registry import ToolRegistry
    from canvas_server.streaming_react import StreamingReAct


def _friendly_error_message(exc: Exception) -> str:
    """Returns a human-readable error message for common LLM or network failures.

    Translates cryptic HTTP status codes and API provider exceptions (e.g. OpenAI,
    Ollama) into actionable advice for the user in the UI.

    Args:
        exc (Exception): The exception that was caught during agent execution.

    Returns:
        str: A friendly error string to display in the chat interface.
    """
    exc_str = str(exc)
    exc_type = type(exc).__name__

    # Detect HTTP status codes and provider exceptions from OpenAI-compatible
    # gateways (OpenRouter, LiteLLM proxies, etc.)
    is_401 = "401" in exc_str or "Unauthorized" in exc_str or "AuthenticationError" in exc_type
    is_403 = "403" in exc_str or "Forbidden" in exc_str
    is_429 = "429" in exc_str or "RateLimitError" in exc_type or "Too Many Requests" in exc_str
    # 502 is checked before 500: gateways like OpenRouter wrap an upstream
    # provider's 500 (e.g. Google AI Studio INTERNAL) inside a 502 response.
    is_502 = "502" in exc_str or "Bad Gateway" in exc_str
    is_500 = "500" in exc_str or "InternalServerError" in exc_type or "Internal error" in exc_str
    is_504 = "504" in exc_str or "Gateway Timeout" in exc_str
    is_503 = "503" in exc_str or "ServiceUnavailable" in exc_type
    is_connection = (
        "APIConnectionError" in exc_type
        or "Connection error" in exc_str
        or "Connection reset" in exc_str
        or "connection refused" in exc_str.lower()
    )

    if is_401:
        return (
            "LLM access unauthorized (401). "
            "Your API key may be invalid, expired, or over budget. "
            "Please check your LLM credentials and budget."
        )
    if is_403:
        return (
            "LLM access forbidden (403). "
            "You may not have permission to use this model or endpoint."
        )
    if is_429:
        return "LLM rate limit exceeded (429). Please wait a moment and try again."
    if is_502:
        return (
            "LLM provider returned a bad gateway (502). "
            "The upstream provider may be temporarily down or overloaded. "
            "Please try again in a moment."
        )
    if is_500:
        return "LLM provider hit an internal error (500). Please try again in a moment."
    if is_504:
        return "LLM request timed out (504 Gateway Timeout). Please try again in a moment."
    if is_503:
        return "LLM service unavailable (503). The LLM endpoint may be down or overloaded."
    if is_connection:
        return (
            "Could not connect to the LLM endpoint. "
            "Check that the provider URL is reachable and try again."
        )
    # Any other LLM API error: never echo raw provider JSON to the chat UI.
    if "APIError" in exc_type or '{"error"' in exc_str:
        return (
            "LLM provider returned an unexpected error. "
            "Please verify your provider settings in Settings or try again later."
        )

    # Truncate very long messages to avoid flooding the UI
    if len(exc_str) > 400:
        exc_str = exc_str[:400] + "..."
    return exc_str

logger = logging.getLogger("canvas_server.runner.execution")


class StrategyServices:
    """Aggregates all services and runner callbacks needed by execution strategies.

    This acts as a dependency injection container passed to strategies, preventing
    the need to pass a large number of individual arguments. It is populated by
    the ``CanvasRunner`` when resolving the execution strategy.

    Args:
        run_state: The current CanvasRunState holding mutable execution context.
        edge_graph: The EdgeGraph instance for navigating node connections.
        memory_manager: The MemoryManager handling mem0 lifecycle and providers.
    """

    def __init__(
        self,
        run_state: CanvasRunState,
        edge_graph: EdgeGraph,
        memory_manager: MemoryManager,
    ) -> None:
        self.run_state: CanvasRunState = run_state
        self.edge_graph: EdgeGraph = edge_graph
        self.memory_manager: MemoryManager = memory_manager

    @property
    def agents(self) -> dict[uuid.UUID, StreamingReAct]:
        return self.run_state.agents

    @property
    def node_map(self) -> dict[uuid.UUID, AgentNode]:
        return self.run_state.node_map

    @property
    def agent_factory(self) -> AgentFactory:
        return self.run_state.agent_factory

    @property
    def conversation_service(self) -> ConversationService:
        return self.run_state.conversation_service

    @property
    def tool_registry(self) -> ToolRegistry:
        return self.run_state.tool_registry

    @property
    def attach_events(self) -> Callable[[uuid.UUID, bool], None]:
        return self.run_state.attach_events

    @property
    def handoff_tool_builder(self) -> HandoffToolBuilder | None:
        return self.run_state.handoff_tool_builder


class ExecutionStrategy(ABC):
    """Base abstract class for all agent execution strategies.

    Strategies define how a specific type of agent (Worker, Router, or Chain)
    should be executed within the context of a run.
    """

    def __init__(self, services: StrategyServices) -> None:
        self._services: StrategyServices = services

    @abstractmethod
    async def execute(self, agent_id: uuid.UUID, ctx: RunContext) -> str | None:
        """Executes the strategy for the given agent.

        Args:
            agent_id (uuid.UUID): The UUID of the agent to execute.
            ctx (RunContext): The contextual state for the current run.

        Returns:
            str | None: The final text answer generated by the agent, or None
                if the execution failed.
        """
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _agent_name(self, agent_id: uuid.UUID) -> str:
        """Helper to resolve an agent's display name from its ID."""
        node = self._services.node_map.get(agent_id)
        return node.name if node else "Unknown"

    async def _store_output_attachments(
        self,
        result: dspy.Prediction,
        agent_node: AgentNode,
        agent_id: uuid.UUID,
        send_event,
        run_id: uuid.UUID | None,
    ) -> None:
        """Validates and stores any ``output_attachments`` the agent emitted (#86).

        Runs once, post-loop, right after the ReAct loop's ``extract()`` step
        resolves ``result`` — never per-iteration. A mismatch against the
        agent's declared output Attachment node(s) is surfaced as a
        tool-output-style ``warning`` event (and a durable system message, so
        it lands in conversation history for the agent to react to on a
        subsequent turn) and skipped — this must never fail an otherwise-
        successful run. Nothing happens when the agent has no declared output
        nodes, even if the LM filled in ``output_attachments`` (the signature
        only gains that field when at least one output node is wired, but
        this stays defensive).
        """
        raw_items = getattr(result, "output_attachments", None)
        if not raw_items:
            return

        canvas = getattr(self._services.run_state, "canvas", None)
        edges = getattr(canvas, "edges", None) or []
        attachment_nodes = getattr(canvas, "attachment_nodes", None) or []
        declared_nodes = declared_output_nodes(edges, attachment_nodes, agent_id)
        if not declared_nodes:
            return

        conversation_service = self._services.conversation_service

        outcome = extract_output_attachments(raw_items, declared_nodes)
        for error in outcome.errors:
            await self._emit_output_attachment_warning(
                error=error,
                agent_node=agent_node,
                agent_id=agent_id,
                send_event=send_event,
                conversation_service=conversation_service,
            )

        if not outcome.attachments:
            return

        conversation_repo = getattr(conversation_service, "conversation_repo", None)
        conversation_id = getattr(conversation_service, "conversation_id", None)
        if not conversation_repo or not conversation_id:
            return

        network_pool = (
            NETWORK_POOL_NETWORKED
            if getattr(agent_node, "enable_network", False)
            else NETWORK_POOL_DEFAULT
        )

        for attachment in outcome.attachments:
            content = attachment.content.encode("utf-8")
            if attachment.sandbox_path is not None:
                sandbox_bytes = await read_sandbox_file(
                    conversation_id=conversation_id,
                    network_pool=network_pool,
                    path=attachment.sandbox_path,
                )
                if sandbox_bytes is None:
                    warning = (
                        "Execution error in output_attachments: "
                        f"{attachment.name!r} referenced sandbox file "
                        f"{attachment.sandbox_path!r}, but the framework could not read it "
                        "from the agent sandbox."
                    )
                    await self._emit_output_attachment_warning(
                        error=warning,
                        agent_node=agent_node,
                        agent_id=agent_id,
                        send_event=send_event,
                        conversation_service=conversation_service,
                    )
                    continue
                content = sandbox_bytes

            try:
                stored = await conversation_repo.save_attachment(
                    conversation_id=conversation_id,
                    content=content,
                    format=file_type_to_format(attachment.file_type),
                    file_type=attachment.file_type,
                    source="agent_output",
                    attachment_node_id=attachment.node_id,
                    produced_by_run_id=run_id,
                )
            except AttachmentTooLargeError as exc:
                logger.warning(
                    "Agent %s: output attachment %r too large to store: %s",
                    agent_node.name,
                    attachment.name,
                    exc,
                )
                continue

            await announce_attachment_produced(
                send_event=send_event,
                conversation_service=conversation_service,
                agent_name=agent_node.name,
                agent_id=agent_id,
                attachment_id=stored.id,
                name=attachment.name,
                file_type=attachment.file_type,
                source="agent_output",
                conversation_id=conversation_id,
                run_id=run_id,
            )

    async def _emit_output_attachment_warning(
        self,
        *,
        error: str,
        agent_node: AgentNode,
        agent_id: uuid.UUID,
        send_event,
        conversation_service,
    ) -> None:
        """Emit/persist a non-fatal output-attachment warning (#86/#89)."""
        logger.warning("Agent %s: %s", agent_node.name, error)
        await send_event(
            self._event(
                "warning",
                message=error,
                agent=agent_node.name,
                node_id=str(agent_id),
            )
        )
        if conversation_service:
            await conversation_service.persist_message(
                role="system",
                content=error,
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="warning",
            )

    async def _run_worker(
        self,
        agent_id: uuid.UUID,
        user_prompt: str,
        send_event,
        dspy_history,
        run_id: uuid.UUID | None = None,
    ) -> str | None:
        """Executes a single worker agent and returns its answer.

        This method handles:
        1. Retrieving/building the agent instance.
        2. Constructing the prompt with optional history.
        3. Executing the DSPy ReAct loop.
        4. Handling exceptions and translating them into friendly errors.
        5. Persisting the final result to the conversation.

        Args:
            agent_id (uuid.UUID): The UUID of the worker agent.
            user_prompt (str): The raw prompt input from the user.
            send_event (Callable): Callback for dispatching websocket events.
            dspy_history: The DSPy history object, if conversation history is enabled.
            run_id (uuid.UUID | None): The durable run producing this turn, if any —
                threaded through to any stored ``AttachmentInstance`` (#86).

        Returns:
            str | None: The final text response, or None on failure.
        """
        agent_node = self._services.node_map.get(agent_id)
        if not agent_node:
            logger.warning("Agent node not found: id=%s", agent_id)
            return None

        logger.info(
            "Running agent: %s (type=%s)", agent_node.name, agent_node.agent_type
        )

        # Delegate RAG compilation, caching, and event callbacks to run_state
        agent = await self._services.run_state.get_or_build_agent(agent_id, task=user_prompt)

        needs_history = self._services.agent_factory.needs_history(agent_node)
        prompt = self._services.agent_factory.build_worker_prompt(user_prompt)
        canvas_name = getattr(
            getattr(self._services.run_state, "canvas", None), "name", None
        )

        # Resolve/materialize any declared input attachments before the loop
        # starts (#88). ``_run_worker`` is always an entry-point call site
        # (WorkerExecution, ChainExecution) which never otherwise emits
        # ``agent_start`` — so it's emitted here, but only when there's an
        # actual attachment to report this turn.
        prompt, attachment_kwargs = await self._deliver_input_attachments(
            agent_node, agent_id, prompt, send_event, run_id, emit_agent_start=True
        )

        try:
            # Name the MLflow span after the real agent so DSPy autolog's
            # generic ``Predict.forward`` / ``LM.__call__`` spans nest under
            # a readable parent. Tracing is best-effort and never raises.
            with agent_span(
                agent_node.name,
                node_id=agent_id,
                agent_type=getattr(agent_node, "agent_type", None),
                canvas_name=canvas_name,
            ):
                if dspy_history is not None and needs_history:
                    result = await agent.aforward(
                        user_request=prompt,
                        history=dspy_history,
                        get_client_response=self._services.run_state.get_client_response,
                        **attachment_kwargs,
                    )
                else:
                    result = await agent.aforward(
                        user_request=prompt,
                        get_client_response=self._services.run_state.get_client_response,
                        **attachment_kwargs,
                    )
            text = result.process_result
            logger.info("Agent %s completed: result=%s", agent_node.name, text[:200])
            await self._store_output_attachments(result, agent_node, agent_id, send_event, run_id)
            await self._services.conversation_service.persist_message(
                role="assistant",
                content=text,
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="final_answer",
            )
            return text
        except (LLMConfigurationError, RAGEmbeddingError) as e:
            logger.error("Agent %s failed with terminal exception: %s", agent_node.name, e)
            raise
        except Exception as e:
            logger.error("Agent %s failed: %s", agent_node.name, e, exc_info=True)
            friendly_msg = _friendly_error_message(e)
            await self._services.conversation_service.persist_message(
                role="assistant",
                content=friendly_msg,
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="final_answer",
            )
            await send_event(
                self._event(
                    "final_answer",
                    content=friendly_msg,
                    agent=agent_node.name,
                    node_id=str(agent_id),
                )
            )
            return None

    async def _deliver_input_attachments(
        self,
        agent_node: AgentNode,
        agent_id: uuid.UUID,
        user_prompt: str,
        send_event,
        run_id: uuid.UUID | None,
        *,
        emit_agent_start: bool,
    ) -> tuple[str, dict[str, Any]]:
        """Resolves/materializes this agent's declared input attachments (#88).

        Runs once, right before the ReAct loop starts. A no-op (returns
        ``user_prompt`` unchanged, no extra kwargs) when the agent has no
        declared input Attachment node(s), or nothing unconsumed is waiting —
        this is what keeps entry-point paths (which normally never emit
        ``agent_start``) from emitting it on every ordinary turn.

        When ``emit_agent_start`` is True and there IS something to deliver,
        emits ``agent_start`` immediately before the ``attachment_consumed``
        announcement(s) — entry-point paths (``_run_worker``,
        ``RouterExecution.execute``) currently never emit ``agent_start``
        themselves, so this is the only place they do. Handoff-delegated
        sub-agents (``handoff.py``) already emit ``agent_start``
        unconditionally and call ``deliver_and_announce_input_attachments``
        directly with ``emit_agent_start=False`` to avoid a duplicate — see
        that shared function for the resolve → emit → announce → augment
        shape both call sites use.

        Returns:
            tuple[str, dict[str, Any]]: The (possibly attachment-augmented)
            prompt, and any extra ``aforward`` kwargs (``attachment_image``
            when an image attachment was resolved).
        """
        canvas = getattr(self._services.run_state, "canvas", None)
        conversation_service = self._services.conversation_service
        conversation_repo = getattr(conversation_service, "conversation_repo", None)
        conversation_id = getattr(conversation_service, "conversation_id", None)
        if canvas is None or conversation_repo is None or conversation_id is None:
            return user_prompt, {}

        return await deliver_and_announce_input_attachments(
            agent_node=agent_node,
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=conversation_id,
            conversation_service=conversation_service,
            send_event=send_event,
            run_id=run_id,
            user_prompt=user_prompt,
            emit_agent_start=emit_agent_start,
        )

    def _event(self, type_: str, **kwargs) -> dict:
        kwargs["type"] = type_
        return kwargs


class WorkerExecution(ExecutionStrategy):
    """Execution strategy for a single standalone Worker agent.

    This strategy simply executes the targeted worker agent and streams its
    final output to the client. Workers execute specialized tasks and do not
    delegate to other agents.
    """

    async def execute(self, agent_id: uuid.UUID, ctx: RunContext) -> str | None:
        agent_node = self._services.node_map.get(agent_id)
        if not agent_node:
            logger.warning("Worker agent node not found: id=%s", agent_id)
            return None

        result = await self._run_worker(
            agent_id, ctx.user_prompt, ctx.send_event, ctx.dspy_history, ctx.run_id
        )
        if result is not None:
            await ctx.send_event(
                self._event(
                    "final_answer",
                    agent=agent_node.name,
                    content=result,
                    node_id=str(agent_id),
                )
            )
        return result


class RouterExecution(ExecutionStrategy):
    """Execution strategy for a Router agent.

    A Router orchestrates work by delegating (handing off) tasks to its
    connected sub-agents via automatically injected handoff tools.

    Because handoff tools require dynamic run context (like `send_event`),
    router agents cannot be eagerly built during the runner setup phase.
    Instead, they are built lazily at runtime by `CanvasRunState.get_or_build_agent()`
    just before execution.
    """

    async def execute(self, agent_id: uuid.UUID, ctx: RunContext) -> str | None:
        agent_node = self._services.node_map.get(agent_id)
        if not agent_node:
            logger.warning("Router agent node not found: id=%s", agent_id)
            return None

        # CanvasRunState handles lazy building and event wiring for routers
        agent = await self._services.run_state.get_or_build_agent(agent_id)

        prompt = self._services.agent_factory.build_worker_prompt(
            ctx.user_prompt, ctx.history_text
        )
        canvas_name = getattr(
            getattr(self._services.run_state, "canvas", None), "name", None
        )

        # Resolve/materialize any declared input attachments before the loop
        # starts (#88). A directly-targeted router is also an entry point
        # that never otherwise emits ``agent_start`` — emitted here only
        # when there's an actual attachment to report this turn.
        prompt, attachment_kwargs = await self._deliver_input_attachments(
            agent_node, agent_id, prompt, ctx.send_event, ctx.run_id, emit_agent_start=True
        )
        try:
            with agent_span(
                agent_node.name,
                node_id=agent_id,
                agent_type=getattr(agent_node, "agent_type", None),
                canvas_name=canvas_name,
            ):
                if ctx.dspy_history is not None:
                    result = await agent.aforward(
                        user_request=prompt,
                        history=ctx.dspy_history,
                        get_client_response=self._services.run_state.get_client_response,
                        **attachment_kwargs,
                    )
                else:
                    result = await agent.aforward(
                        user_request=prompt,
                        get_client_response=self._services.run_state.get_client_response,
                        **attachment_kwargs,
                    )
            final_text = result.process_result

            await self._store_output_attachments(
                result, agent_node, agent_id, ctx.send_event, ctx.run_id
            )
            await self._services.conversation_service.persist_message(
                role="assistant",
                content=final_text,
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="final_answer",
            )
            await ctx.send_event(
                self._event(
                    "final_answer",
                    agent=agent_node.name,
                    content=final_text,
                    node_id=str(agent_id),
                )
            )
            return final_text
        except (LLMConfigurationError, RAGEmbeddingError) as e:
            logger.error("Router agent %s failed with terminal exception: %s", agent_node.name, e)
            raise
        except Exception as e:
            logger.error(
                "Router agent %s failed: %s", agent_node.name, e, exc_info=True
            )
            friendly_msg = _friendly_error_message(e)
            await self._services.conversation_service.persist_message(
                role="assistant",
                content=friendly_msg,
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="final_answer",
            )
            await ctx.send_event(
                self._event(
                    "final_answer",
                    content=friendly_msg,
                    agent=agent_node.name,
                    node_id=str(agent_id),
                )
            )
            return None


class ChainExecution(ExecutionStrategy):
    """Legacy sequential worker chain via handoff edges.

    .. deprecated::
       The frontend now always sends ``target_agent_id``.  This strategy
       exists only for backward compatibility with graphs that use sequential
       handoff chains without an explicit target.
    """

    async def execute(self, agent_id: uuid.UUID, ctx: RunContext) -> str | None:
        agent_ids = [n.id for n in self._services.node_map.values()]
        if not agent_ids:
            return None

        handoff_map = self._services.edge_graph.build_handoff_map(agent_ids)
        current_agent_id = agent_id
        visited: set[uuid.UUID] = set()
        final_text = None

        while current_agent_id is not None and current_agent_id not in visited:
            visited.add(current_agent_id)
            result_text = await self._run_worker(
                current_agent_id,
                ctx.user_prompt,
                ctx.send_event,
                ctx.dspy_history,
                ctx.run_id,
            )
            if result_text is None:
                break

            final_text = result_text
            await ctx.send_event(
                self._event(
                    "final_answer",
                    agent=self._agent_name(current_agent_id),
                    content=result_text,
                    node_id=str(current_agent_id),
                )
            )

            handoff_targets = handoff_map.get(current_agent_id, [])
            next_agent_id = handoff_targets[0] if handoff_targets else None

            if next_agent_id and next_agent_id != current_agent_id:
                next_name = self._agent_name(next_agent_id)
                logger.info(
                    "Handoff: %s -> %s",
                    self._agent_name(current_agent_id),
                    next_name,
                )
                await ctx.send_event(
                    {
                        "type": "handoff",
                        "from": self._agent_name(current_agent_id),
                        "to": next_name,
                        "node_id": str(next_agent_id),
                    }
                )

            current_agent_id = next_agent_id

        return final_text
