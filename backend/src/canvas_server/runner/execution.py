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
import re
import uuid
from abc import ABC, abstractmethod

from canvas_server.exceptions import (
    LLMConfigurationError,
    RAGEmbeddingError,
)
from canvas_server.runner.config import RunContext


def ensure_plots_in_result(result, text: str) -> str:
    """Scans the trajectory for markdown plot links and appends them if missing.

    When an agent uses the `generate_plot` tool, the tool returns a markdown
    image link pointing to the dynamically generated plot in the database.
    Sometimes, the LLM forgets to include this exact link in its final answer.
    This function searches the ReAct trajectory observations for any plot links
    and forcefully appends them to the final text response if they are absent.

    Args:
        result: The dspy.Prediction result object containing the trajectory.
        text (str): The final extracted text answer from the agent.

    Returns:
        str: The final text answer, with missing plot links appended.
    """
    if not hasattr(result, "trajectory") or not result.trajectory:
        return text

    image_regex = r"!\[.*?\]\(.*?\)"
    links_found = []

    # Check all observations in the ReAct loop trajectory
    for key, val in result.trajectory.items():
        if key.startswith("observation_") and isinstance(val, str):
            matches = re.findall(image_regex, val)
            for m in matches:
                if m not in links_found:
                    links_found.append(m)

    if not links_found:
        return text

    # Append any links that the LLM forgot to copy
    missing_links = [link for link in links_found if link not in text]
    if missing_links:
        text = text.rstrip() + "\n\n" + "\n".join(missing_links)

    return text


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

    # Detect HTTP 401 Unauthorized (auth/budget errors from OpenAI-compatible gateways)
    is_401 = "401" in exc_str or "Unauthorized" in exc_str or "AuthenticationError" in exc_type
    is_403 = "403" in exc_str or "Forbidden" in exc_str
    is_429 = "429" in exc_str or "RateLimitError" in exc_type or "Too Many Requests" in exc_str
    is_503 = "503" in exc_str or "ServiceUnavailable" in exc_type

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
    if is_503:
        return "LLM service unavailable (503). The LLM endpoint may be down or overloaded."

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
        run_state,
        edge_graph,
        memory_manager,
    ):
        self.run_state = run_state
        self.edge_graph = edge_graph
        self.memory_manager = memory_manager

    @property
    def agents(self):
        return self.run_state.agents

    @property
    def node_map(self):
        return self.run_state.node_map

    @property
    def agent_factory(self):
        return self.run_state.agent_factory

    @property
    def conversation_service(self):
        return self.run_state.conversation_service

    @property
    def tool_registry(self):
        return self.run_state.tool_registry

    @property
    def attach_events(self):
        return self.run_state.attach_events

    @property
    def handoff_tool_builder(self):
        return self.run_state.handoff_tool_builder


class ExecutionStrategy(ABC):
    """Base abstract class for all agent execution strategies.

    Strategies define how a specific type of agent (Worker, Router, or Chain)
    should be executed within the context of a run.
    """

    def __init__(self, services: StrategyServices):
        self._services = services

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

    async def _run_worker(
        self,
        agent_id: uuid.UUID,
        user_prompt: str,
        send_event,
        dspy_history,
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

        try:
            if dspy_history is not None and needs_history:
                result = await agent.aforward(
                    user_request=prompt,
                    history=dspy_history,
                    get_client_response=self._services.run_state.get_client_response,
                )
            else:
                result = await agent.aforward(
                    user_request=prompt,
                    get_client_response=self._services.run_state.get_client_response,
                )
            text = result.process_result
            text = ensure_plots_in_result(result, text)
            logger.info("Agent %s completed: result=%s", agent_node.name, text[:200])
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
            agent_id, ctx.user_prompt, ctx.send_event, ctx.dspy_history
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
        try:
            if ctx.dspy_history is not None:
                result = await agent.aforward(
                    user_request=prompt,
                    history=ctx.dspy_history,
                    get_client_response=self._services.run_state.get_client_response,
                )
            else:
                result = await agent.aforward(
                    user_request=prompt,
                    get_client_response=self._services.run_state.get_client_response,
                )
            final_text = result.process_result

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
