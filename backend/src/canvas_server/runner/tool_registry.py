"""ToolRegistry — compiles tool nodes and resolves per-agent tool lists."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import mcp.types as mcp_types

from canvas_server.mcp_probe import _summarize
from canvas_server.runner.mcp_sessions import McpSessionRegistry
from canvas_server.runner.mcp_sessions import is_stale_session_error as _is_stale_session_error
from canvas_server.runner.mcp_tools import build_mcp_tool, sanitize_tool_name
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
        # node_id → human phrase describing where a node's tools came from
        # ("server '<name>'" / "code tool node '<name>'") for flag messages.
        self._node_labels: dict[uuid.UUID, str] = {}
        self._collision_keys: set[tuple[uuid.UUID, str, uuid.UUID | None]] = set()

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
            self._node_labels[tool_node.id] = (
                f"code tool node '{tool_node.name}'"
            )
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
            # The agent-visible name of a code tool is the callable's
            # ``__name__`` (dspy wraps it as-is) — register it too so
            # attribution and per-agent collisions key on the names the LLM
            # actually sees (normally identical to the node name).
            visible = getattr(fn, "__name__", None)
            if visible and visible != tool_node.name:
                self._register_tool_name(visible, tool_node.id)
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
        """Serve one MCP-backed node's enabled grants (tickets #138/#139).

        Grant semantics (spec §4 / #122): the ``tool_access`` edge grants
        exactly the node's enabled ``mcp_tools`` selection — new server tools
        never self-grant, enabled-but-vanished tools are omitted and flagged
        ("N of M enabled tools unavailable"). A dead/unreachable server
        degrades the run: its grants are omitted entirely and the failure is
        flagged naming the server and reason — no retry, no stub, no run
        failure (spec §4.6).
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
            except Exception as e:  # noqa: BLE001 — handled below
                if _is_stale_session_error(e):
                    # #139: a stale session at grant time gets its one
                    # re-handshake + one ``tools/list`` retry, then normal
                    # resolution continues.
                    fresh = await mcp_registry.rehandshake(server_id)
                    if fresh is not None:
                        session = fresh
                        try:
                            listing = {
                                server_tool.name: server_tool
                                for server_tool in await mcp_registry.list_tools(
                                    server_id
                                )
                            }
                        except Exception as retry_error:  # noqa: BLE001
                            logger.warning(
                                "tools/list failed for MCP server %s after its "
                                "one re-handshake: %s", server_id, retry_error
                            )
                            error = error or retry_error
                if error is None and listing is None:
                    logger.warning(
                        "tools/list failed for MCP server %s: %s", server_id, e
                    )
                    error = error or e

        server_label = self._server_label(mcp_registry, server_id)
        self._node_labels[tool_node.id] = f"server '{server_label}'"
        if error is not None or listing is None:
            # Spec §4.6 degradation: omit every grant, flag server + reason.
            reason = (
                _summarize(error)
                if error is not None
                else f"no open session for server {server_label}"
            )
            self._record_flag(
                "degraded_server",
                tool_node.id,
                f"MCP server '{server_label}' is unreachable: {reason}. "
                f"{len(grants)} enabled tool(s) of tool node '{tool_node.name}' "
                "are unavailable for this run; the run continues without them.",
            )
            return

        built: list[object] = []
        vanished: list[str] = []
        for grant in grants:
            display_name = sanitize_tool_name(grant["name"])
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
                session_registry=mcp_registry,
                server_id=server_id,
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
    def _server_label(
        mcp_registry: McpSessionRegistry | None, server_id: uuid.UUID
    ) -> str:
        """Human-readable server name for flag messages (id fallback)."""
        if mcp_registry is not None:
            resolved = mcp_registry.server_name(server_id)
            if resolved:
                return str(resolved)
        return str(server_id)

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
        """First-come name → node mapping (attributing runs to first-come)."""
        owner = self._tool_name_to_id.get(tool_name)
        if owner is not None and owner != node_id:
            logger.warning(
                "Tool name %r is already owned by node %s — name mapping for "
                "node %s is dropped (collision flagging: #139)",
                tool_name,
                owner,
                node_id,
            )
            return
        self._tool_name_to_id[tool_name] = node_id

    @staticmethod
    def _tool_identity(tool: Any) -> tuple[str, uuid.UUID | None]:
        """The agent-visible (sanitized) name and owning node of a tool."""
        func = getattr(tool, "func", None)
        if func is None:
            func = tool
        name = getattr(tool, "name", None) or getattr(func, "__name__", None)
        return (str(name) if name else ""), getattr(func, "node_id", None)

    def get_tools_for_agent(
        self, agent_id: uuid.UUID, edges: list[Edge], include_mcp: bool = True
    ) -> list[Callable[..., Any]]:
        """Return the tool callables accessible to *agent_id* via
        ``tool_access`` edges, collision-resolved per agent (spec §4.5).

        Per-agent first-come wins, keyed by the registry's first-come
        name → node attribution: when two tools in one agent's list share a
        sanitized name, the descriptor whose node owns the name stays and
        later colliders are excluded + flagged — no silent merge (a ReAct
        dict over this list can no longer let the later tool win), no
        auto-prefix. When the owning node is absent from the list, the first
        list occurrence wins.

        ``include_mcp=False`` (routers, spec §4.3 / arch decision 8) skips
        MCP-backed tool nodes entirely while keeping their sandbox tools.
        """
        kept: dict[str, tuple[object, uuid.UUID | None, int]] = {}
        ordered: list[object] = []
        for edge in edges:
            if edge.source_node_id != agent_id or edge.edge_type != "tool_access":
                continue
            candidates: list[Any] = []
            if include_mcp:
                candidates.extend(self._mcp_tools.get(edge.target_node_id, []))
            fn = self.tools.get(edge.target_node_id)
            if fn:
                candidates.append(fn)

            for tool in candidates:
                name, node_id = self._tool_identity(tool)
                if not name:
                    ordered.append(tool)
                    continue
                if name not in kept:
                    kept[name] = (tool, node_id, len(ordered))
                    ordered.append(tool)
                    continue

                current_tool, current_node, current_index = kept[name]
                owner = self._tool_name_to_id.get(name)
                if owner is not None and node_id == owner and current_node != owner:
                    # The first-come owner arrives later in the edges — swap.
                    self._record_collision(
                        name, dropped_node=current_node, kept_node=node_id,
                        agent_id=agent_id,
                    )
                    kept[name] = (tool, node_id, current_index)
                    ordered[current_index] = tool
                    continue
                self._record_collision(
                    name, dropped_node=node_id, kept_node=current_node,
                    agent_id=agent_id,
                )
        return ordered

    def _record_collision(
        self,
        name: str,
        dropped_node: uuid.UUID | None,
        kept_node: uuid.UUID | None,
        agent_id: uuid.UUID,
    ) -> None:
        """Flag an excluded per-agent collider (spec §4.5), once per
        (agent, name, dropped node) tuple."""
        key = (agent_id, name, dropped_node)
        if key in self._collision_keys:
            return
        self._collision_keys.add(key)
        dropped = self._node_labels.get(dropped_node, str(dropped_node))
        kept = self._node_labels.get(kept_node, str(kept_node))
        message = (
            f"tool '{name}' from {dropped} was dropped — name already taken "
            f"by a tool from {kept}"
        )
        node_id = dropped_node if dropped_node is not None else agent_id
        self._record_flag("collision", node_id, message)

    def resolve_tool_node_id(self, tool_name: str) -> uuid.UUID | None:
        """Return the tool-node ID for *tool_name*, or ``None``."""
        return self._tool_name_to_id.get(tool_name)
