"""AgentFactory — builds worker and router StreamingReAct agents."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import dspy

from canvas_server.runner.plot_provider import PlotProvider
from canvas_server.streaming_react import StreamingReAct

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
        conversation_repo = None,
    ):
        self._lm = lm
        self._tool_registry = tool_registry
        self._memory_manager = memory_manager
        self._edges = edges
        self._agent_names = agent_names or {}
        self._conversation_id = conversation_id
        self._conversation_repo = conversation_repo
        self._run_state = None

    # ------------------------------------------------------------------
    # DSPy signature
    # ------------------------------------------------------------------

    def build_signature(self, agent_node, passages: str | None = None) -> type[dspy.Signature]:
        """Dynamically creates a `dspy.Signature` class for an agent node.

        The signature dictates the input/output structure for the DSPy LLM module
        and embeds instructions. This method compiles the user-defined role and
        instructions, substituting template variables (like `{{ rag_document }}`),
        and dynamically appends system prompts based on the agent's configured
        capabilities (e.g., parallel handoff, plotting, HITL, memory).

        Args:
            agent_node: The AgentNode model defining configuration.
            passages (str | None, optional): Retrieved RAG document text to inject.

        Returns:
            type[dspy.Signature]: A generated DSPy Signature class.
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

        handoff_targets = [
            edge.target_node_id
            for edge in self._edges
            if edge.source_node_id == agent_node.id and edge.edge_type == "handoff"
        ]
        if handoff_targets:
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

            full_instructions += (
                "\n\n[CRITICAL SYSTEM RULE] If any downstream agent or tool generates a plot "
                "or returns a markdown image link (e.g. `![Plot](/api/static/plots/...)`), "
                "you MUST preserve this image markdown link exactly and include it "
                "in your final answer/response to the user. Do not omit, summarize, or modify the image link."
            )

        if getattr(agent_node, "enable_plotting", False):
            full_instructions += (
                "\n\n[CRITICAL SYSTEM RULE] If you call the plotting tool `generate_plot` and it returns "
                "a markdown image link (e.g. `![Plot](/api/plots/...)`), you MUST preserve this image "
                "markdown link exactly and include it in your final answer/response (process_result). "
                "Do not omit, summarize, or modify the image link."
            )

        if getattr(agent_node, "enable_hitl", False):
            full_instructions += (
                "\n\nYou have a tool `ask_human` available. If you need clarification, "
                "more information, or need to ask the user a question (for example, if a "
                "parameter is ambiguous or you need the user to choose an option), you MUST "
                "call the `ask_human` tool with your question. Do not reply to the user "
                "directly with the question in your thought or final answer."
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
        """Eagerly builds all worker agents during runner setup.

        Worker agents do not depend on ephemeral run state (like event streams)
        unless they have handoff targets (which is rare, but supported via lazy
        rebuilding). Therefore, standard workers are built once when the runner
        initializes, avoiding compilation overhead on every message.

        Args:
            agent_nodes (list): List of AgentNode instances from the canvas.

        Returns:
            dict[uuid.UUID, StreamingReAct]: Mapping of worker agent IDs to
                compiled DSPy ReAct instances.
        """
        agents: dict[uuid.UUID, StreamingReAct] = {}
        for agent_node in agent_nodes:
            if agent_node.agent_type == "worker":
                agent = await self.build_worker(agent_node)
                agents[agent_node.id] = agent
        logger.info("Built %d worker agents", len(agents))
        return agents

    async def build_worker(
        self,
        agent_node,
        passages: str | None = None,
        handoff_tool_builder: HandoffToolBuilder | None = None,
        send_event=None,
        history_text: str = "",
        dspy_history=None,
    ) -> StreamingReAct:
        """Builds a single worker agent instance.

        Collects tools from the registry, attaches memory providers if enabled,
        injects plotting tools if enabled, creates the `ask_human` HITL tool,
        and finally constructs the StreamingReAct agent with the built signature.

        Args:
            agent_node: The AgentNode configuration model.
            passages (str | None, optional): Optional RAG context to inject into prompt.
            handoff_tool_builder (HandoffToolBuilder | None, optional): Builder for delegation tools.
            send_event (Callable | None, optional): Callback for websocket events.
            history_text (str, optional): Formatted conversation history.
            dspy_history (Any, optional): DSPy native history object.

        Returns:
            StreamingReAct: The constructed agent instance.
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

        if getattr(agent_node, "enable_plotting", False) and self._conversation_id:
            plot_provider = PlotProvider(self._conversation_id, self._conversation_repo)
            tools.append(plot_provider.generate_plot)

        if getattr(agent_node, "enable_hitl", False):
            async def ask_human(question: str) -> str:
                """Ask a human user for input or clarification when you are stuck or need more information.

                Args:
                    question: The question or prompt to show to the human user.

                Returns:
                    The text response provided by the human user.
                """
                request_id = str(uuid.uuid4())

                # Persist the interrupt request to conversation messages
                if self._conversation_id and self._conversation_repo:
                    await self._conversation_repo.add_message(
                        conversation_id=uuid.UUID(self._conversation_id) if isinstance(self._conversation_id, str) else self._conversation_id,
                        role="assistant",
                        content=question,
                        agent_name=agent_node.name,
                        node_id=agent_node.id,
                        event_type="human_input_request",
                    )

                # Send websocket event
                run_state = getattr(self, "_run_state", None)
                if run_state and run_state.send_event:
                    await run_state.send_event({
                        "type": "human_input_request",
                        "request_id": request_id,
                        "question": question,
                        "agent": agent_node.name,
                        "node_id": str(agent_node.id),
                    })

                # Wait for the response
                if run_state and hasattr(run_state, "get_client_response") and run_state.get_client_response:
                    res = await run_state.get_client_response(request_id, "human_input_response")
                    content = res.get("content", "")

                    # Persist the user's response to history
                    if self._conversation_id and self._conversation_repo:
                        await self._conversation_repo.add_message(
                            conversation_id=uuid.UUID(self._conversation_id) if isinstance(self._conversation_id, str) else self._conversation_id,
                            role="user",
                            content=content,
                            agent_name=None,
                            node_id=None,
                            event_type="human_input_response",
                        )
                    return content

                return "Error: Human input callback not available."

            tools.append(ask_human)

        if handoff_tool_builder and send_event:
            handoff_targets = await self._get_handoff_target_ids(agent_node.id)
            handoff_tools = [
                handoff_tool_builder.make_handoff_tool(
                    tid, agent_node.name, send_event, history_text, dspy_history
                )
                for tid in handoff_targets
            ]
            tools.extend(handoff_tools)

            if len(handoff_targets) >= 2:
                parallel_tool = handoff_tool_builder.make_parallel_handoff_tool(
                    handoff_targets, agent_node.name, send_event, history_text, dspy_history
                )
                tools.append(parallel_tool)

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
        handoff_tool_builder: HandoffToolBuilder | None = None,
        history_text: str = "",
        dspy_history=None,
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

        return await self.build_worker(
            agent_node,
            passages=passages,
            handoff_tool_builder=handoff_tool_builder,
            send_event=send_event,
            history_text=history_text,
            dspy_history=dspy_history,
        )

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
        """Lazily builds a router agent at execution time.

        Unlike workers, routers MUST be built at runtime because they require
        dynamically generated handoff tools. These handoff tools need the active
        `send_event` callback and `dspy_history` context to properly bridge
        execution from the router to the sub-agent.

        Args:
            agent_node: The Router agent node configuration.
            existing_agents (dict): Reference to the runner's dictionary of compiled agents.
            router_name (str): The display name of the router.
            send_event (Callable): Active callback for websocket event dispatch.
            history_text (str): Formatted conversational history string.
            dspy_history: Active DSPy history list.
            handoff_tool_builder (HandoffToolBuilder): Helper to construct delegation callables.

        Returns:
            StreamingReAct: The constructed router agent.
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
