import logging
import uuid

import dspy
import mlflow

from canvas_server.config import settings
from canvas_server.memory_config import build_mem0_config
from canvas_server.memory_provider import MemoryProvider
from canvas_server.streaming_react import StreamingReAct
from canvas_server.tool_factory import compile_tool_from_code

logger = logging.getLogger("canvas_server.runner")


class CanvasRunner:
    def __init__(self, canvas, conversation_repo=None, conversation_id=None):
        self.canvas = canvas
        self.conversation_repo = conversation_repo
        self.conversation_id = conversation_id
        self.tools: dict[uuid.UUID, object] = {}
        self._tool_name_to_id: dict[str, uuid.UUID] = {}
        self._wired_agents: set[uuid.UUID] = set()
        # worker agents built during setup; router agents built at run time
        self.agents: dict[uuid.UUID, StreamingReAct] = {}
        self.node_map: dict[uuid.UUID, object] = {}
        self._lm = dspy.LM(
            settings.llm_model, api_base=settings.llm_base_url, api_key=""
        )
        self._memory_providers: dict[uuid.UUID, MemoryProvider] = {}
        self._shared_memory = None

    async def setup(self):
        logger.info("Setting up canvas runner")
        for node in self.canvas.agent_nodes:
            self.node_map[node.id] = node

        await self._build_tools()
        await self._build_agents()
        logger.info(
            "Setup complete: %d tools, %d agents", len(self.tools), len(self.agents)
        )

    async def _build_tools(self):
        logger.debug("Building tools from %d tool nodes", len(self.canvas.tool_nodes))
        for tool_node in self.canvas.tool_nodes:
            try:
                fn = await compile_tool_from_code(tool_node.name, tool_node.code)
                self.tools[tool_node.id] = fn
                self._tool_name_to_id[tool_node.name] = tool_node.id
                logger.debug(
                    "  compiled tool: id=%s name=%s", tool_node.id, tool_node.name
                )
            except Exception as e:
                logger.error(
                    "  failed to compile tool %s: %s", tool_node.name, e, exc_info=True
                )
        logger.info("Built %d tools successfully", len(self.tools))

    def _get_agent_tools(self, agent_id: uuid.UUID) -> list:
        agent_tools = []
        for edge in self.canvas.edges:
            if edge.source_node_id == agent_id and edge.edge_type == "tool_access":
                fn = self.tools.get(edge.target_node_id)
                if fn:
                    agent_tools.append(fn)
        return agent_tools

    def _get_handoff_targets(self, agent_id: uuid.UUID) -> list:
        targets = []
        for edge in self.canvas.edges:
            if edge.source_node_id == agent_id and edge.edge_type == "handoff":
                targets.append(edge.target_node_id)
        return targets

    def _needs_memory(self, agent_node) -> bool:
        return getattr(agent_node, "enable_memory", False)

    def _needs_history(self, agent_node) -> bool:
        return getattr(agent_node, "enable_conversation_history", False)

    def _init_shared_memory(self):
        """Create a single shared mem0 Memory instance to avoid local-qdrant file locking."""
        if self._shared_memory is None:
            from mem0 import Memory
            config = build_mem0_config()
            self._shared_memory = Memory.from_config(config)
        return self._shared_memory

    def _build_memory_provider(self, agent_node) -> MemoryProvider | None:
        if not self._needs_memory(agent_node):
            return None
        try:
            memory = self._init_shared_memory()
            user_id = f"agent_{agent_node.id}"
            return MemoryProvider(user_id=user_id, memory=memory)
        except ImportError:
            logger.warning("mem0 not installed; memory disabled for agent %s", agent_node.name)
            return None
        except Exception as e:
            logger.warning("Failed to initialize mem0 for agent %s: %s", agent_node.name, e)
            return None

    def _build_agent_signature(self, agent_node):
        role = agent_node.role or ""
        instructions = agent_node.instructions or ""
        if role and instructions:
            full_instructions = f"{role}\n\n{instructions}"
        elif role:
            full_instructions = role
        else:
            full_instructions = instructions or "You are a helpful AI agent."

        if self._needs_memory(agent_node):
            full_instructions += (
                "\n\nYou have memory tools available. After each interaction, "
                "use store_memory to save important information the user shares "
                "(facts, preferences, details from previous questions). "
                "When the user asks about something from the past, use search_memories "
                "to look up relevant information. Use get_all_memories to list everything stored."
            )

        if self._needs_history(agent_node):
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

    def _build_worker_prompt(self, user_prompt: str, history: str = "") -> str:
        parts = []
        if history:
            parts.append(history)
        parts.append(user_prompt)
        return "\n\n".join(parts)

    async def _build_agents(self):
        logger.debug(
            "Building agents from %d agent nodes", len(self.canvas.agent_nodes)
        )

        # Build worker agents at setup time; router agents are built at run time
        # (they need send_event and history which aren't available during setup).
        for agent_node in self.canvas.agent_nodes:
            if agent_node.agent_type == "worker":
                await self._build_single_worker(agent_node)

        logger.info(
            "Built %d agents successfully", len(self.agents)
        )

    async def _build_single_worker(self, agent_node):
        tools = self._get_agent_tools(agent_node.id)

        memory_provider = self._build_memory_provider(agent_node)
        if memory_provider:
            tools.extend([
                memory_provider.search_memories,
                memory_provider.store_memory,
                memory_provider.get_all_memories,
            ])
            self._memory_providers[agent_node.id] = memory_provider

        signature = self._build_agent_signature(agent_node)
        agent = StreamingReAct(signature, tools=tools)
        self.agents[agent_node.id] = agent
        logger.debug(
            "  built worker: id=%s name=%s tools=%d",
            agent_node.id,
            agent_node.name,
            len(tools),
        )

    def _attach_events(self, agent_id: uuid.UUID, send_event):
        """Wire event callbacks on an agent so StreamingReAct events flow to send_event."""
        if agent_id in self._wired_agents:
            return
        agent = self.agents.get(agent_id)
        agent_node = self.node_map.get(agent_id)
        if agent and agent_node:
            self._wired_agents.add(agent_id)
            tool_name_to_id = self._tool_name_to_id

            async def callback(event, aid=agent_id, aname=agent_node.name):
                await send_event(
                    {"agent": aname, "node_id": str(aid), **event}
                )
                if event.get("type") == "tool_start":
                    tool_name = event.get("tool", "")
                    tool_node_id = tool_name_to_id.get(tool_name)
                    if tool_node_id:
                        await send_event(
                            {"type": "tool_start", "tool": tool_name, "node_id": str(tool_node_id)}
                        )

            agent.on_event(callback)

    def _make_handoff_tool(self, target_id: uuid.UUID, router_name: str, send_event, history: str, dspy_history=None):
        """Create a DSPy tool function that delegates to a sub-agent.

        The target agent lookup is deferred to call time so that router→router
        handoffs work: router agents are built lazily when first invoked, not
        during the parent router's setup.
        """
        target_node = self.node_map[target_id]
        target_name = target_node.name

        async def transfer(task: str) -> str:
            # Lazily build the target agent if it hasn't been built yet
            # (e.g. a router that wasn't pre-built during setup)
            if target_id not in self.agents:
                if target_node.agent_type == "router":
                    self._build_router_agent(target_node, send_event, history, dspy_history)
                else:
                    raise RuntimeError(
                        f"Worker agent '{target_name}' (id={target_id}) not found in agents dict"
                    )

            target_agent = self.agents[target_id]

            await send_event(
                {
                    "type": "handoff",
                    "from": router_name,
                    "to": target_name,
                    "node_id": str(target_id),
                }
            )
            await send_event(
                {
                    "type": "agent_start",
                    "agent": target_name,
                    "agentType": target_node.agent_type,
                    "node_id": str(target_id),
                }
            )

            self._attach_events(target_id, send_event)
            prompt = self._build_worker_prompt(task, history)
            try:
                if dspy_history is not None and self._needs_history(target_node):
                    result = await target_agent.aforward(user_request=prompt, history=dspy_history)
                else:
                    result = await target_agent.aforward(user_request=prompt)
                answer = result.process_result
            except Exception as e:
                answer = f"Error: {e}"
                logger.error(
                    "Sub-agent %s failed: %s", target_name, e, exc_info=True
                )

            await self._persist_message(
                role="assistant",
                content=answer,
                agent_name=target_name,
                node_id=target_id,
                event_type="final_answer",
            )
            return answer

        transfer.__name__ = f"transfer_to_{target_name}"
        transfer.__doc__ = (
            f"Route the user request to {target_name}, who handles: {target_node.role or target_name}"
        )
        return transfer

    def _build_router_agent(self, agent_node, send_event, history: str, dspy_history=None):
        """Create a fresh StreamingReAct for a router with handoff tools baked in."""
        tools = self._get_agent_tools(agent_node.id)

        memory_provider = self._build_memory_provider(agent_node)
        if memory_provider:
            tools.extend([
                memory_provider.search_memories,
                memory_provider.store_memory,
                memory_provider.get_all_memories,
            ])
            self._memory_providers[agent_node.id] = memory_provider

        handoff_tool_fns = [
            self._make_handoff_tool(tid, agent_node.name, send_event, history, dspy_history)
            for tid in self._get_handoff_targets(agent_node.id)
        ]
        all_tools = tools + handoff_tool_fns

        signature = self._build_agent_signature(agent_node)
        agent = StreamingReAct(signature, tools=all_tools)
        self.agents[agent_node.id] = agent
        self._attach_events(agent_node.id, send_event)
        return agent

    def _agent_name(self, agent_id: uuid.UUID) -> str:
        node = self.node_map.get(agent_id)
        return node.name if node else "Unknown"

    def _format_history(
        self, messages: list, history_enabled_node_ids: set | None = None
    ) -> str:
        if not messages:
            return ""
        lines = ["## Conversation History"]
        for msg in messages:
            # System prompts are already in the DSPy signature — skip them
            if msg.role == "system":
                continue
            # Only include assistant messages from agents with history enabled;
            # intermediate sub-agent responses are internal implementation details.
            if msg.role == "assistant" and history_enabled_node_ids is not None:
                if msg.node_id not in history_enabled_node_ids:
                    continue
            if msg.agent_name and msg.role == "assistant":
                label = f"Assistant [{msg.agent_name}]"
            else:
                label = msg.role.capitalize()
            lines.append(f"{label}: {msg.content}")
            lines.append("---")
        return "\n".join(lines)

    async def _load_conversation_history(self) -> list:
        if not self.conversation_repo or not self.conversation_id:
            return []
        try:
            conv = await self.conversation_repo.get(self.conversation_id)
            if conv:
                return list(conv.messages)
        except Exception:
            pass
        return []

    async def _persist_message(
        self,
        role: str,
        content: str,
        agent_name: str | None = None,
        node_id: uuid.UUID | None = None,
        event_type: str | None = None,
    ):
        if not self.conversation_repo or not self.conversation_id:
            return
        try:
            await self.conversation_repo.add_message(
                conversation_id=self.conversation_id,
                role=role,
                content=content,
                agent_name=agent_name,
                node_id=node_id,
                event_type=event_type,
            )
        except Exception as e:
            logger.error("Failed to persist message: %s", e, exc_info=True)

    def _event(self, type_: str, **kwargs) -> dict:
        kwargs["type"] = type_
        return kwargs

    async def _run_worker(
        self, agent_id: uuid.UUID, user_prompt: str, send_event, dspy_history=None
    ):
        agent = self.agents.get(agent_id)
        agent_node = self.node_map.get(agent_id)
        if not agent or not agent_node:
            logger.warning("Agent not found: id=%s", agent_id)
            return None

        logger.info(
            "Running agent: %s (type=%s)",
            agent_node.name,
            agent_node.agent_type,
        )

        prompt = self._build_worker_prompt(user_prompt)

        try:
            if dspy_history is not None and self._needs_history(agent_node):
                result = await agent.aforward(user_request=prompt, history=dspy_history)
            else:
                result = await agent.aforward(user_request=prompt)
            text = result.process_result
            logger.info(
                "Agent %s completed: result=%s", agent_node.name, text[:200]
            )
            await self._persist_message(
                role="assistant",
                content=text,
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="final_answer",
            )
            return text
        except Exception as e:
            logger.error(
                "Agent %s failed: %s", agent_node.name, e, exc_info=True
            )
            await self._persist_message(
                role="system",
                content=f"Error: {e}",
                agent_name=agent_node.name,
                node_id=agent_id,
                event_type="error",
            )
            return None

    @mlflow.trace(name="canvas_run", span_type="CHAIN", attributes={"component": "agent"})
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

        history_messages = await self._load_conversation_history()

        agent_ids = [n.id for n in self.canvas.agent_nodes]

        # Determine if the target agent has conversation history enabled
        first_agent_id = target_agent_id if target_agent_id else (agent_ids[0] if agent_ids else None)
        target_node = self.node_map.get(first_agent_id) if first_agent_id else None
        conv_history_enabled = target_node and self._needs_history(target_node)

        # Compute which agents have history enabled — used to filter intermediate
        # sub-agent responses from conversation history.  Only messages from
        # history-enabled agents should appear; sub-agent responses are internal
        # details that don't belong in the agent's conversation context.
        history_enabled_node_ids = {
            n.id for n in self.canvas.agent_nodes if self._needs_history(n)
        }

        await self._persist_message(
            role="user",
            content=user_prompt,
            event_type="run_start",
        )

        history_text = self._format_history(
            history_messages, history_enabled_node_ids=history_enabled_node_ids
        )

        # Build dspy.History from stored conversation messages when enabled.
        # Only include user messages and assistant messages from history-enabled
        # agents.  System prompts are excluded — they're already in the DSPy
        # signature instructions.  Intermediate sub-agent responses are excluded
        # — only the final answers from history-enabled agents matter.
        dspy_history = None
        if conv_history_enabled:
            dspy_messages = []
            for msg in history_messages:
                if msg.role == "system":
                    continue
                elif msg.role == "user":
                    dspy_messages.append({"user_request": msg.content})
                elif msg.role == "assistant":
                    if msg.node_id in history_enabled_node_ids:
                        dspy_messages.append({"process_result": msg.content})
            dspy_history = dspy.History(messages=dspy_messages)

        final_text = None

        with dspy.context(lm=self._lm):

            if target_agent_id is not None and target_agent_id in self.agents:
                agent_node = self.node_map[target_agent_id]

                if agent_node.agent_type == "router":
                    agent = self._build_router_agent(
                        agent_node, send_event, history_text, dspy_history
                    )
                    prompt = self._build_worker_prompt(user_prompt, history_text)
                    if dspy_history is not None:
                        result = await agent.aforward(user_request=prompt, history=dspy_history)
                    else:
                        result = await agent.aforward(user_request=prompt)
                    final_text = result.process_result
                    await self._persist_message(
                        role="assistant",
                        content=final_text,
                        agent_name=agent_node.name,
                        node_id=target_agent_id,
                        event_type="final_answer",
                    )
                    await send_event(
                        self._event(
                            "final_answer",
                            agent=agent_node.name,
                            content=final_text,
                            node_id=str(target_agent_id),
                        )
                    )
                else:
                    self._attach_events(target_agent_id, send_event)
                    result = await self._run_worker(
                        target_agent_id, user_prompt, send_event, dspy_history
                    )
                    final_text = result
                    if result is not None:
                        await send_event(
                            self._event(
                                "final_answer",
                                agent=agent_node.name,
                                content=result,
                                node_id=str(target_agent_id),
                            )
                        )
            else:
                first_node = self.node_map[agent_ids[0]]

                if first_node.agent_type == "router":
                    agent = self._build_router_agent(
                        first_node, send_event, history_text, dspy_history
                    )
                    prompt = self._build_worker_prompt(user_prompt, history_text)
                    if dspy_history is not None:
                        result = await agent.aforward(user_request=prompt, history=dspy_history)
                    else:
                        result = await agent.aforward(user_request=prompt)
                    final_text = result.process_result
                    await self._persist_message(
                        role="assistant",
                        content=final_text,
                        agent_name=first_node.name,
                        node_id=first_node.id,
                        event_type="final_answer",
                    )
                    await send_event(
                        self._event(
                            "final_answer",
                            agent=first_node.name,
                            content=final_text,
                            node_id=str(first_node.id),
                        )
                    )
                else:
                    handoff_map = {}
                    for agent_node in self.canvas.agent_nodes:
                        handoff_map[agent_node.id] = self._get_handoff_targets(
                            agent_node.id
                        )

                    current_agent_id = agent_ids[0]
                    visited = set()
                    final_text = None

                    while current_agent_id is not None and current_agent_id not in visited:
                        visited.add(current_agent_id)
                        self._attach_events(current_agent_id, send_event)

                        result_text = await self._run_worker(
                            current_agent_id, user_prompt, send_event, dspy_history
                        )
                        if result_text is None:
                            break

                        final_text = result_text

                        await send_event(
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
                            await send_event(
                                {
                                    "type": "handoff",
                                    "from": self._agent_name(current_agent_id),
                                    "to": next_name,
                                    "node_id": str(next_agent_id),
                                }
                            )

                        current_agent_id = next_agent_id

            # Append the turn to dspy_history if being used
            if dspy_history is not None and final_text:
                dspy_history.messages.append(
                    {"user_request": user_prompt, "process_result": final_text}
                )

            # Auto-store memory for the primary agent.  This is more reliable than
            # relying on the LLM to call store_memory on its own.
            if final_text:
                primary_id = target_agent_id if target_agent_id else agent_ids[0]
                primary_node = self.node_map.get(primary_id) if primary_id else None
                if primary_node and self._needs_memory(primary_node):
                    mp = self._memory_providers.get(primary_id)
                    if mp:
                        try:
                            await mp.store_memory(
                                f"The user asked: '{user_prompt}' → Response: {final_text[:500]}"
                            )
                        except Exception as e:
                            logger.warning("Failed to auto-store memory: %s", e)

        # Do NOT mark the conversation as "completed" here — the user
        # may send more messages in the same conversation.  Conversations
        # should stay "active" across multiple turns so that
        # enable_conversation_history works correctly.

        logger.info(
            "Canvas execution completed: canvas_id=%s", self.canvas.id
        )
        await send_event(
            self._event("run_complete", result="Workflow execution completed.")
        )
        return final_text
