"""AgentFactory — builds worker and router StreamingReAct agents."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import dspy

from canvas_server.streaming_react import StreamingReAct
from canvas_server.runner.plot_provider import PlotProvider

if TYPE_CHECKING:
    from canvas_server.runner.handoff import HandoffToolBuilder

logger = logging.getLogger("canvas_server.runner.agent_factory")


class AgentFactory:
    """Creates ``StreamingReAct`` agent instances for the canvas.

    **Worker agents** are built eagerly during ``build_workers()`` (called from
    ``setup()``).  **Router agents** are built lazily via ``build_router()`` at
    run time because they need ``send_event`` and ``history`` which aren't
    available during setup.

    The factory does **not** own the agent dict — agents are returned to the
    caller (``CanvasRunner``) which stores them.  This keeps the factory
    stateless and testable.
    """

    def __init__(
        self,
        lm: dspy.LM,
        tool_registry,
        memory_manager,
        edges: list,
        agent_names: dict[uuid.UUID, str] | None = None,
        conversation_id: str | None = None,
    ):
        self._lm = lm
        self._tool_registry = tool_registry
        self._memory_manager = memory_manager
        self._edges = edges
        self._agent_names = agent_names or {}
        self._conversation_id = conversation_id

    # ------------------------------------------------------------------
    # DSPy signature
    # ------------------------------------------------------------------

    def build_signature(self, agent_node, passages: str | None = None) -> type[dspy.Signature]:
        """Dynamically create a ``dspy.Signature`` for *agent_node*.

        The signature includes a ``history`` field when conversation history is
        enabled, and memory-hint instructions are injected into the prompt.
        """
        role = agent_node.role or ""
        instructions = agent_node.instructions or ""

        if passages is not None:
            role = role.replace("{{ rag_document }}", passages)
            instructions = instructions.replace("{{ rag_document }}", passages)
        elif not getattr(agent_node, "enable_rag", False):
            role = role.replace("{{ rag_document }}", "")
            instructions = instructions.replace("{{ rag_document }}", "")

        if role and instructions:
            full_instructions = f"{role}\n\n{instructions}"
        elif role:
            full_instructions = role
        else:
            full_instructions = instructions or "You are a helpful AI agent."

        if agent_node.agent_type == "router":
            handoff_targets = [
                edge.target_node_id
                for edge in self._edges
                if edge.source_node_id == agent_node.id and edge.edge_type == "handoff"
            ]
            if len(handoff_targets) >= 2:
                target_names = [
                    self._agent_names.get(tid, f"Agent-{str(tid)[:8]}")
                    for tid in handoff_targets
                ]
                full_instructions += (
                    "\n\nYou have a parallel execution tool available: `execute_parallel_agents`. "
                    "If the user's request requires work from multiple downstream agents that can be run "
                    "independently/simultaneously, call `execute_parallel_agents` with the list of agent names "
                    "and their inputs to run them in parallel and get their combined findings. "
                    f"The available parallel handoff agents are: {', '.join(target_names)}."
                )

        if self._memory_manager.needs_memory(agent_node):
            if self._memory_manager.initialization_error is not None:
                err_details = str(self._memory_manager.initialization_error)
                full_instructions += (
                    f"\n\n[SYSTEM WARNING] Memory initialization failed: {err_details}. "
                    "Although memory tools (store_memory, search_memories, get_all_memories) "
                    "are registered on your toolset, calling them will fail. "
                    "If the user asks you to remember something or retrieve past information, "
                    "you must explicitly inform them that memory features are currently "
                    "disabled/failed and you cannot save or retrieve memories."
                )
            else:
                full_instructions += (
                    "\n\nYou have memory tools available. After each interaction, "
                    "use store_memory to save important information the user shares "
                    "(facts, preferences, details from previous questions). "
                    "When the user asks about something from the past, use search_memories "
                    "to look up relevant information. Use get_all_memories to list everything stored."
                )

        if getattr(agent_node, "enable_conversation_history", False):

            class _AgentSig(dspy.Signature):
                user_request: str = dspy.InputField()
                history: dspy.History = dspy.InputField()
                process_result: str = dspy.OutputField(
                    desc="Final answer summarizing the result and information the user needs"
                )

        else:

            class _AgentSig(dspy.Signature):
                user_request: str = dspy.InputField()
                process_result: str = dspy.OutputField(
                    desc="Final answer summarizing the result and information the user needs"
                )

        return _AgentSig.with_instructions(full_instructions)

    # ------------------------------------------------------------------
    # Building worker agents (eager, during setup)
    # ------------------------------------------------------------------

    async def build_workers(self, agent_nodes: list) -> dict[uuid.UUID, StreamingReAct]:
        """Eagerly build all worker agents from *agent_nodes*.

        Returns ``{agent_id: StreamingReAct}`` for every node with
        ``agent_type == "worker"``.  Router nodes are skipped (built lazily).
        """
        agents: dict[uuid.UUID, StreamingReAct] = {}
        for agent_node in agent_nodes:
            if agent_node.agent_type == "worker":
                agent = await self.build_worker(agent_node)
                agents[agent_node.id] = agent
        logger.info("Built %d worker agents", len(agents))
        return agents

    async def build_worker(self, agent_node, passages: str | None = None) -> StreamingReAct:
        """Build a single worker agent, optionally with retrieved RAG passages."""
        tools = list(
            self._tool_registry.get_tools_for_agent(agent_node.id, self._edges)
        )
        memory_provider = self._memory_manager.build_provider(agent_node)
        if memory_provider:
            tools.extend(
                [
                    memory_provider.search_memories,
                    memory_provider.store_memory,
                    memory_provider.get_all_memories,
                ]
            )

        if getattr(agent_node, "enable_plotting", False):
            if self._conversation_id:
                plot_provider = PlotProvider(self._conversation_id)
                tools.append(plot_provider.generate_plot)


        signature = self.build_signature(agent_node, passages=passages)
        agent = StreamingReAct(signature, tools=tools)
        logger.debug(
            "  built worker: id=%s name=%s tools=%d",
            agent_node.id,
            agent_node.name,
            len(tools),
        )
        return agent

    async def assemble_rag_worker(
        self,
        agent_node,
        task: str,
        conversation_service,
        send_event=None,
    ) -> StreamingReAct:
        """Fetch RAG documents, perform similarity search, handle warnings/errors, and compile the worker agent."""
        from canvas_server.runner.rag_helper import run_rag_search

        try:
            passages = await run_rag_search(agent_node.id, task)
        except Exception as e:
            warn_msg = f"RAG document retrieval failed for agent '{agent_node.name}': {e}"
            logger.warning(warn_msg)
            if send_event:
                await send_event({
                    "type": "warning",
                    "message": warn_msg
                })
            if conversation_service:
                await conversation_service.persist_message(
                    role="system",
                    content=warn_msg,
                    event_type="warning",
                    node_id=agent_node.id,
                )
            passages = "Here context retrieval failed and you see this line. You are unable to leverage context."

        return await self.build_worker(agent_node, passages=passages)

    # ------------------------------------------------------------------
    # Building router agents (lazy, at run time)
    # ------------------------------------------------------------------

    async def build_router(
        self,
        agent_node,
        existing_agents: dict[uuid.UUID, StreamingReAct],
        router_name: str,
        send_event,
        history_text: str,
        dspy_history,
        handoff_tool_builder: HandoffToolBuilder,
    ) -> StreamingReAct:
        """Build (or rebuild) a router agent and register it in *existing_agents*.

        This is called lazily — either from ``run()`` directly or from within a
        handoff-tool closure when a router→router handoff is triggered.
        """
        tools = list(
            self._tool_registry.get_tools_for_agent(agent_node.id, self._edges)
        )
        memory_provider = self._memory_manager.build_provider(agent_node)
        if memory_provider:
            tools.extend(
                [
                    memory_provider.search_memories,
                    memory_provider.store_memory,
                    memory_provider.get_all_memories,
                ]
            )

        if getattr(agent_node, "enable_plotting", False):
            if self._conversation_id:
                plot_provider = PlotProvider(self._conversation_id)
                tools.append(plot_provider.generate_plot)


        handoff_targets = await self._get_handoff_target_ids(agent_node.id)
        handoff_tools = [
            handoff_tool_builder.make_handoff_tool(
                tid, router_name, send_event, history_text, dspy_history
            )
            for tid in handoff_targets
        ]
        all_tools = tools + handoff_tools

        if len(handoff_targets) >= 2:
            parallel_tool = handoff_tool_builder.make_parallel_handoff_tool(
                handoff_targets, router_name, send_event, history_text, dspy_history
            )
            all_tools.append(parallel_tool)

        signature = self.build_signature(agent_node)
        agent = StreamingReAct(signature, tools=all_tools)
        existing_agents[agent_node.id] = agent
        return agent

    async def _get_handoff_target_ids(self, agent_id: uuid.UUID) -> list[uuid.UUID]:
        """Return handoff target node IDs for *agent_id*."""
        return [
            edge.target_node_id
            for edge in self._edges
            if edge.source_node_id == agent_id and edge.edge_type == "handoff"
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_worker_prompt(user_prompt: str, history: str = "") -> str:
        """Combine *history* and *user_prompt* into a single prompt string."""
        if history:
            return f"{history}\n\n{user_prompt}"
        return user_prompt

    @staticmethod
    def needs_history(agent_node) -> bool:
        return getattr(agent_node, "enable_conversation_history", False)
