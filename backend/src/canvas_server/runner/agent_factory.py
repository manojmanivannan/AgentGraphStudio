"""AgentFactory — builds worker and router StreamingReAct agents."""

from __future__ import annotations

import logging
import uuid

import dspy

from canvas_server.streaming_react import StreamingReAct

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
    ):
        self._lm = lm
        self._tool_registry = tool_registry
        self._memory_manager = memory_manager
        self._edges = edges

    # ------------------------------------------------------------------
    # DSPy signature
    # ------------------------------------------------------------------

    def build_signature(self, agent_node) -> type[dspy.Signature]:
        """Dynamically create a ``dspy.Signature`` for *agent_node*.

        The signature includes a ``history`` field when conversation history is
        enabled, and memory-hint instructions are injected into the prompt.
        """
        role = agent_node.role or ""
        instructions = agent_node.instructions or ""

        if not getattr(agent_node, "enable_rag", False):
            role = role.replace("{{ rag_document }}", "")
            instructions = instructions.replace("{{ rag_document }}", "")

        if role and instructions:
            full_instructions = f"{role}\n\n{instructions}"
        elif role:
            full_instructions = role
        else:
            full_instructions = instructions or "You are a helpful AI agent."

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
                agent = await self._build_worker(agent_node)
                agents[agent_node.id] = agent
        logger.info("Built %d worker agents", len(agents))
        return agents

    async def _build_worker(self, agent_node) -> StreamingReAct:
        """Build a single worker agent."""
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

        signature = self.build_signature(agent_node)
        agent = StreamingReAct(signature, tools=tools)
        logger.debug(
            "  built worker: id=%s name=%s tools=%d",
            agent_node.id,
            agent_node.name,
            len(tools),
        )
        return agent

    async def build_worker_with_rag_prompt(self, agent_node, passages: str) -> StreamingReAct:
        """Build a single worker agent with RAG search results substituted into instructions."""
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

        role = agent_node.role or ""
        instructions = agent_node.instructions or ""

        # Substitute the template placeholder
        role = role.replace("{{ rag_document }}", passages)
        instructions = instructions.replace("{{ rag_document }}", passages)

        if role and instructions:
            full_instructions = f"{role}\n\n{instructions}"
        elif role:
            full_instructions = role
        else:
            full_instructions = instructions or "You are a helpful AI agent."

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

        signature = _AgentSig.with_instructions(full_instructions)
        agent = StreamingReAct(signature, tools=tools)
        return agent

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
        make_handoff_tool_fn,
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

        handoff_targets = await self._get_handoff_target_ids(agent_node.id)
        handoff_tools = [
            make_handoff_tool_fn(
                tid, router_name, send_event, history_text, dspy_history
            )
            for tid in handoff_targets
        ]
        all_tools = tools + handoff_tools

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
