import uuid
import logging
import re

from pydantic import BaseModel, Field

from beeai_framework.agents.react import ReActAgent
from beeai_framework.backend.chat import ChatModel, _ChatModelKwargsAdapter
from beeai_framework.backend.message import UserMessage
from beeai_framework.context import RunContext
from beeai_framework.memory.unconstrained_memory import UnconstrainedMemory

from canvas_server.config import settings
from canvas_server.exceptions import ExecutionError
from canvas_server.tool_factory import compile_tool_from_code

_ChatModelKwargsAdapter.rebuild()

logger = logging.getLogger("canvas_server.runner")


class RouterDecision(BaseModel):
    thought: str = Field(description="Your reasoning about what to do next")
    action: str | None = Field(
        default=None,
        description="The transfer action to take, e.g. transfer_to_MathAgent. Null if giving a final answer.",
    )
    action_input: str | None = Field(
        default=None,
        description="The task/question to pass to the sub-agent. Null if giving a final answer.",
    )
    final_answer: str | None = Field(
        default=None,
        description="The final answer if no further routing is needed. Null if routing to a sub-agent.",
    )


class CanvasRunner:
    def __init__(self, canvas):
        self.canvas = canvas
        self.tools: dict[uuid.UUID, object] = {}
        self.agents: dict[uuid.UUID, ReActAgent] = {}
        self.llms: dict[uuid.UUID, object] = {}
        self.node_map: dict[uuid.UUID, object] = {}

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
                beeai_tool = await compile_tool_from_code(
                    tool_node.name, tool_node.code
                )
                self.tools[tool_node.id] = beeai_tool
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

    def _model_kwargs(self, agent_node) -> dict:
        kwargs = {}
        model = agent_node.model_name
        if model.startswith("ollama:"):
            kwargs["base_url"] = settings.llm_base_url
        return kwargs

    def _resolve_model_name(self, agent_node) -> str:
        if agent_node.agent_type == "router" and settings.llm_model_router:
            return settings.llm_model_router
        if agent_node.agent_type == "worker" and settings.llm_model_agent:
            return settings.llm_model_agent
        return agent_node.model_name

    async def _build_agents(self):
        logger.debug(
            "Building agents from %d agent nodes", len(self.canvas.agent_nodes)
        )
        for agent_node in self.canvas.agent_nodes:
            tools = self._get_agent_tools(agent_node.id)
            model_name = self._resolve_model_name(agent_node)
            logger.debug(
                "  agent: id=%s name=%s type=%s model=%s tools=%d",
                agent_node.id,
                agent_node.name,
                agent_node.agent_type,
                model_name,
                len(tools),
            )
            try:
                model_kwargs = self._model_kwargs(agent_node)
                llm = ChatModel.from_name(model_name, **model_kwargs)
                self.llms[agent_node.id] = llm

                agent = ReActAgent(
                    llm=llm,
                    tools=tools,
                    memory=UnconstrainedMemory(),
                )
                self.agents[agent_node.id] = agent
            except Exception as e:
                logger.error(
                    "  failed to build agent %s: %s", agent_node.name, e, exc_info=True
                )
        logger.info("Built %d agents successfully", len(self.agents))

    def _agent_name(self, agent_id: uuid.UUID) -> str:
        node = self.node_map.get(agent_id)
        return node.name if node else "Unknown"

    def _find_agent_id_by_name(self, name: str) -> uuid.UUID | None:
        for node in self.canvas.agent_nodes:
            if node.name == name:
                return node.id
        return None

    def _build_router_prompt(self, agent_node, user_prompt: str, observations: str = "") -> str:
        parts = []
        handoff_targets = self._get_handoff_targets(agent_node.id)
        action_names = [f"transfer_to_{self.node_map[tid].name}" for tid in handoff_targets if tid in self.node_map]

        tool_descriptions = []
        for tid in handoff_targets:
            target = self.node_map.get(tid)
            if target:
                desc = target.instructions or target.role or f"Handles tasks related to {target.name}"
                tool_descriptions.append(f"{target.name}: {desc}")

        parts.append(
            "Answer the following questions as best you can. "
            "You have access to the following sub-agents:\n\n"
            + "\n".join(tool_descriptions)
        )

        parts.append(
            "\nUse the following format:\n\n"
            "Question: the input question you must answer\n"
            "Thought: you should always think about what to do\n"
            "Action: the action to take, should be one of [" + ", ".join(action_names) + "]\n"
            "Action Input: the input to the action (the question to delegate)\n"
            "Observation: the result of the action\n"
            "... (this Thought/Action/Action Input/Observation can repeat N times)\n"
            "Thought: I now know the final answer\n"
            "Final Answer: the final answer to the original input question\n"
        )

        if agent_node.instructions:
            parts.append(agent_node.instructions)

        parts.append(f"Question: {user_prompt}")
        if observations:
            parts.append(observations)

        return "\n".join(parts)

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

    async def _call_llm(self, llm, prompt: str, response_format=None) -> str:
        kwargs = {}
        if response_format is not None:
            kwargs["response_format"] = response_format

        result = await llm.run([UserMessage(prompt)], **kwargs)

        if response_format is not None and hasattr(result, "output_structured") and result.output_structured is not None:
            return result.output_structured

        if hasattr(result, "get_text_content"):
            text = result.get_text_content()
            if text:
                return text
        if hasattr(result, "messages"):
            for msg in result.messages:
                if hasattr(msg, "text"):
                    return msg.text
        return str(result)

    def _parse_react_response(self, text: str) -> RouterDecision:
        """Parse a text ReAct response into a RouterDecision."""
        thought = ""
        action = None
        action_input = None
        final_answer = None

        thought_match = re.search(r"Thought:\s*(.+)", text, re.IGNORECASE)
        if thought_match:
            thought = thought_match.group(1).strip()

        action_match = re.search(r"Action:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        if action_match:
            action = action_match.group(1).strip()
            if not action.startswith("transfer_to_"):
                action = None

        ai_match = re.search(r"Action Input:\s*(.+)", text, re.IGNORECASE)
        if ai_match:
            action_input = ai_match.group(1).strip()

        fa_match = re.search(r"Final Answer:\s*(.+)", text, re.IGNORECASE)
        if fa_match:
            final_answer = fa_match.group(1).strip()

        if not thought and not action and not final_answer:
            thought = text[:100]

        return RouterDecision(
            thought=thought,
            action=action,
            action_input=action_input,
            final_answer=final_answer,
        )

    async def _run_router_loop(self, agent_node, user_prompt: str, send_event):
        llm = self.llms[agent_node.id]
        observations = ""
        max_rounds = 10

        for round_num in range(max_rounds):
            prompt = self._build_router_prompt(agent_node, user_prompt, observations)
            logger.info("Router %s round %d", agent_node.name, round_num + 1)
            logger.debug("Router prompt: %s", prompt)

            decision = None
            for attempt in range(2):
                use_structured = attempt == 0
                try:
                    fmt = RouterDecision if use_structured else None
                    result = await self._call_llm(llm, prompt, response_format=fmt)
                except Exception as e:
                    logger.error("Router call failed: %s", e, exc_info=True)
                    if use_structured:
                        continue
                    await send_event({"type": "error", "message": f"Router error: {e}"})
                    return f"Router failed: {e}"

                if use_structured and isinstance(result, RouterDecision):
                    decision = result
                    break
                elif not use_structured and isinstance(result, str):
                    decision = self._parse_react_response(result)
                    break
                elif isinstance(result, RouterDecision):
                    decision = result
                    break

            if decision is None:
                await send_event({"type": "error", "message": "Router could not parse response"})
                return "Router failed: could not parse response"

            logger.info(
                "Router %s round %d decision: thought=%s action=%s",
                agent_node.name,
                round_num + 1,
                decision.thought[:100],
                decision.action,
            )

            await send_event({
                "type": "thought",
                "agent": agent_node.name,
                "content": decision.thought,
            })

            if decision.final_answer:
                return decision.final_answer

            if decision.action:
                target_name = None
                if decision.action.startswith("transfer_to_"):
                    target_name = decision.action[len("transfer_to_"):]

                if not target_name:
                    observations += f"\nObservation: Unknown action '{decision.action}'. Use one of the valid transfer_to_X actions.\n"
                    continue

                sub_task = decision.action_input or user_prompt
                target_id = self._find_agent_id_by_name(target_name)

                if target_id and target_id in self.agents:
                    target_node = self.node_map[target_id]
                    sub_agent = self.agents[target_id]

                    await send_event({
                        "type": "handoff",
                        "from": agent_node.name,
                        "to": target_name,
                    })
                    await send_event({
                        "type": "agent_start",
                        "agent": target_name,
                        "agentType": target_node.agent_type,
                    })

                    sub_agent.memory = UnconstrainedMemory()
                    sub_prompt = self._build_worker_prompt(target_node, sub_task)

                    try:
                        result = await sub_agent.run(sub_prompt)
                        obs = self._extract_text(result)
                    except Exception as e:
                        obs = f"Error: {e}"
                        logger.error("Sub-agent %s failed: %s", target_name, e, exc_info=True)

                    observations += f"\nThought: {decision.thought}\n"
                    observations += f"Action: {decision.action}\n"
                    observations += f"Action Input: {decision.action_input or ''}\n"
                    observations += f"Observation: {obs}\n"

                    await send_event({
                        "type": "final_answer",
                        "agent": target_name,
                        "content": obs,
                    })
                    await send_event({
                        "type": "tool_result",
                        "agent": agent_node.name,
                        "tool": f"transfer_to_{target_name}",
                        "output": obs,
                    })
                else:
                    observations += f"\nObservation: Agent '{target_name}' is not available.\n"

            else:
                observations += "\nObservation: You must provide either an action or a final_answer. Neither was set.\n"

        return "Router reached maximum rounds without producing a final answer."

    def _build_worker_prompt(self, agent_node, user_prompt: str) -> str:
        parts = []
        if agent_node.role:
            parts.append(f"You are: {agent_node.role}")
        if agent_node.instructions:
            parts.append(agent_node.instructions)
        parts.append(user_prompt)
        return "\n\n".join(parts)

    async def run(self, user_prompt: str, send_event):
        logger.info(
            "Starting canvas execution: canvas_id=%s prompt=%s",
            self.canvas.id,
            user_prompt[:100],
        )
        await self.setup()

        if not self.canvas.agent_nodes:
            logger.error("Canvas has no agent nodes")
            await send_event(
                {"type": "error", "message": "Canvas has no agents to run."}
            )
            return

        await send_event({"type": "run_start", "canvas_id": str(self.canvas.id)})

        agent_ids = [n.id for n in self.canvas.agent_nodes]
        first_node = self.node_map[agent_ids[0]]

        if first_node.agent_type == "router":
            final_text = await self._run_router_loop(
                first_node, user_prompt, send_event
            )
            await send_event(
                {
                    "type": "final_answer",
                    "agent": first_node.name,
                    "content": final_text,
                }
            )
        else:
            handoff_map = {}
            for agent_node in self.canvas.agent_nodes:
                handoff_map[agent_node.id] = self._get_handoff_targets(agent_node.id)

            current_agent_id = agent_ids[0]
            visited = set()

            while current_agent_id is not None and current_agent_id not in visited:
                visited.add(current_agent_id)
                agent = self.agents.get(current_agent_id)
                agent_node = self.node_map.get(current_agent_id)
                if not agent or not agent_node:
                    logger.warning("Agent not found: id=%s", current_agent_id)
                    break

                logger.info(
                    "Running agent: %s (type=%s model=%s)",
                    agent_node.name,
                    agent_node.agent_type,
                    agent_node.model_name,
                )
                await send_event(
                    {
                        "type": "agent_start",
                        "agent": agent_node.name,
                        "agentType": agent_node.agent_type,
                    }
                )

                prompt = self._build_worker_prompt(agent_node, user_prompt)

                try:
                    result = await agent.run(prompt)
                    text = self._extract_text(result)
                    logger.info(
                        "Agent %s completed: result=%s", agent_node.name, text[:200]
                    )
                    await send_event(
                        {
                            "type": "final_answer",
                            "agent": agent_node.name,
                            "content": text,
                        }
                    )
                except Exception as e:
                    logger.error(
                        "Agent %s failed: %s", agent_node.name, e, exc_info=True
                    )
                    await send_event(
                        {
                            "type": "error",
                            "message": str(e),
                            "agent": agent_node.name,
                        }
                    )

                handoff_targets = handoff_map.get(current_agent_id, [])
                next_agent_id = handoff_targets[0] if handoff_targets else None

                if next_agent_id and next_agent_id != current_agent_id:
                    next_name = self._agent_name(next_agent_id)
                    logger.info("Handoff: %s -> %s", agent_node.name, next_name)
                    await send_event(
                        {
                            "type": "handoff",
                            "from": agent_node.name,
                            "to": next_name,
                        }
                    )

                current_agent_id = next_agent_id

        logger.info("Canvas execution completed: canvas_id=%s", self.canvas.id)
        await send_event(
            {"type": "run_complete", "result": "Workflow execution completed."}
        )
