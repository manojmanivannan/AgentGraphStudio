import uuid
import logging

from beeai_framework.agents.react import ReActAgent
from beeai_framework.backend.chat import ChatModel
from beeai_framework.memory.unconstrained_memory import UnconstrainedMemory

from canvas_server.exceptions import ExecutionError
from canvas_server.tool_factory import compile_tool_from_code

logger = logging.getLogger("canvas_server.runner")


class CanvasRunner:
    def __init__(self, canvas):
        self.canvas = canvas
        self.tools: dict[uuid.UUID, object] = {}
        self.agents: dict[uuid.UUID, ReActAgent] = {}

    async def setup(self):
        logger.info("Setting up canvas runner")
        await self._build_tools()
        await self._build_agents()
        logger.info(
            "Setup complete: %d tools, %d agents",
            len(self.tools),
            len(self.agents),
        )

    async def _build_tools(self):
        logger.debug("Building tools from %d tool nodes", len(self.canvas.tool_nodes))
        for tool_node in self.canvas.tool_nodes:
            try:
                beeai_tool = await compile_tool_from_code(tool_node.name, tool_node.code)
                self.tools[tool_node.id] = beeai_tool
                logger.debug("  compiled tool: id=%s name=%s", tool_node.id, tool_node.name)
            except Exception as e:
                logger.error("  failed to compile tool %s: %s", tool_node.name, e, exc_info=True)
        logger.info("Built %d tools successfully", len(self.tools))

    def _get_agent_tools(self, agent_id: uuid.UUID) -> list:
        agent_tools = []
        for edge in self.canvas.edges:
            if edge.source_node_id == agent_id and edge.edge_type == "tool_access":
                tool = self.tools.get(edge.target_node_id)
                if tool:
                    agent_tools.append(tool)
        return agent_tools

    def _get_handoff_targets(self, agent_id: uuid.UUID) -> list:
        targets = []
        for edge in self.canvas.edges:
            if edge.source_node_id == agent_id and edge.edge_type == "handoff":
                targets.append(edge.target_node_id)
        return targets

    async def _build_agents(self):
        logger.debug("Building agents from %d agent nodes", len(self.canvas.agent_nodes))
        for agent_node in self.canvas.agent_nodes:
            tools = self._get_agent_tools(agent_node.id)
            logger.debug(
                "  agent: id=%s name=%s model=%s tools=%d",
                agent_node.id,
                agent_node.name,
                agent_node.model_name,
                len(tools),
            )
            try:
                llm = ChatModel.from_name(agent_node.model_name)
                agent = ReActAgent(
                    llm=llm,
                    tools=tools,
                    memory=UnconstrainedMemory(),
                )
                self.agents[agent_node.id] = agent
            except Exception as e:
                logger.error(
                    "  failed to build agent %s: %s",
                    agent_node.name,
                    e,
                    exc_info=True,
                )
        logger.info("Built %d agents successfully", len(self.agents))

    def _agent_name(self, agent_id: uuid.UUID) -> str:
        for node in self.canvas.agent_nodes:
            if node.id == agent_id:
                return node.name
        return "Unknown"

    def _agent_prompt(self, agent_node, user_prompt: str) -> str:
        parts = []
        if agent_node.role:
            parts.append(f"You are: {agent_node.role}")
        if agent_node.instructions:
            parts.append(agent_node.instructions)
        parts.append(user_prompt)
        return "\n\n".join(parts)

    async def run(self, user_prompt: str, send_event):
        logger.info("Starting canvas execution: canvas_id=%s prompt=%s", self.canvas.id, user_prompt[:100])
        await self.setup()

        if not self.canvas.agent_nodes:
            logger.error("Canvas has no agent nodes")
            await send_event({"type": "error", "message": "Canvas has no agents to run."})
            return

        handoff_map = {}
        agent_node_map = {}
        for agent_node in self.canvas.agent_nodes:
            handoff_map[agent_node.id] = self._get_handoff_targets(agent_node.id)
            agent_node_map[agent_node.id] = agent_node
            logger.debug(
                "  agent %s handoff targets: %s",
                agent_node.name,
                [self._agent_name(t) for t in handoff_map[agent_node.id]],
            )

        await send_event({"type": "run_start", "canvas_id": str(self.canvas.id)})

        agent_ids = [n.id for n in self.canvas.agent_nodes]
        current_agent_id = agent_ids[0]
        visited = set()

        while current_agent_id is not None and current_agent_id not in visited:
            visited.add(current_agent_id)
            agent = self.agents.get(current_agent_id)
            agent_node = agent_node_map.get(current_agent_id)
            if not agent or not agent_node:
                logger.warning("Agent not found: id=%s", current_agent_id)
                break

            logger.info("Running agent: %s (model=%s)", agent_node.name, agent_node.model_name)
            await send_event({"type": "agent_start", "agent": agent_node.name})

            prompt = self._agent_prompt(agent_node, user_prompt)

            try:
                result = await agent.run(prompt)
                text = str(result.result) if hasattr(result, "result") else str(result)
                logger.info("Agent %s completed: result=%s", agent_node.name, text[:200])
                await send_event({
                    "type": "final_answer",
                    "agent": agent_node.name,
                    "content": text,
                })
            except Exception as e:
                logger.error("Agent %s failed: %s", agent_node.name, e, exc_info=True)
                await send_event({
                    "type": "error",
                    "message": str(e),
                    "agent": agent_node.name,
                })

            handoff_targets = handoff_map.get(current_agent_id, [])
            next_agent_id = handoff_targets[0] if handoff_targets else None

            if next_agent_id and next_agent_id != current_agent_id:
                next_name = self._agent_name(next_agent_id)
                logger.info("Handoff: %s -> %s", agent_node.name, next_name)
                await send_event({
                    "type": "handoff",
                    "from": agent_node.name,
                    "to": next_name,
                })

            current_agent_id = next_agent_id

        logger.info("Canvas execution completed: canvas_id=%s", self.canvas.id)
        await send_event({"type": "run_complete", "result": "Workflow execution completed."})
