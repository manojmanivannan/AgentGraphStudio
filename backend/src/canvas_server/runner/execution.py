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

from canvas_server.exceptions import (
    LLMConfigurationError,
    RAGEmbeddingError,
)
from canvas_server.runner.config import RunContext

logger = logging.getLogger("canvas_server.runner.execution")


class StrategyServices:
    """Aggregates all services and runner callbacks needed by execution strategies.

    Populated by ``CanvasRunner`` when it resolves the strategy.
    """

    def __init__(
        self,
        *,
        agents: dict[uuid.UUID, object],
        node_map: dict[uuid.UUID, object],
        agent_factory,
        conversation_service,
        edge_graph,
        memory_manager,
        tool_registry,
        attach_events: Callable[[uuid.UUID, Callable], None],
        make_handoff_tool: Callable,
        make_parallel_handoff_tool: Callable | None = None,
    ):
        self.agents = agents
        self.node_map = node_map
        self.agent_factory = agent_factory
        self.conversation_service = conversation_service
        self.edge_graph = edge_graph
        self.memory_manager = memory_manager
        self.tool_registry = tool_registry
        self.attach_events = attach_events
        self.make_handoff_tool = make_handoff_tool
        self.make_parallel_handoff_tool = make_parallel_handoff_tool


class ExecutionStrategy(ABC):
    """Base class for execution strategies."""

    def __init__(self, services: StrategyServices):
        self._services = services

    @abstractmethod
    async def execute(self, agent_id: uuid.UUID, ctx: RunContext) -> str | None: ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _agent_name(self, agent_id: uuid.UUID) -> str:
        node = self._services.node_map.get(agent_id)
        return node.name if node else "Unknown"

    async def _run_worker(
        self,
        agent_id: uuid.UUID,
        user_prompt: str,
        send_event,
        dspy_history,
    ) -> str | None:
        """Execute a single worker agent and return its answer."""
        agent = self._services.agents.get(agent_id)
        agent_node = self._services.node_map.get(agent_id)
        if not agent or not agent_node:
            logger.warning("Agent not found: id=%s", agent_id)
            return None

        logger.info(
            "Running agent: %s (type=%s)", agent_node.name, agent_node.agent_type
        )

        if getattr(agent_node, "enable_rag", False):
            from canvas_server.runner.rag_helper import run_rag_search
            try:
                passages = await run_rag_search(
                    agent_id,
                    user_prompt
                )
            except Exception as e:
                warn_msg = f"RAG document retrieval failed for agent '{agent_node.name}': {e}"
                logger.warning(warn_msg)
                if send_event:
                    await send_event({
                        "type": "warning",
                        "message": warn_msg
                    })
                await self._services.conversation_service.persist_message(
                    role="system",
                    content=warn_msg,
                    event_type="warning",
                    node_id=agent_id,
                )
                passages = "Here context retrieval failed and you see this line. You are unable to leverage context."

            agent = await self._services.agent_factory.build_worker_with_rag_prompt(agent_node, passages)
            self._services.agents[agent_id] = agent
            self._services.attach_events(agent_id, send_event, force=True)
        else:
            self._services.attach_events(agent_id, send_event)

        needs_history = self._services.agent_factory.needs_history(agent_node)
        prompt = self._services.agent_factory.build_worker_prompt(user_prompt)

        try:
            if dspy_history is not None and needs_history:
                result = await agent.aforward(user_request=prompt, history=dspy_history)
            else:
                result = await agent.aforward(user_request=prompt)
            text = result.process_result
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
            await self._services.conversation_service.persist_message(
                role="system",
                content=f"Error: {e}",
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="error",
            )
            return None

    def _event(self, type_: str, **kwargs) -> dict:
        kwargs["type"] = type_
        return kwargs


class WorkerExecution(ExecutionStrategy):
    """Execute a single worker agent directly."""

    async def execute(self, agent_id: uuid.UUID, ctx: RunContext) -> str | None:
        agent_node = self._services.node_map.get(agent_id)
        if not agent_node:
            logger.warning("Worker agent node not found: id=%s", agent_id)
            return None

        self._services.attach_events(agent_id, ctx.send_event)
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
    """Execute a router agent with handoff tools.

    The router agent is built lazily (it wasn't built during ``setup()``)
    and wired with handoff tools pointing to its sub-agents.
    """

    async def execute(self, agent_id: uuid.UUID, ctx: RunContext) -> str | None:
        agent_node = self._services.node_map.get(agent_id)
        if not agent_node:
            logger.warning("Router agent node not found: id=%s", agent_id)
            return None

        agent = await self._services.agent_factory.build_router(
            agent_node,
            self._services.agents,
            agent_node.name,
            ctx.send_event,
            ctx.history_text,
            ctx.dspy_history,
            self._services.make_handoff_tool,
            self._services.make_parallel_handoff_tool,
        )
        self._services.attach_events(agent_id, ctx.send_event)

        prompt = self._services.agent_factory.build_worker_prompt(
            ctx.user_prompt, ctx.history_text
        )
        try:
            if ctx.dspy_history is not None:
                result = await agent.aforward(
                    user_request=prompt, history=ctx.dspy_history
                )
            else:
                result = await agent.aforward(user_request=prompt)
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
            self._services.attach_events(current_agent_id, ctx.send_event)

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
