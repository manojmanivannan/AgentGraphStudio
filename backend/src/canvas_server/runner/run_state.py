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

    Maintains the lookup tables for nodes and compiled agent instances. It holds
    ephemeral run context (like websocket callbacks and conversation history)
    and acts as the centralized point for lazily compiling agents or wiring
    event callbacks just-in-time before an agent executes.

    Attributes:
        canvas: The source Canvas ORM model.
        agent_factory (AgentFactory): The factory for building DSPy agents.
        conversation_service (ConversationService): Service for saving messages.
        tool_registry (ToolRegistry): Compiled python sandbox tools.
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
        self.get_client_response: Callable | None = None

    def set_run_context(
        self,
        user_prompt: str,
        send_event: Callable,
        history_text: str,
        dspy_history: Any,
    ):
        """Configures ephemeral fields for the duration of a single execution run.

        Args:
            user_prompt (str): The raw input message from the user.
            send_event (Callable): Async callback to stream events over websocket.
            history_text (str): Serialized conversation history for prompt injection.
            dspy_history (Any): Native DSPy history list.
        """
        self.user_prompt = user_prompt
        self.send_event = send_event
        self.history_text = history_text
        self.dspy_history = dspy_history

    async def get_or_build_agent(self, agent_id: uuid.UUID, task: str | None = None):
        """Retrieves or dynamically builds an agent instance for execution.

        This method handles three distinct compilation pathways:
        1. **RAG Workers**: Recompiled dynamically per-turn to embed the user's
           specific query and retrieve relevant document passages.
        2. **Routers**: Built lazily on first invocation because they require
           active `send_event` callbacks bound to their handoff tools.
        3. **Standard Workers**: Retrieved directly from the eager-compilation
           cache populated during runner setup.

        Args:
            agent_id (uuid.UUID): The UUID of the requested agent node.
            task (str | None, optional): Specific task query (used for RAG similarity search).

        Returns:
            StreamingReAct: The fully compiled and wired agent instance.

        Raises:
            ValueError: If the agent node ID does not exist in the graph.
            RuntimeError: If handoff tools or dependencies are missing.
        """
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
        """Wires event callbacks to the agent's StreamingReAct loop.

        This ensures that intermediate steps (thoughts, tool invocations) are
        intercepted and forwarded to both the UI (via `send_event`) and the
        database (via `conversation_service.persist_message`).

        It is idempotent by default to prevent double-wiring agents that stay
        alive across multiple conversation turns.

        Args:
            agent_id (uuid.UUID): The UUID of the agent to wire.
            force (bool, optional): If True, bypasses the idempotency check
                (required when an agent is recompiled dynamically, e.g. RAG).
        """
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
                event_type = event.get("type")

                if event_type == "tool_start":
                    tool_name = event.get("tool", "")
                    tool_node_id = tool_name_to_id.get(tool_name)
                    await send_event(
                        {
                            "agent": aname,
                            "node_id": str(aid),
                            **event,
                        }
                    )
                    if tool_node_id:
                        await send_event(
                            {
                                "type": "tool_start",
                                "tool": tool_name,
                                "node_id": str(tool_node_id),
                            }
                        )
                    return

                if event_type == "tool_result":
                    tool_name = event.get("tool", "")
                    classification = classify_tool_result(
                        tool_name=tool_name,
                        fallback_agent_name=aname,
                    )
                    tool_node_id = tool_name_to_id.get(tool_name)
                    resolved_node_id = tool_node_id or aid

                    await send_event(
                        {
                            "agent": aname,
                            "node_id": str(resolved_node_id),
                            **event,
                        }
                    )

                    persisted_role = "assistant" if classification.event_type == "response" else "tool"
                    await self.conversation_service.persist_message(
                        role=persisted_role,
                        content=event.get("output", ""),
                        agent_name=classification.agent_name,
                        node_id=resolved_node_id,
                        event_type=classification.event_type,
                        tool=tool_name,
                        args=event.get("input") or event.get("args"),
                    )
                    return

                await send_event({"agent": aname, "node_id": str(aid), **event})

                if event_type == "thought":
                    await self.conversation_service.persist_message(
                        role="assistant",
                        content=event.get("content", ""),
                        agent_name=aname,
                        node_id=aid,
                        event_type="thought",
                    )
                elif event_type == "tool_approval_request":
                    await self.conversation_service.persist_message(
                        role="tool",
                        content=f"Tool approval required: {event.get('tool', '')}",
                        agent_name=aname,
                        node_id=event.get("node_id") or aid,
                        event_type="tool_approval_request",
                        tool=event.get("tool"),
                        args=event.get("args"),
                    )

            agent.on_event(callback)
