"""CanvasRunner — the core orchestrator for canvas-based agent execution.

After the big modularisation, ``CanvasRunner`` is a thin orchestrator that:
  * Owns shared mutable state (agent instances, node map, event wiring set).
  * Delegates domain work to extracted services:
      - ``ToolRegistry`` — compiles tools, maps name→id
      - ``EdgeGraph`` — navigates the canvas edge graph
      - ``MemoryManager`` — shared mem0 lifecycle, per-agent providers
      - ``ConversationService`` — message persistence and history formatting
      - ``AgentFactory`` — builds StreamingReAct agents
      - ``ExecutionStrategy`` (Router/Worker/Chain)
"""

from __future__ import annotations

import logging
import uuid

import dspy
import mlflow

from canvas_server.config import settings
from canvas_server.runner.agent_factory import AgentFactory
from canvas_server.runner.config import RunContext
from canvas_server.runner.conversation import ConversationService
from canvas_server.runner.edge_graph import EdgeGraph
from canvas_server.runner.execution import (
    ChainExecution,
    ExecutionStrategy,
    RouterExecution,
    StrategyServices,
    WorkerExecution,
)
from canvas_server.runner.memory import MemoryManager
from canvas_server.runner.tool_registry import ToolRegistry

logger = logging.getLogger("canvas_server.runner")


