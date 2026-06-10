"""HandoffToolBuilder — constructs handoff tools for agent delegation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable

logger = logging.getLogger("canvas_server.runner.handoff")


class HandoffToolBuilder:
    """Consolidates the creation of handoff and parallel handoff tools.

    Encapsulates all interaction with canvas runner services needed at
    execution/tool-call time, avoiding circular references and callback passing.
    """

    def __init__(
        self,
        agents: dict[uuid.UUID, object],
        node_map: dict[uuid.UUID, object],
        agent_factory,
        conversation_service,
        attach_events: Callable[[uuid.UUID, Callable, bool], None],
    ):
        self.agents = agents
        self.node_map = node_map
        self.agent_factory = agent_factory
        self.conversation_service = conversation_service
        self.attach_events = attach_events

    def make_handoff_tool(
        self,
        target_id: uuid.UUID,
        router_name: str,
        send_event,
        history: str,
        dspy_history=None,
    ) -> Callable[[str], asyncio.Future[str]]:
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
                    await self.agent_factory.build_router(
                        target_node,
                        self.agents,
                        router_name,
                        send_event,
                        history,
                        dspy_history,
                        self,
                    )
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
            await self.conversation_service.persist_message(
                role="system",
                content=f"Delegating to {target_name}...",
                agent_name=router_name,
                node_id=target_id,
                event_type="handoff",
            )
            await send_event(
                {
                    "type": "agent_start",
                    "agent": target_name,
                    "agentType": target_node.agent_type,
                    "node_id": str(target_id),
                }
            )

            if getattr(target_node, "enable_rag", False):
                target_agent = await self.agent_factory.assemble_rag_worker(
                    agent_node=target_node,
                    task=task,
                    conversation_service=self.conversation_service,
                    send_event=send_event,
                )
                self.agents[target_id] = target_agent
                self.attach_events(target_id, send_event, force=True)
            else:
                self.attach_events(target_id, send_event)

            prompt = self.agent_factory.build_worker_prompt(task, history)
            try:
                needs_history = self.agent_factory.needs_history(target_node)
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

            await self.conversation_service.persist_message(
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

    def make_parallel_handoff_tool(
        self,
        handoff_targets: list[uuid.UUID],
        router_name: str,
        send_event,
        history: str,
        dspy_history=None,
    ) -> Callable[[list[dict]], asyncio.Future[str]]:
        """Create a DSPy tool function that delegates to multiple sub-agents in parallel."""
        # Pre-build individual handoff tools for each target so we can invoke them easily
        handoff_tool_map = {}
        for target_id in handoff_targets:
            target_node = self.node_map.get(target_id)
            if target_node:
                handoff_tool_map[target_node.name] = self.make_handoff_tool(
                    target_id, router_name, send_event, history, dspy_history
                )

        async def execute_parallel_agents(agents_and_inputs: list[dict]) -> str:
            """Run multiple downstream worker agents in parallel and return their combined findings.

            Args:
                agents_and_inputs: A list of dicts, where each dict has:
                  - "agent_name": The exact name of the target agent to run (e.g. "Researcher", "Writer").
                  - "task": The specific task or input prompt for that agent.

            Example:
                execute_parallel_agents([
                    {"agent_name": "Researcher", "task": "analyze trends"},
                    {"agent_name": "Writer", "task": "draft post"}
                ])
            """
            if not isinstance(agents_and_inputs, list):
                return "Error: agents_and_inputs must be a list of dictionaries."

            tasks = []
            for item in agents_and_inputs:
                if not isinstance(item, dict):
                    return "Error: Each item in agents_and_inputs must be a dictionary."
                name = item.get("agent_name") or item.get("agent")
                task_prompt = item.get("task") or item.get("input")
                if not name or not task_prompt:
                    return "Error: Each item in agents_and_inputs must contain 'agent_name' and 'task'."

                if name not in handoff_tool_map:
                    available = list(handoff_tool_map.keys())
                    return f"Error: Agent '{name}' is not an available handoff target. Available targets: {available}"

                tool_fn = handoff_tool_map[name]
                tasks.append((name, tool_fn(task_prompt)))

            if not tasks:
                return "Error: No valid tasks to execute."

            names = [t[0] for t in tasks]
            coroutines = [t[1] for t in tasks]
            results = await asyncio.gather(*coroutines, return_exceptions=True)

            findings = []
            for name, result in zip(names, results, strict=False):
                if isinstance(result, Exception):
                    findings.append(f"Agent '{name}' failed with error: {result}")
                else:
                    findings.append(f"Agent '{name}' findings:\n{result}")

            return "\n\n".join(findings)

        execute_parallel_agents.__name__ = "execute_parallel_agents"
        return execute_parallel_agents
