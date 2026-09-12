"""ToolRegistry — compiles tool nodes and resolves per-agent tool lists."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from canvas_server.tool_factory import compile_tool_from_code

if TYPE_CHECKING:
    from canvas_server.models.canvas import Edge, ToolNode

logger = logging.getLogger("canvas_server.runner.tool_registry")


def _attach_tool_metadata(fn, requires_approval: bool, node_id: uuid.UUID) -> None:
    """Attach approval/node metadata to a compiled tool callable.

    Compiled tools are plain functions (DSPy tool callables); the approval flag
    and owning node ID ride on them as dynamic attributes, read elsewhere via
    ``getattr`` (see ``streaming_react``).
    """
    fn.requires_approval = requires_approval
    fn.node_id = node_id


class ToolRegistry:
    """Compiles ``ToolNode.code`` strings into callable functions and maintains
    the reverse mapping from tool name to node ID.

    State owned by this service:
      ``tools`` — ``{node_id: callable}`` for all compiled tools
      ``_tool_name_to_id`` — ``{tool_name: node_id}`` used by ``_attach_events``
        to resolve tool names to canonical node IDs (for canvas highlighting).
    """

    def __init__(self) -> None:
        self.tools: dict[uuid.UUID, object] = {}
        self._tool_name_to_id: dict[str, uuid.UUID] = {}

    async def compile_all(
        self,
        tool_nodes: list[ToolNode],
        runtime_session_id: str | None = None,
    ) -> None:
        """Compile every ``ToolNode`` in *tool_nodes*."""
        logger.debug("Building tools from %d tool nodes", len(tool_nodes))
        for tool_node in tool_nodes:
            try:
                fn = await compile_tool_from_code(
                    tool_node.name,
                    tool_node.code,
                    dependencies=tool_node.dependencies,
                    runtime_session_id=runtime_session_id,
                )
            except Exception as e:
                logger.warning("Failed to compile tool %s: %s", tool_node.name, e)
                # Create a fallback/stub tool that raises the error when called
                def make_failed_tool(name: str, err: Exception):
                    async def failed_tool(*args, **kwargs):
                        """Failed to compile this tool. Call this tool to see the error details."""
                        raise err
                    failed_tool.__name__ = name
                    return failed_tool

                fn = make_failed_tool(tool_node.name, e)

            _attach_tool_metadata(
                fn,
                requires_approval=getattr(tool_node, "requires_approval", False),
                node_id=tool_node.id,
            )

            self.tools[tool_node.id] = fn
            self._tool_name_to_id[tool_node.name] = tool_node.id
            logger.debug(
                "  compiled tool: id=%s name=%s", tool_node.id, tool_node.name
            )
        logger.info("Built %d tools", len(self.tools))

    def get_tools_for_agent(
        self, agent_id: uuid.UUID, edges: list[Edge]
    ) -> list[Callable[..., Any]]:
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