class CanvasRunner:
    """Orchestrates a canvas execution run.

    All services are created during ``__init__`` (they are lightweight wrappers).
    ``setup()`` performs the actual work: compiling tools, building worker
    agents.  This lets tests mock ``setup()`` and inject state directly.
    """

    def __init__(self, canvas, conversation_repo=None, conversation_id=None):
        self.canvas = canvas

        # ---- mutable run-time state (owned here, shared with services) ----
        self.tools: dict[uuid.UUID, object] = {}
        self._tool_name_to_id: dict[str, uuid.UUID] = {}
        self.agents: dict[uuid.UUID, object] = {}
        self._wired_agents: set[uuid.UUID] = set()
        self.node_map: dict[uuid.UUID, object] = {}

        # ---- LM (cheap to construct, needs no I/O) ----
        self._lm = dspy.LM(
            settings.llm_model, api_base=settings.llm_base_url, api_key=""
        )

        # ---- services ----
        self._tool_registry = ToolRegistry()
        self._edge_graph = EdgeGraph(self.canvas.edges if self.canvas else [])
        self._memory_manager = MemoryManager()
        self._conversation = ConversationService(
            conversation_repo=conversation_repo,
            conversation_id=conversation_id,
        )
        self._agent_factory = AgentFactory(
            lm=self._lm,
            tool_registry=self._tool_registry,
            memory_manager=self._memory_manager,
            edges=self.canvas.edges if self.canvas else [],
        )

    # -- backward-compat properties so existing tests don't break ----------

    @property
    def conversation_repo(self):
        return self._conversation.conversation_repo

    @conversation_repo.setter
    def conversation_repo(self, value):
        self._conversation.conversation_repo = value

    @property
    def conversation_id(self):
        return self._conversation.conversation_id

    @conversation_id.setter
    def conversation_id(self, value):
        self._conversation.conversation_id = value

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def setup(self):
        """Initialise all services and build worker agents.

        Called at the start of every ``run()``.  Idempotent-ish: if a
        previous ``setup()`` already built tools and workers, building again
        is cheap (but currently we always re-build).
        """
        logger.info("Setting up canvas runner")

        # Build the node map for fast lookups
        for node in self.canvas.agent_nodes:
            self.node_map[node.id] = node

        self._tool_registry = ToolRegistry()
        await self._tool_registry.compile_all(self.canvas.tool_nodes)
        # Sync tool state up to the runner for backward-compat access
        self.tools = self._tool_registry.tools
        self._tool_name_to_id = self._tool_registry._tool_name_to_id

        self._edge_graph = EdgeGraph(self.canvas.edges)
        self._memory_manager = MemoryManager()
        self._agent_factory = AgentFactory(
            lm=self._lm,
            tool_registry=self._tool_registry,
            memory_manager=self._memory_manager,
            edges=self.canvas.edges,
        )

        # Build worker agents (routers are built lazily at run time)
        self.agents = await self._agent_factory.build_workers(
            self.canvas.agent_nodes
        )

        logger.info(
            "Setup complete: %d tools, %d agents",
            len(self.tools), len(self.agents),
        )

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def _attach_events(self, agent_id: uuid.UUID, send_event):
        """Wire event callbacks on *agent_id* so StreamingReAct events flow
        to ``send_event``.  Idempotent — agents are only wired once."""
        if agent_id in self._wired_agents:
            return
        agent = self.agents.get(agent_id)
        agent_node = self.node_map.get(agent_id)
        if agent and agent_node:
            self._wired_agents.add(agent_id)
            tool_name_to_id = self._tool_name_to_id

            async def callback(event, aid=agent_id, aname=agent_node.name):
                await send_event({"agent": aname, "node_id": str(aid), **event})
                if event.get("type") == "tool_start":
                    tool_name = event.get("tool", "")
                    tool_node_id = tool_name_to_id.get(tool_name)
                    if tool_node_id:
                        await send_event(
                            {
                                "type": "tool_start",
                                "tool": tool_name,
                                "node_id": str(tool_node_id),
                            }
                        )

            agent.on_event(callback)

    # ------------------------------------------------------------------
    # Handoff tool builder
    # ------------------------------------------------------------------

    def _make_handoff_tool(
        self,
        target_id: uuid.UUID,
        router_name: str,
        send_event,
        history: str,
        dspy_history=None,
    ):
        """Create a DSPy tool function that delegates to a sub-agent.

        The target agent lookup is deferred to call time so that router→router
        handoffs work: router agents are built lazily when first invoked.
        """
        target_node = self.node_map[target_id]
        target_name = target_node.name

        async def transfer(task: str) -> str:
            # Lazily build the target agent if it hasn't been built yet
            if target_id not in self.agents:
                if target_node.agent_type == "router":
                    await self._agent_factory.build_router(
                        target_node,
                        self.agents,
                        router_name,
                        send_event,
                        history,
                        dspy_history,
                        self._make_handoff_tool,
                    )
                else:
                    raise RuntimeError(
                        f"Worker agent '{target_name}' (id={target_id}) not found in agents dict"
                    )

            target_agent = self.agents[target_id]

            await send_event({
                "type": "handoff",
                "from": router_name,
                "to": target_name,
                "node_id": str(target_id),
            })
            await send_event({
                "type": "agent_start",
                "agent": target_name,
                "agentType": target_node.agent_type,
                "node_id": str(target_id),
            })

            self._attach_events(target_id, send_event)
            prompt = self._agent_factory.build_worker_prompt(task, history)
            try:
                needs_history = self._agent_factory.needs_history(target_node)
                if dspy_history is not None and needs_history:
                    result = await target_agent.aforward(
                        user_request=prompt, history=dspy_history
                    )
                else:
                    result = await target_agent.aforward(user_request=prompt)
                answer = result.process_result
            except Exception as e:
                answer = f"Error: {e}"
                logger.error("Sub-agent %s failed: %s", target_name, e, exc_info=True)

            await self._conversation.persist_message(
                role="assistant",
                content=answer,
                agent_name=target_name,
                node_id=target_id,
                event_type="final_answer",
            )
            return answer

        transfer.__name__ = f"transfer_to_{target_name}"
        transfer.__doc__ = (
            f"Route the user request to {target_name}, who handles: "
            f"{target_node.role or target_name}"
        )
        return transfer

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def _event(self, type_: str, **kwargs) -> dict:
        kwargs["type"] = type_
        return kwargs

    def _resolve_strategy(self, target_agent_id) -> ExecutionStrategy:
        """Build the appropriate execution strategy from the services context."""
        services = StrategyServices(
            agents=self.agents,
            node_map=self.node_map,
            agent_factory=self._agent_factory,
            conversation_service=self._conversation,
            edge_graph=self._edge_graph,
            memory_manager=self._memory_manager,
            tool_registry=self._tool_registry,
            attach_events=self._attach_events,
            make_handoff_tool=self._make_handoff_tool,
        )

        if target_agent_id is not None:
            agent_node = self.node_map.get(target_agent_id)
            if agent_node and agent_node.agent_type == "router":
                return RouterExecution(services)
            return WorkerExecution(services)

        # No target agent: use the legacy chain strategy
        return ChainExecution(services)

    @mlflow.trace(
        name="canvas_run", span_type="CHAIN", attributes={"component": "agent"}
    )
    async def run(
        self,
        user_prompt: str,
        send_event,
        target_agent_id: uuid.UUID | None = None,
    ) -> str | None:
        logger.info(
            "Starting canvas execution: canvas_id=%s prompt=%s target=%s",
            self.canvas.id,
            user_prompt[:100],
            str(target_agent_id) if target_agent_id else "auto",
        )
        await self.setup()

        if not self.canvas.agent_nodes:
            logger.error("Canvas has no agent nodes")
            await send_event(
                self._event("error", message="Canvas has no agents to run.")
            )
            return None

        await send_event(self._event("run_start", canvas_id=str(self.canvas.id)))

        # ---- Load conversation history ----
        history_messages = await self._conversation.load_messages()
        agent_ids = [n.id for n in self.canvas.agent_nodes]

        first_agent_id = (
            target_agent_id
            if target_agent_id
            else (agent_ids[0] if agent_ids else None)
        )

        history_enabled_node_ids = {
            n.id for n in self.canvas.agent_nodes
            if self._agent_factory.needs_history(n)
        }

        await self._conversation.persist_message(
            role="user",
            content=user_prompt,
            event_type="run_start",
        )

        history_text, dspy_history = self._conversation.build_conversation_history_context(
            history_messages, history_enabled_node_ids
        )

        ctx = RunContext(
            user_prompt=user_prompt,
            send_event=send_event,
            target_agent_id=target_agent_id,
            history_text=history_text,
            dspy_history=dspy_history,
            history_enabled_node_ids=history_enabled_node_ids,
            primary_agent_id=first_agent_id,
        )

        # ---- Execute ---
        strategy = self._resolve_strategy(target_agent_id)
        first_id = (
            target_agent_id
            if target_agent_id
            else (agent_ids[0] if agent_ids else None)
        )

        final_text = None
        with dspy.context(lm=self._lm):
            final_text = await strategy.execute(first_id, ctx)

        # ---- Append turn to dspy.History ----
        if dspy_history is not None and final_text:
            dspy_history.messages.append(
                {"user_request": user_prompt, "process_result": final_text}
            )

        # ---- Auto-store memory for the primary agent ----
        if final_text:
            primary_id = target_agent_id if target_agent_id else (agent_ids[0] if agent_ids else None)
            primary_node = self.node_map.get(primary_id) if primary_id else None
            if primary_node and self._memory_manager.needs_memory(primary_node):
                mp = self._memory_manager.get_provider(primary_id)
                if mp:
                    try:
                        await mp.store_memory(
                            f"The user asked: '{user_prompt}' → Response: {final_text[:500]}"
                        )
                    except Exception as e:
                        logger.warning("Failed to auto-store memory: %s", e)

        logger.info("Canvas execution completed: canvas_id=%s", self.canvas.id)
        await send_event(
            self._event("run_complete", result="Workflow execution completed.")
        )
        return final_text