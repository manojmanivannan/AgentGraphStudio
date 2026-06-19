from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from canvas_server.runner.agent_factory import AgentFactory
    from canvas_server.runner.conversation import ConversationService
    from canvas_server.runner.handoff import HandoffToolBuilder
    from canvas_server.runner.tool_registry import ToolRegistry

from canvas_server.runner.transcript_classifier import classify_tool_result

logger = logging.getLogger("canvas_server.runner.run_state")


class CanvasRunState:
    """Encapsulates the mutable runtime state for a canvas execution.

    Maintains:
      * node_map — lookup table of active AgentNodes by ID
      * agents — dictionary of active StreamingReAct instances
      * wired_agents — set of agent IDs that have attached event listeners
      * run-specific context fields (user_prompt, send_event, history)

    Provides:
      * get_or_build_agent — resolves agent lookup, lazy router compilation,
        and dynamic RAG assembly.
      * attach_events — wires event logging and message persistence callbacks.
    """

    def __init__(
        self,
        canvas,
        agent_factory: AgentFactory,
        conversation_service: ConversationService,
        tool_registry: ToolRegistry,
    ):
        self.canvas = canvas
        self.agent_factory = agent_factory
        self.conversation_service = conversation_service
        self.tool_registry = tool_registry

        # Runtime collections
        self.node_map: dict[uuid.UUID, Any] = {}
        self.agents: dict[uuid.UUID, Any] = {}
        self.wired_agents: set[uuid.UUID] = set()

        # Injected dependencies resolved at setup time
        self.handoff_tool_builder: HandoffToolBuilder | None = None

        # Ephemeral fields configured at run start
        self.user_prompt: str = ""
        self.send_event: Callable | None = None
        self.history_text: str = ""
        self.dspy_history: Any = None

    def set_run_context(
        self,
        user_prompt: str,
        send_event: Callable,
        history_text: str,
        dspy_history: Any,
    ):
        """Configure ephemeral fields for the duration of a single run() call."""
        self.user_prompt = user_prompt
        self.send_event = send_event
        self.history_text = history_text
        self.dspy_history = dspy_history

    async def get_or_build_agent(self, agent_id: uuid.UUID, task: str | None = None):
        """Retrieve the agent instance, building or wiring it based on agent type and settings."""
        agent_node = self.node_map.get(agent_id)
        if not agent_node:
            raise ValueError(f"Agent node not found: id={agent_id}")

        handoff_targets = await self.agent_factory._get_handoff_target_ids(agent_id)

        # If RAG is enabled on a worker agent, assemble it dynamically
        if getattr(agent_node, "enable_rag", False):
            query = task if task is not None else self.user_prompt
            agent = await self.agent_factory.assemble_rag_worker(
                agent_node=agent_node,
                task=query,
                conversation_service=self.conversation_service,
                send_event=self.send_event,
                handoff_tool_builder=self.handoff_tool_builder,
                history_text=self.history_text,
                dspy_history=self.dspy_history,
            )
            self.agents[agent_id] = agent
            self.attach_events(agent_id, force=True)
            return agent

        # If it is a router agent, compile it lazily if it doesn't exist yet
        if agent_node.agent_type == "router":
            if agent_id not in self.agents:
                if not self.handoff_tool_builder:
                    raise RuntimeError("HandoffToolBuilder must be set on run state before resolving routers")
                agent = await self.agent_factory.build_router(
                    agent_node=agent_node,
                    existing_agents=self.agents,
                    router_name=agent_node.name,
                    send_event=self.send_event,
                    history_text=self.history_text,
                    dspy_history=self.dspy_history,
                    handoff_tool_builder=self.handoff_tool_builder,
                )
                self.agents[agent_id] = agent
            self.attach_events(agent_id)
            return self.agents[agent_id]

        # Standard worker agent with handoff targets needs to be rebuilt dynamically to bind handoff tools
        if handoff_targets:
            if not self.handoff_tool_builder:
                raise RuntimeError("HandoffToolBuilder must be set on run state before resolving handoff targets")
            agent = await self.agent_factory.build_worker(
                agent_node=agent_node,
                handoff_tool_builder=self.handoff_tool_builder,
                send_event=self.send_event,
                history_text=self.history_text,
                dspy_history=self.dspy_history,
            )
            self.agents[agent_id] = agent
            self.attach_events(agent_id, force=True)
            return agent

        # Standard worker agent (eagerly compiled during setup)
        agent = self.agents.get(agent_id)
        if not agent:
            raise RuntimeError(
                f"Worker agent '{agent_node.name}' (id={agent_id}) not found in agents. Make sure setup() was called."
            )
        self.attach_events(agent_id)
        return agent

    def attach_events(self, agent_id: uuid.UUID, force: bool = False):
        """Wire event callbacks on *agent_id* so StreamingReAct events flow
        to ``send_event``. Idempotent unless force=True."""
        if not self.send_event:
            return
        if agent_id in self.wired_agents and not force:
            return

        agent = self.agents.get(agent_id)
        agent_node = self.node_map.get(agent_id)
        if agent and agent_node:
            self.wired_agents.add(agent_id)
            tool_name_to_id = self.tool_registry._tool_name_to_id
            send_event = self.send_event

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
                elif event.get("type") == "thought":
                    await self.conversation_service.persist_message(
                        role="assistant",
                        content=event.get("content", ""),
                        agent_name=aname,
                        node_id=aid,
                        event_type="thought",
                    )
                elif event.get("type") == "tool_result":
                    tool_name = event.get("tool", "")
                    classification = classify_tool_result(
                        tool_name=tool_name,
                        fallback_agent_name=aname,
                    )
                    await self.conversation_service.persist_message(
                        role="assistant",
                        content=event.get("output", ""),
                        agent_name=classification.agent_name,
                        node_id=aid,
                        event_type=classification.event_type,
                    )

            agent.on_event(callback)
