"""ToolRegistry — compiles tool nodes and resolves per-agent tool lists."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import mcp.types as mcp_types

from canvas_server.runner.mcp_sessions import McpSessionRegistry
from canvas_server.runner.mcp_tools import build_mcp_tool, make_unavailable_stub, sanitize_tool_name
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
      ``tools`` — ``{node_id: callable}`` for all compiled code tools
      ``_mcp_tools`` — ``{node_id: [dspy.Tool]}`` for MCP-backed nodes (#138):
        one descriptor per enabled grant, each carrying the raw callables'
        ``requires_approval``/``node_id`` metadata on its ``.func``
      ``_tool_name_to_id`` — ``{tool_name: node_id}`` used by ``_attach_events``
        to resolve tool names to canonical node IDs (for canvas highlighting).
    """

    def __init__(self) -> None:
        self.tools: dict[uuid.UUID, object] = {}
        self._mcp_tools: dict[uuid.UUID, list[object]] = {}
        self._tool_name_to_id: dict[str, uuid.UUID] = {}
        # Degradation/staleness/collision notes (#139), drained once by the
        # runner and surfaced through the existing "warning" event machinery.
        self._flags: list[dict[str, Any]] = []

    def drain_flags(self) -> list[dict[str, Any]]:
        """Unread flag notes (and clear them) — the runner's emit pass."""
        flags, self._flags = self._flags, []
        return flags

    def _record_flag(self, kind: str, node_id: uuid.UUID, message: str) -> None:
        logger.warning("MCP flag (%s) node %s: %s", kind, node_id, message)
        self._flags.append(
            {"kind": kind, "node_id": node_id, "message": message}
        )

    async def compile_all(
        self,
        tool_nodes: list[ToolNode],
        runtime_session_id: str | None = None,
        mcp_registry: McpSessionRegistry | None = None,
    ) -> None:
        """Compile every ``ToolNode`` in *tool_nodes*.

        MCP-backed nodes (``mcp_server_id`` is set, #132) are served from the
        run's ``McpSessionRegistry`` (#137) instead of the code compiler; a
        ``None`` *mcp_registry* degrades their grants to call-time error
        stubs so the run never fails outright (spec §4.6).
        """
        logger.debug("Building tools from %d tool nodes", len(tool_nodes))
        for tool_node in tool_nodes:
            server_id = getattr(tool_node, "mcp_server_id", None)
            if server_id is not None:
                await self._compile_mcp_node(tool_node, server_id, mcp_registry)
                continue
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
            self._register_tool_name(tool_node.name, tool_node.id)
            logger.debug(
                "  compiled tool: id=%s name=%s", tool_node.id, tool_node.name
            )
        logger.info(
            "Built %d code tools and %d MCP-backed tool node(s)",
            len(self.tools),
            len(self._mcp_tools),
        )

    async def _compile_mcp_node(
        self,
        tool_node: ToolNode,
        server_id: uuid.UUID,
        mcp_registry: McpSessionRegistry | None,
    ) -> None:
        """Serve one MCP-backed node's enabled grants (ticket #138).

        Grant semantics (spec §4 / #122): the ``tool_access`` edge grants
        exactly the node's enabled ``mcp_tools`` selection — new server tools
        never self-grant, enabled-but-vanished tools are omitted (flagging
        waits for #139). A dead/absent server session degrades every grant
        into a call-time error stub (spec §4.6).
        """
        grants = self._parse_mcp_grants(tool_node)
        if not grants:
            logger.info(
                "MCP tool node %s (%s) grants no tools — nothing to serve",
                tool_node.name,
                tool_node.id,
            )
            return

        session = (
            mcp_registry.get_session(server_id) if mcp_registry is not None else None
        )
        error = (
            mcp_registry.error_for(server_id) if mcp_registry is not None else None
        )
        listing: dict[str, mcp_types.Tool] | None = None
        if session is not None:
            try:
                listing = {
                    server_tool.name: server_tool
                    for server_tool in await mcp_registry.list_tools(server_id)
                }
            except Exception as e:  # noqa: BLE001 — session died before tools/list
                logger.warning(
                    "tools/list failed for MCP server %s: %s", server_id, e
                )
                error = error or e

        built: list[object] = []
        vanished: list[str] = []
        for grant in grants:
            display_name = sanitize_tool_name(grant["name"])
            if error is not None:
                descriptor = make_unavailable_stub(
                    display_name, error, tool_node.id
                )
            elif listing is None:
                descriptor = make_unavailable_stub(
                    display_name,
                    RuntimeError(
                        f"MCP server {server_id} is not connected; "
                        f"its tools are unavailable for this run."
                    ),
                    tool_node.id,
                )
            else:
                server_tool = listing.get(grant["name"])
                if server_tool is None:
                    # Enabled-but-vanished: omitted from the grant and
                    # flagged "N of M enabled tools unavailable" (spec §4.5).
                    logger.info(
                        "Granted MCP tool %r of server %s is not in the run's "
                        "tools/list — omitted",
                        grant["name"],
                        server_id,
                    )
                    vanished.append(grant["name"])
                    continue
                descriptor = build_mcp_tool(
                    session,
                    server_tool,
                    node_id=tool_node.id,
                    requires_approval=grant["requires_approval"],
                )

            _attach_tool_metadata(
                getattr(descriptor, "func", descriptor),
                requires_approval=grant["requires_approval"],
                node_id=tool_node.id,
            )
            built.append(descriptor)
            self._register_tool_name(display_name, tool_node.id)

        if built:
            self._mcp_tools[tool_node.id] = built

        if vanished:
            self._record_flag(
                "stale_tools",
                tool_node.id,
                f"MCP tool node '{tool_node.name}': "
                f"{len(vanished)} of {len(grants)} enabled tools unavailable "
                "— omitted from this run.",
            )

    @staticmethod
    def _parse_mcp_grants(tool_node: ToolNode) -> list[dict[str, Any]]:
        """The node's enabled-tools selection as ``{name, requires_approval}``."""
        grants: list[dict[str, Any]] = []
        for entry in getattr(tool_node, "mcp_tools", None) or []:
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            grants.append(
                {
                    "name": name,
                    "requires_approval": bool(entry.get("requires_approval", False)),
                }
            )
        return grants

    def _register_tool_name(self, tool_name: str, node_id: uuid.UUID) -> None:
        """First-come name → node mapping (collision flagging is #139)."""
        owner = self._tool_name_to_id.get(tool_name)
        if owner is not None and owner != node_id:
            logger.warning(
                "Tool name %r is already owned by node %s — name mapping for "
                "node %s is dropped (collision surfacing lands with #139)",
                tool_name,
                owner,
                node_id,
            )
            return
        self._tool_name_to_id[tool_name] = node_id

    def get_tools_for_agent(
        self, agent_id: uuid.UUID, edges: list[Edge], include_mcp: bool = True
    ) -> list[Callable[..., Any]]:
        """Return the tool callables accessible to *agent_id* via
        ``tool_access`` edges.

        ``include_mcp=False`` (routers, spec §4.3 / arch decision 8) skips
        MCP-backed tool nodes entirely while keeping their sandbox tools.
        """
        agent_tools = []
        for edge in edges:
            if edge.source_node_id == agent_id and edge.edge_type == "tool_access":
                if include_mcp:
                    agent_tools.extend(self._mcp_tools.get(edge.target_node_id, []))
                fn = self.tools.get(edge.target_node_id)
                if fn:
                    agent_tools.append(fn)
        return agent_tools

    def resolve_tool_node_id(self, tool_name: str) -> uuid.UUID | None:
        """Return the tool-node ID for *tool_name*, or ``None``."""
        return self._tool_name_to_id.get(tool_name)
