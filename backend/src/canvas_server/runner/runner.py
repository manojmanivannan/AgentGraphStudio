"""CanvasRunner — the core orchestrator for canvas-based agent execution.

After the big modularisation, ``CanvasRunner`` is a thin orchestrator that:
  * Owns shared mutable state (agent instances, node map, event wiring set).
  * Delegates domain work to extracted services:
      - ``ToolRegistry`` — compiles tools, maps name→id
      - ``EdgeGraph`` — navigates the canvas edge graph
      - ``MemoryManager`` — shared mem0 lifecycle, per-agent providers
      - ``ConversationService`` — message persistence and history formatting
      - ``AgentFactory`` — builds StreamingReAct agents
      - ``ExecutionStrategy`` (Router/Worker/Chain)
"""

from __future__ import annotations

import logging
import os
import re
import sys
import uuid

import dspy
import mlflow

from canvas_server.config import settings
from canvas_server.exceptions import LLMConfigurationError
from canvas_server.package_manager import PackageManager
from canvas_server.runner.agent_factory import AgentFactory
from canvas_server.runner.config import RunContext
from canvas_server.runner.conversation import ConversationService
from canvas_server.runner.edge_graph import EdgeGraph
from canvas_server.runner.execution import (
    ChainExecution,
    ExecutionStrategy,
    RouterExecution,
    StrategyServices,
    WorkerExecution,
)
from canvas_server.runner.handoff import HandoffToolBuilder
from canvas_server.runner.memory import MemoryManager
from canvas_server.runner.tool_registry import ToolRegistry

logger = logging.getLogger("canvas_server.runner")


