import contextlib
import logging
import uuid

import dspy

from canvas_server.config import settings
from canvas_server.streaming_react import StreamingReAct
from canvas_server.tool_factory import compile_tool_from_code

logger = logging.getLogger("canvas_server.runner")


class CanvasRunner:
    def __init__(self, canvas, conversation_repo=None, conversation_id=None):
        self.canvas = canvas
        self.conversation_repo = conversation_repo
        self.conversation_id = conversation_id
        self.tools: dict[uuid.UUID, object] = {}
        # worker agents built during setup; router agents built at run time
        self.agents: dict[uuid.UUID, StreamingReAct] = {}
        self.node_map: dict[uuid.UUID, object] = {}
        self._lm = dspy.LM(
            settings.llm_model, api_base=settings.llm_base_url, api_key=""
        )

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

    def _build_agent_signature(self, agent_node):
        role = agent_node.role or ""
        instructions = agent_node.instructions or ""
        if role and instructions:
            full_instructions = f"{role}\n\n{instructions}"
        elif role:
            full_instructions = role
        else:
            full_instructions = instructions or "You are a helpful AI agent."

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
        agent = self.agents.get(agent_id)
        agent_node = self.node_map.get(agent_id)
        if agent and agent_node:
            agent.on_event(
                lambda event, aid=agent_id, aname=agent_node.name: send_event(
                    {"agent": aname, "node_id": str(aid), **event}
                )
            )

    def _make_handoff_tool(self, target_id: uuid.UUID, router_name: str, send_event, history: str):
        """Create a DSPy tool function that delegates to a sub-agent."""
        target_agent = self.agents[target_id]
        target_node = self.node_map[target_id]
        target_name = target_node.name

        async def transfer(task: str) -> str:
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

            prompt = self._build_worker_prompt(task, history)
            try:
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

    def _build_router_agent(self, agent_node, send_event, history: str):
        """Create a fresh StreamingReAct for a router with handoff tools baked in."""
        tools = self._get_agent_tools(agent_node.id)
        handoff_tool_fns = [
            self._make_handoff_tool(tid, agent_node.name, send_event, history)
            for tid in self._get_handoff_targets(agent_node.id)
        ]
        all_tools = tools + handoff_tool_fns

        signature = self._build_agent_signature(agent_node)
        agent = StreamingReAct(signature, tools=all_tools)
        self._attach_events(agent_node.id, send_event)
        return agent

    def _agent_name(self, agent_id: uuid.UUID) -> str:
        node = self.node_map.get(agent_id)
        return node.name if node else "Unknown"

    def _format_history(self, messages: list) -> str:
        if not messages:
            return ""
        lines = ["## Conversation History"]
        for msg in messages:
            role_label = msg.role.capitalize()
            if msg.agent_name and msg.role == "assistant":
                role_label = f"Assistant [{msg.agent_name}]"
            lines.append(f"{role_label}: {msg.content}")
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
        self, agent_id: uuid.UUID, user_prompt: str, send_event
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

    async def run(
        self,
        user_prompt: str,
        send_event,
        target_agent_id: uuid.UUID | None = None,
    ):
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
            return

        await send_event(self._event("run_start", canvas_id=str(self.canvas.id)))

        await self._persist_message(
            role="user",
            content=user_prompt,
            event_type="run_start",
        )

        history_messages = await self._load_conversation_history()
        history_text = self._format_history(history_messages)

        with dspy.context(lm=self._lm):

            agent_ids = [n.id for n in self.canvas.agent_nodes]

            if target_agent_id is not None and target_agent_id in self.agents:
                agent_node = self.node_map[target_agent_id]

                if agent_node.agent_type == "router":
                    agent = self._build_router_agent(
                        agent_node, send_event, history_text
                    )
                    prompt = self._build_worker_prompt(user_prompt, history_text)
                    result = await agent.aforward(user_request=prompt)
                    final_text = result.process_result
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
                        target_agent_id, user_prompt, send_event
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
                        first_node, send_event, history_text
                    )
                    prompt = self._build_worker_prompt(user_prompt, history_text)
                    result = await agent.aforward(user_request=prompt)
                    final_text = result.process_result
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

                    while current_agent_id is not None and current_agent_id not in visited:
                        visited.add(current_agent_id)
                        self._attach_events(current_agent_id, send_event)

                        result_text = await self._run_worker(
                            current_agent_id, user_prompt, send_event
                        )
                        if result_text is None:
                            break

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

        if self.conversation_repo and self.conversation_id:
            with contextlib.suppress(Exception):
                await self.conversation_repo.complete_conversation(
                    self.conversation_id
                )

        logger.info(
            "Canvas execution completed: canvas_id=%s", self.canvas.id
        )
        await send_event(
            self._event("run_complete", result="Workflow execution completed.")
        )
