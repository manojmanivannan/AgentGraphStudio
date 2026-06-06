"""ToolRegistry — compiles tool nodes and resolves per-agent tool lists."""

from __future__ import annotations

import logging
import uuid

from canvas_server.tool_factory import compile_tool_from_code

logger = logging.getLogger("canvas_server.runner.tool_registry")


class ToolRegistry:
    """Compiles ``ToolNode.code`` strings into callable functions and maintains
    the reverse mapping from tool name to node ID.

    State owned by this service:
      ``tools`` — ``{node_id: callable}`` for all compiled tools
      ``_tool_name_to_id`` — ``{tool_name: node_id}`` used by ``_attach_events``
        to resolve tool names to canonical node IDs (for canvas highlighting).
    """

    def __init__(self):
        self.tools: dict[uuid.UUID, object] = {}
        self._tool_name_to_id: dict[str, uuid.UUID] = {}

    async def compile_all(self, tool_nodes: list) -> None:
        """Compile every ``ToolNode`` in *tool_nodes*.

        Failed compilations are logged and skipped — one bad tool doesn't
        prevent the rest from being compiled.
        """
        logger.debug("Building tools from %d tool nodes", len(tool_nodes))
        for tool_node in tool_nodes:
            try:
                fn = await compile_tool_from_code(
                    tool_node.name, tool_node.code, dependencies=tool_node.dependencies
                )
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

    def get_tools_for_agent(self, agent_id: uuid.UUID, edges: list) -> list:
        """Return the list of compiled tool callables accessible to *agent_id*
        via ``tool_access`` edges."""
        agent_tools = []
        for edge in edges:
            if edge.source_node_id == agent_id and edge.edge_type == "tool_access":
                fn = self.tools.get(edge.target_node_id)
                if fn:
                    agent_tools.append(fn)
        return agent_tools

    def resolve_tool_node_id(self, tool_name: str) -> uuid.UUID | None:
        """Return the tool-node ID for *tool_name*, or ``None``."""
        return self._tool_name_to_id.get(tool_name)