class CanvasRunner:
    """Orchestrates a canvas execution run.

    All services are created during ``__init__`` (they are lightweight wrappers).
    ``setup()`` performs the actual work: compiling tools, building worker
    agents.  This lets tests mock ``setup()`` and inject state directly.
    """

    def __init__(self, canvas, conversation_repo=None, conversation_id=None):
        self.canvas = canvas

        # ---- mutable run-time state (owned here, shared with services) ----
        self.tools: dict[uuid.UUID, object] = {}
        self._tool_name_to_id: dict[str, uuid.UUID] = {}
        self.agents: dict[uuid.UUID, object] = {}
        self._wired_agents: set[uuid.UUID] = set()
        self._node_map: dict[uuid.UUID, object] = {}

        # ---- LM (cheap to construct, needs no I/O) ----
        self._lm = dspy.LM(
            settings.llm_model,
            api_base=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )

        # ---- services ----
        self._tool_registry = ToolRegistry()
        self._edge_graph = EdgeGraph(self.canvas.edges if self.canvas else [])
        self._memory_manager = MemoryManager()
        self._conversation = ConversationService(
            conversation_repo=conversation_repo,
            conversation_id=conversation_id,
        )
        self._agent_factory = AgentFactory(
            lm=self._lm,
            tool_registry=self._tool_registry,
            memory_manager=self._memory_manager,
            edges=self.canvas.edges if self.canvas else [],
            agent_names={node.id: node.name for node in self.canvas.agent_nodes} if self.canvas else {},
        )
        self._handoff_tool_builder = HandoffToolBuilder(
            agents=self.agents,
            node_map=self.node_map,
            agent_factory=self._agent_factory,
            conversation_service=self._conversation,
            attach_events=self._attach_events,
        )

    # -- backward-compat properties so existing tests don't break ----------

    @property
    def node_map(self) -> dict[uuid.UUID, object]:
        return self._node_map

    @node_map.setter
    def node_map(self, value: dict[uuid.UUID, object]):
        self._node_map = value
        if hasattr(self, "_handoff_tool_builder"):
            self._handoff_tool_builder.node_map = value

    @property
    def conversation_repo(self):
        return self._conversation.conversation_repo

    @conversation_repo.setter
    def conversation_repo(self, value):
        self._conversation.conversation_repo = value

    @property
    def conversation_id(self):
        return self._conversation.conversation_id

    @conversation_id.setter
    def conversation_id(self, value):
        self._conversation.conversation_id = value

    async def generate_conversation_title(self, user_prompt: str) -> str | None:
        if not user_prompt or not user_prompt.strip():
            return None

        prompt = (
            "Create a concise chat title from the user's first question below. "
            "Reply with only the title in 3-8 words, with no explanation, quotes, or extra punctuation.\n\n"
            f"User question: {user_prompt.strip()}"
        )

        try:
            with dspy.context(lm=self._lm):
                result = await self._lm.acall(prompt=prompt)
        except Exception as exc:
            logger.warning(
                "Failed to generate conversation title: %s", exc, exc_info=True
            )
            return None

        title = None
        if isinstance(result, list) and result:
            first = result[0]
            title = (
                first.get("content") or first.get("text")
                if isinstance(first, dict)
                else str(first)
            )
        else:
            title = str(result)

        if not title:
            return None

        title = title.splitlines()[0].strip()
        title = title.strip(" \"'")
        title = re.sub(r"[.?!]+$", "", title)
        title = re.sub(r"\s+", " ", title)
        if len(title) > 100:
            title = title[:100].rstrip(" .?!")

        return title or None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def setup(self, send_event=None):
        """Initialise all services and build worker agents.

        Called at the start of every ``run()``.  Idempotent-ish: if a
        previous ``setup()`` already built tools and workers, building again
        is cheap (but currently we always re-build).
        """
        logger.info("Setting up canvas runner")

        # Proactively validate LLM configuration (skipped in unit tests unless TEST_VALIDATE_LLM is set)
        if "pytest" not in sys.modules or os.environ.get("TEST_VALIDATE_LLM"):
            try:
                await self._lm.acall(prompt="Test connection. Respond with 'ok'.", max_tokens=5)
            except Exception as e:
                err_details = str(e)
                if "<html" in err_details.lower() or "<!doctype" in err_details.lower():
                    err_details = (
                        "LLM/API returned an HTML error page. "
                        "Please check that your server URL, credentials, and settings are correct."
                    )
                elif len(err_details) > 300:
                    err_details = err_details[:300] + "..."
                err_msg = (
                    f"LLM configuration is incorrect. Please check your LLM settings "
                    f"(model name: '{settings.llm_model}', base URL: '{settings.llm_base_url}', "
                    f"API key: '{'***' if settings.llm_api_key else 'None'}').\n"
                    f"Details: {err_details}"
                )
                logger.error("LLM configuration validation failed: %s", err_msg)
                raise LLMConfigurationError(err_msg) from e

        # Build the node map for fast lookups
        for node in self.canvas.agent_nodes:
            self.node_map[node.id] = node

        # Install tool dependencies in the sandbox before compiling tools
        await self._install_dependencies(self.canvas.tool_nodes)

        self._tool_registry = ToolRegistry()
        await self._tool_registry.compile_all(self.canvas.tool_nodes)
        # Sync tool state up to the runner for backward-compat access
        self.tools = self._tool_registry.tools
        self._tool_name_to_id = self._tool_registry._tool_name_to_id

        self._edge_graph = EdgeGraph(self.canvas.edges)
        self._memory_manager = MemoryManager()

        # Eagerly initialize memory providers for all agents that need them to check for configuration errors
        for node in self.canvas.agent_nodes:
            if self._memory_manager.needs_memory(node):
                self._memory_manager.build_provider(node)

        self._agent_factory = AgentFactory(
            lm=self._lm,
            tool_registry=self._tool_registry,
            memory_manager=self._memory_manager,
            edges=self.canvas.edges,
            agent_names={node.id: node.name for node in self.canvas.agent_nodes},
        )

        # Build worker agents (routers are built lazily at run time)
        self.agents = await self._agent_factory.build_workers(self.canvas.agent_nodes)

        self._handoff_tool_builder = HandoffToolBuilder(
            agents=self.agents,
            node_map=self.node_map,
            agent_factory=self._agent_factory,
            conversation_service=self._conversation,
            attach_events=self._attach_events,
        )

        # Alert if memory provider failed to initialize but proceed with LLM anyway
        if self._memory_manager.initialization_error:
            warn_msg = (
                f"Memory/Message configuration is wrong, memory will not work. Proceeding with LLM anyway. "
                f"(Error: {self._memory_manager.initialization_error})"
            )
            logger.warning(warn_msg)
            if send_event:
                await send_event({
                    "type": "warning",
                    "message": warn_msg
                })
            # Persist the warning so it is loaded on page refresh
            await self._conversation.persist_message(
                role="system",
                content=warn_msg,
                event_type="warning"
            )

        logger.info(
            "Setup complete: %d tools, %d agents",
            len(self.tools),
            len(self.agents),
        )

    async def _install_dependencies(self, tool_nodes):
        """Collect and install all unique package dependencies from tool nodes."""
        all_packages = set()
        for tool_node in tool_nodes:
            if hasattr(tool_node, "dependencies") and tool_node.dependencies:
                for pkg in tool_node.dependencies:
                    pkg = pkg.strip()
                    if pkg:
                        all_packages.add(pkg)

        if all_packages:
            pm = PackageManager()
            logger.info(
                "Installing tool dependencies: %s",
                sorted(all_packages),
            )
            try:
                await pm.install_packages(sorted(all_packages))
                logger.info("Tool dependencies installed successfully")
            except Exception as e:
                logger.error("Failed to install tool dependencies: %s", e)
                raise

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def _attach_events(self, agent_id: uuid.UUID, send_event, force=False):
        """Wire event callbacks on *agent_id* so StreamingReAct events flow
        to ``send_event``.  Idempotent — agents are only wired once."""
        if agent_id in self._wired_agents and not force:
            return
        agent = self.agents.get(agent_id)
        agent_node = self.node_map.get(agent_id)
        if agent and agent_node:
            self._wired_agents.add(agent_id)
            tool_name_to_id = self._tool_name_to_id

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
                    await self._conversation.persist_message(
                        role="assistant",
                        content=event.get("content", ""),
                        agent_name=aname,
                        node_id=aid,
                        event_type="thought",
                    )
                elif event.get("type") == "tool_result":
                    tool_name = event.get("tool", "")
                    clean_tool_name = (
                        tool_name.replace("transfer_to_", "") if tool_name else aname
                    )
                    await self._conversation.persist_message(
                        role="assistant",
                        content=event.get("output", ""),
                        agent_name=clean_tool_name,
                        node_id=aid,
                        event_type="tool_result",
                    )

            agent.on_event(callback)


    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def _event(self, type_: str, **kwargs) -> dict:
        kwargs["type"] = type_
        return kwargs

    def _resolve_strategy(self, target_agent_id) -> ExecutionStrategy:
        """Build the appropriate execution strategy from the services context."""
        services = StrategyServices(
            agents=self.agents,
            node_map=self.node_map,
            agent_factory=self._agent_factory,
            conversation_service=self._conversation,
            edge_graph=self._edge_graph,
            memory_manager=self._memory_manager,
            tool_registry=self._tool_registry,
            attach_events=self._attach_events,
            handoff_tool_builder=self._handoff_tool_builder,
        )

        if target_agent_id is not None:
            agent_node = self.node_map.get(target_agent_id)
            if agent_node and agent_node.agent_type == "router":
                return RouterExecution(services)
            return WorkerExecution(services)

        # No target agent: inspect the first agent's type
        # Routers aren't built during setup() — they're built lazily by
        # RouterExecution, so we must pick the right strategy here.
        agent_ids = [n.id for n in self.canvas.agent_nodes]
        first_node = self.node_map.get(agent_ids[0]) if agent_ids else None
        if first_node and first_node.agent_type == "router":
            return RouterExecution(services)

        # Legacy chain strategy for worker-only canvases
        return ChainExecution(services)

    @mlflow.trace(
        name="canvas_run", span_type="CHAIN", attributes={"component": "agent"}
    )
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
        await self.setup(send_event=send_event)

        if not self.canvas.agent_nodes:
            logger.error("Canvas has no agent nodes")
            await send_event(
                self._event("error", message="Canvas has no agents to run.")
            )
            return None

        await send_event(self._event("run_start", canvas_id=str(self.canvas.id)))

        # ---- Load conversation history ----
        history_messages = await self._conversation.load_messages()
        agent_ids = [n.id for n in self.canvas.agent_nodes]

        first_agent_id = (
            target_agent_id
            if target_agent_id
            else (agent_ids[0] if agent_ids else None)
        )

        history_enabled_node_ids = {
            n.id
            for n in self.canvas.agent_nodes
            if self._agent_factory.needs_history(n)
        }

        await self._conversation.persist_message(
            role="user",
            content=user_prompt,
            event_type="run_start",
        )

        history_text, dspy_history = (
            self._conversation.build_conversation_history_context(
                history_messages, history_enabled_node_ids
            )
        )

        ctx = RunContext(
            user_prompt=user_prompt,
            send_event=send_event,
            target_agent_id=target_agent_id,
            history_text=history_text,
            dspy_history=dspy_history,
            history_enabled_node_ids=history_enabled_node_ids,
            primary_agent_id=first_agent_id,
        )

        # ---- Execute ---
        strategy = self._resolve_strategy(target_agent_id)
        first_id = (
            target_agent_id
            if target_agent_id
            else (agent_ids[0] if agent_ids else None)
        )

        final_text = None
        with dspy.context(lm=self._lm):
            final_text = await strategy.execute(first_id, ctx)

        # ---- Append turn to dspy.History ----
        if dspy_history is not None and final_text:
            dspy_history.messages.append(
                {"user_request": user_prompt, "process_result": final_text}
            )



        logger.info("Canvas execution completed: canvas_id=%s", self.canvas.id)
        await send_event(
            self._event("run_complete", result="Workflow execution completed.")
        )
        return final_text
