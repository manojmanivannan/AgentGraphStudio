import uuid
import logging
import re

from beeai_framework.agents.react import ReActAgent
from beeai_framework.backend.chat import ChatModel
from beeai_framework.memory.unconstrained_memory import UnconstrainedMemory

from canvas_server.config import settings
from canvas_server.exceptions import ExecutionError
from canvas_server.tool_factory import compile_tool_from_code

logger = logging.getLogger("canvas_server.runner")

REACT_PATTERN = """**ReAct Pattern**
Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{actions}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question"""


class CanvasRunner:
    def __init__(self, canvas):
        self.canvas = canvas
        self.tools: dict[uuid.UUID, object] = {}
        self.agents: dict[uuid.UUID, ReActAgent] = {}
        self.node_map: dict[uuid.UUID, object] = {}

    async def setup(self):
        logger.info("Setting up canvas runner")
        for node in self.canvas.agent_nodes:
            self.node_map[node.id] = node
        await self._build_tools()
        await self._build_agents()
        logger.info("Setup complete: %d tools, %d agents", len(self.tools), len(self.agents))

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
                "  agent: id=%s name=%s type=%s model=%s tools=%d",
                agent_node.id, agent_node.name, agent_node.agent_type,
                agent_node.model_name, len(tools),
            )
            try:
                model_kwargs = {}
                if agent_node.model_name.startswith("ollama:"):
                    model_kwargs["base_url"] = settings.ollama_host
                llm = ChatModel.from_name(agent_node.model_name, **model_kwargs)
                agent = ReActAgent(
                    llm=llm,
                    tools=tools,
                    memory=UnconstrainedMemory(),
                )
                self.agents[agent_node.id] = agent
            except Exception as e:
                logger.error("  failed to build agent %s: %s", agent_node.name, e, exc_info=True)
        logger.info("Built %d agents successfully", len(self.agents))

    def _agent_name(self, agent_id: uuid.UUID) -> str:
        node = self.node_map.get(agent_id)
        return node.name if node else "Unknown"

    def _find_agent_id_by_name(self, name: str) -> uuid.UUID | None:
        for node in self.canvas.agent_nodes:
            if node.name == name:
                return node.id
        return None

    def _agent_prompt(self, agent_node, user_prompt: str) -> str:
        parts = []

        if agent_node.role:
            parts.append(f"You are: {agent_node.role}")

        if agent_node.agent_type == "router":
            handoff_targets = self._get_handoff_targets(agent_node.id)
            if handoff_targets:
                sub_agents = []
                for tid in handoff_targets:
                    target = self.node_map.get(tid)
                    if target:
                        desc = target.role or f"Agent: {target.name}"
                        sub_agents.append(f"- **{target.name}**: {desc}")
                if sub_agents:
                    parts.append(
                        "You are a Router agent. Your job is to analyze the user's request "
                        "and delegate it to the most appropriate sub-agent below. "
                        "Do NOT answer the question yourself — always route it.\n\n"
                        "Available sub-agents:\n" + "\n".join(sub_agents)
                    )

            action_names = []
            for t in self._get_agent_tools(agent_node.id):
                action_names.append(t.name)
            for tid in self._get_handoff_targets(agent_node.id):
                target = self.node_map.get(tid)
                if target:
                    action_names.append(f"transfer_to_{target.name}")

            react = REACT_PATTERN.format(actions=", ".join(action_names) if action_names else "none")
            parts.append(react)

        if agent_node.instructions:
            parts.append(agent_node.instructions)
        parts.append(user_prompt)
        return "\n\n".join(parts)

    def _extract_text(self, result) -> str:
        if hasattr(result, "iterations"):
            for iteration in reversed(result.iterations):
                if iteration.state and iteration.state.final_answer:
                    return iteration.state.final_answer
        if hasattr(result, "result"):
            msg = result.result
            if hasattr(msg, "text"):
                return msg.text
            if hasattr(msg, "content"):
                return str(msg.content)
        return str(result)

    async def _run_router_loop(self, agent_node, user_prompt, send_event):
        agent = self.agents[agent_node.id]
        base_prompt = self._agent_prompt(agent_node, user_prompt)
        accumulated_context = ""
        max_rounds = 10

        for round_num in range(max_rounds):
            agent.memory = UnconstrainedMemory()

            prompt = base_prompt
            if accumulated_context:
                prompt += f"\n\n---\nPrevious results:\n{accumulated_context}\n---\n\nBased on the above results, continue following the ReAct pattern."

            logger.info("Router %s round %d", agent_node.name, round_num + 1)

            result = await agent.run(prompt)
            text = self._extract_text(result)

            logger.info("Router %s round %d output: %s", agent_node.name, round_num + 1, text[:300])

            await send_event({"type": "thought", "agent": agent_node.name, "content": text})

            transfer_match = re.search(r'transfer_to_(\S+)', text)

            if transfer_match:
                target_name = transfer_match.group(1).rstrip(",:;")

                sub_task_match = re.search(r'transfer_to_\S+[:\s,]*\n?(.*)', text, re.DOTALL)
                sub_task = sub_task_match.group(1).strip() if sub_task_match and sub_task_match.group(1).strip() else user_prompt

                target_id = self._find_agent_id_by_name(target_name)

                if target_id and target_id in self.agents:
                    target_node = self.node_map[target_id]
                    sub_agent = self.agents[target_id]

                    await send_event({"type": "handoff", "from": agent_node.name, "to": target_name})
                    await send_event({"type": "agent_start", "agent": target_name, "agentType": target_node.agent_type})

                    sub_agent.memory = UnconstrainedMemory()
                    sub_prompt = self._agent_prompt(target_node, sub_task)

                    try:
                        sub_result = await sub_agent.run(sub_prompt)
                        obs = self._extract_text(sub_result)
                    except Exception as e:
                        obs = f"Error: {e}"
                        logger.error("Sub-agent %s failed: %s", target_name, e, exc_info=True)

                    accumulated_context += f"\nObservation from {target_name}: {obs}"

                    await send_event({"type": "final_answer", "agent": target_name, "content": obs})
                    await send_event({
                        "type": "tool_result",
                        "agent": agent_node.name,
                        "tool": f"transfer_to_{target_name}",
                        "output": obs,
                    })
                else:
                    accumulated_context += f"\nObservation: Error - agent '{target_name}' is not available."
            else:
                return text

        return "Router reached maximum rounds without producing a final answer."

    async def run(self, user_prompt: str, send_event):
        logger.info("Starting canvas execution: canvas_id=%s prompt=%s", self.canvas.id, user_prompt[:100])
        await self.setup()

        if not self.canvas.agent_nodes:
            logger.error("Canvas has no agent nodes")
            await send_event({"type": "error", "message": "Canvas has no agents to run."})
            return

        await send_event({"type": "run_start", "canvas_id": str(self.canvas.id)})

        agent_ids = [n.id for n in self.canvas.agent_nodes]
        first_agent_id = agent_ids[0]
        first_node = self.node_map[first_agent_id]

        if first_node.agent_type == "router":
            final_text = await self._run_router_loop(first_node, user_prompt, send_event)
            await send_event({
                "type": "final_answer",
                "agent": first_node.name,
                "content": final_text,
            })
        else:
            handoff_map = {}
            for agent_node in self.canvas.agent_nodes:
                handoff_map[agent_node.id] = self._get_handoff_targets(agent_node.id)

            current_agent_id = first_agent_id
            visited = set()

            while current_agent_id is not None and current_agent_id not in visited:
                visited.add(current_agent_id)
                agent = self.agents.get(current_agent_id)
                agent_node = self.node_map.get(current_agent_id)
                if not agent or not agent_node:
                    logger.warning("Agent not found: id=%s", current_agent_id)
                    break

                logger.info("Running agent: %s (type=%s model=%s)", agent_node.name, agent_node.agent_type, agent_node.model_name)
                await send_event({"type": "agent_start", "agent": agent_node.name, "agentType": agent_node.agent_type})

                prompt = self._agent_prompt(agent_node, user_prompt)

                try:
                    result = await agent.run(prompt)
                    text = self._extract_text(result)
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
