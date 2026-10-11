"""ToolRegistry grant semantics for MCP-backed Tool Nodes (tickets #138/#139).

Seam: ``ToolRegistry.compile_all(..., mcp_registry)`` + ``get_tools_for_agent``.
The Agent→Tool ``tool_access`` edge grants **exactly** the node's enabled
``mcp_tools`` selection — never all server tools; enabled-but-vanished tools
are omitted and flagged; connect-time failures and dangling server ids
degrade gracefully (tools omitted, server + reason flagged, the run continues
— spec §4.6); routers are excluded while keeping sandbox tools.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import mcp.types as mcp_types
import pytest

from canvas_server.runner.tool_registry import ToolRegistry


class FakeMcpRegistry:
    """The #137/#139 registry surface ToolRegistry consumes."""

    def __init__(self, tools=None, session=None, error=None, sessions_by_id=None,
                 name=None, tools_by_id=None, names_by_id=None):
        self.tools = tools or []
        self.session = session
        self.error = error
        self.sessions_by_id = sessions_by_id or {}
        self.name = name
        self.tools_by_id = tools_by_id or {}
        self.names_by_id = names_by_id or {}

    def get_session(self, server_id):
        if self.sessions_by_id:
            return self.sessions_by_id.get(server_id, self.session)
        return self.session

    def error_for(self, server_id):
        return self.error

    def server_name(self, server_id):
        return self.names_by_id.get(server_id, self.name)

    async def list_tools(self, server_id):
        return self.tools_by_id.get(server_id, self.tools)


class FakeToolNode:
    def __init__(self, id=None, name="Tool", mcp_server_id=None, mcp_tools=None):
        self.id = id or uuid.uuid4()
        self.name = name
        self.code = "" if mcp_server_id is not None else "async def t(): pass"
        self.dependencies = []
        self.requires_approval = False
        self.mcp_server_id = mcp_server_id
        self.mcp_tools = mcp_tools or []


class FakeAgentNode:
    def __init__(self, id=None, name="Worker", agent_type="worker"):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = ""
        self.instructions = ""
        self.agent_type = agent_type


def _edge(agent, tool, edge_type="tool_access"):
    return SimpleNamespace(
        edge_type=edge_type,
        source_node_id=agent.id,
        target_node_id=tool.id,
    )


async def _compile_ok(name, code, dependencies=None, runtime_session_id=None):
    async def compiled_tool(*_args, **_kwargs):
        """Compiled author tool standing in."""

    return compiled_tool


@pytest.fixture
def _compile_stub():
    with patch(
        "canvas_server.runner.tool_registry.compile_tool_from_code",
        new=_compile_ok,
    ):
        yield


def server_tool(name, description=None):
    return mcp_types.Tool(
        name=name,
        description=description or f"{name} description.",
        inputSchema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
        },
    )


def _registry_with(mcp_registry, tool_nodes, agents):
    registry = ToolRegistry()
    registry._compile = None  # marker unused
    return registry


async def _compile(registry, tool_nodes, mcp_registry):
    await registry.compile_all(tool_nodes, runtime_session_id=None,
                               mcp_registry=mcp_registry)


class TestCodeToolRegression:
    async def test_code_tools_compile_unchanged_alongside_mcp_nodes(
        self, _compile_stub
    ):
        worker = FakeAgentNode(name="Worker")
        code_tool = FakeToolNode(name="scribbler")
        registry = ToolRegistry()
        await registry.compile_all(
            [code_tool], runtime_session_id=None, mcp_registry=FakeMcpRegistry()
        )

        tools = registry.get_tools_for_agent(worker.id, [_edge(worker, code_tool)])
        assert len(tools) == 1
        assert registry.resolve_tool_node_id("scribbler") == code_tool.id


class TestGrantSemantics:
    async def test_grant_is_exactly_the_enabled_selection(self, _compile_stub):
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[
                {"name": "add", "requires_approval": True},
                {"name": "echo", "requires_approval": False},
            ],
        )
        mcp_registry = FakeMcpRegistry(
            tools=[server_tool("add"), server_tool("echo"), server_tool("secret_extra")],
            session=object(),
        )
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        tools = registry.get_tools_for_agent(worker.id, [_edge(worker, node)])
        names = {t.name for t in tools}

        # Enabled tools granted; new server tools never self-grant.
        assert names == {"add", "echo"}
        assert "secret_extra" not in registry._tool_name_to_id

    async def test_per_tool_approval_and_node_id_ride_the_callables(
        self, _compile_stub
    ):
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[
                {"name": "add", "requires_approval": True},
                {"name": "echo", "requires_approval": False},
            ],
        )
        mcp_registry = FakeMcpRegistry(
            tools=[server_tool("add"), server_tool("echo")], session=object()
        )
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        by_name = {
            t.name: t
            for t in registry.get_tools_for_agent(worker.id, [_edge(worker, node)])
        }
        assert by_name["add"].func.requires_approval is True
        assert by_name["echo"].func.requires_approval is False
        for tool in by_name.values():
            assert tool.func.node_id == node.id
            assert tool.func.__name__ == tool.name
            assert "description." in tool.func.__doc__

    async def test_enabled_tool_missing_from_tools_list_is_omitted(
        self, _compile_stub
    ):
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}, {"name": "vanished"}],
        )
        mcp_registry = FakeMcpRegistry(tools=[server_tool("add")], session=object())
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        tools = registry.get_tools_for_agent(worker.id, [_edge(worker, node)])

        assert [t.name for t in tools] == ["add"]
        assert registry.resolve_tool_node_id("vanished") is None

    async def test_sanitized_server_names_map_to_the_tool_node(
        self, _compile_stub
    ):
        node = FakeToolNode(
            name="web",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "search.web v2"}],
        )
        mcp_registry = FakeMcpRegistry(
            tools=[server_tool("search.web v2")], session=object()
        )
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        assert registry.resolve_tool_node_id("search_web_v2") == node.id

    async def test_empty_grant_list_registers_nothing(self, _compile_stub):
        node = FakeToolNode(name="idle", mcp_server_id=uuid.uuid4())
        mcp_registry = FakeMcpRegistry(tools=[server_tool("add")], session=object())
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        assert registry.get_tools_for_agent(worker.id, [_edge(worker, node)]) == []


class TestStalenessFlagging:
    """Spec §4.5 / #139: enabled tools the live ``tools/list`` no longer
    offers are excluded from the grant and flagged "N of M enabled tools
    unavailable" via the existing event machinery (drained by the runner)."""

    async def test_vanished_grants_are_counted_and_flagged(self, _compile_stub):
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}, {"name": "echo"}, {"name": "vanished"}],
        )
        mcp_registry = FakeMcpRegistry(
            tools=[server_tool("add"), server_tool("echo")], session=object()
        )
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        assert [t.name for t in registry.get_tools_for_agent(worker.id, [_edge(worker, node)])] == [
            "add",
            "echo",
        ]

        flags = registry.drain_flags()
        stale = [f for f in flags if f.get("kind") == "stale_tools"]
        assert len(stale) == 1
        assert stale[0]["node_id"] == node.id
        assert "1 of 3 enabled tools unavailable" in stale[0]["message"]

    async def test_no_flag_when_everything_granted_is_offered(self, _compile_stub):
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}, {"name": "echo"}],
        )
        mcp_registry = FakeMcpRegistry(
            tools=[server_tool("add"), server_tool("echo")], session=object()
        )
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        registry.get_tools_for_agent(uuid.uuid4(), [])
        assert registry.drain_flags() == []

    async def test_drain_flags_empties_the_queue(self, _compile_stub):
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}, {"name": "vanished"}],
        )
        mcp_registry = FakeMcpRegistry(tools=[server_tool("add")], session=object())
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        assert registry.drain_flags()
        assert registry.drain_flags() == []


class TestPerAgentCollisions:
    """Spec §4.5 (#139): per-agent, first-come wins; later colliders are
    excluded + flagged; no silent merge, no auto-prefix; the tool-name →
    node-id attribution map belongs to the first-come owner."""

    def _two_nodes(self):
        server_a, server_b = uuid.uuid4(), uuid.uuid4()
        node_a = FakeToolNode(
            name="nodeA",
            mcp_server_id=server_a,
            mcp_tools=[{"name": "search"}],
        )
        node_b = FakeToolNode(
            name="nodeB",
            mcp_server_id=server_b,
            mcp_tools=[{"name": "search"}],
        )
        mcp_registry = FakeMcpRegistry(
            sessions_by_id={server_a: object(), server_b: object()},
            tools_by_id={
                server_a: [server_tool("search", "from A")],
                server_b: [server_tool("search", "from B")],
            },
            names_by_id={server_a: "srv-a", server_b: "srv-b"},
        )
        return node_a, node_b, mcp_registry

    async def test_later_collider_is_excluded_and_flagged(self, _compile_stub):
        node_a, node_b, mcp_registry = self._two_nodes()
        registry = ToolRegistry()
        await _compile(registry, [node_a, node_b], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        edges = [_edge(worker, node_a), _edge(worker, node_b)]
        tools = registry.get_tools_for_agent(worker.id, edges)

        # First-come wins.
        assert len(tools) == 1
        assert tools[0].name == "search"
        assert tools[0].func.node_id == node_a.id

        flags = registry.drain_flags()
        collisions = [f for f in flags if f.get("kind") == "collision"]
        assert len(collisions) == 1
        assert collisions[0]["node_id"] == node_b.id
        message = collisions[0]["message"]
        assert message.startswith("tool 'search' from server")
        assert "was dropped — name already taken by a tool from server" in message
        assert "srv-b" in message and "srv-a" in message

    async def test_attribution_map_stays_with_the_first_come_owner(
        self, _compile_stub
    ):
        node_a, node_b, mcp_registry = self._two_nodes()
        registry = ToolRegistry()
        await _compile(registry, [node_a, node_b], mcp_registry)

        assert registry.resolve_tool_node_id("search") == node_a.id

        worker = FakeAgentNode(name="Worker")
        registry.get_tools_for_agent(worker.id, [_edge(worker, node_b)])
        assert registry.resolve_tool_node_id("search") == node_a.id

    async def test_owner_arriving_later_still_wins(self, _compile_stub):
        # Edges are ordered nodeB-first here, but nodeA owns the name by
        # first-come compile order — the ReAct dict must never see B's tool.
        node_a, node_b, mcp_registry = self._two_nodes()
        registry = ToolRegistry()
        await _compile(registry, [node_a, node_b], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        tools = registry.get_tools_for_agent(
            worker.id, [_edge(worker, node_b), _edge(worker, node_a)]
        )
        assert len(tools) == 1
        assert tools[0].func.node_id == node_a.id

    async def test_code_tool_owner_beats_a_later_mcp_grant(self):
        code_node = FakeToolNode(name="scribbler")  # will compile a "search" tool

        async def search_tool(*_args, **_kwargs):
            """search result"""

        search_tool.__name__ = "search"  # the agent-visible tool name

        server_a = uuid.uuid4()
        mcp_node = FakeToolNode(
            name="nodeA",
            mcp_server_id=server_a,
            mcp_tools=[{"name": "search"}],
        )
        mcp_registry = FakeMcpRegistry(
            sessions_by_id={server_a: object()},
            tools_by_id={server_a: [server_tool("search", "from A")]},
            names_by_id={server_a: "srv-a"},
        )

        async def fake_compile(name, code, dependencies=None,
                               runtime_session_id=None):
            return search_tool

        with patch(
            "canvas_server.runner.tool_registry.compile_tool_from_code",
            new=fake_compile,
        ):
            registry = ToolRegistry()
            await registry.compile_all(
                [code_node, mcp_node], runtime_session_id=None,
                mcp_registry=mcp_registry,
            )

        worker = FakeAgentNode(name="Worker")
        edges = [
            SimpleNamespace(edge_type="tool_access", source_node_id=worker.id,
                target_node_id=mcp_node.id),
            SimpleNamespace(edge_type="tool_access", source_node_id=worker.id,
                target_node_id=code_node.id),
        ]
        tools = registry.get_tools_for_agent(worker.id, edges)
        assert len(tools) == 1
        assert getattr(tools[0], "name", getattr(tools[0], "__name__", "")) == "search"
        assert getattr(tools[0], "node_id", None) == code_node.id

        collisions = [f for f in registry.drain_flags() if f.get("kind") == "collision"]
        assert len(collisions) == 1
        assert collisions[0]["node_id"] == mcp_node.id
        message = collisions[0]["message"]
        assert "from server 'srv-a' was dropped" in message
        assert "code tool node" in message and "scribbler" in message

    async def test_no_collision_when_names_differ(self, _compile_stub):
        node_a, node_b, mcp_registry = self._two_nodes()
        # Overwrite B's grant with a distinct name via a fresh node list.
        server_b = node_b.mcp_server_id
        node_b.mcp_tools = [{"name": "echo"}]
        mcp_registry.tools_by_id[server_b] = [server_tool("echo", "from B")]
        registry = ToolRegistry()
        await _compile(registry, [node_a, node_b], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        tools = registry.get_tools_for_agent(
            worker.id, [_edge(worker, node_a), _edge(worker, node_b)]
        )
        assert {t.name for t in tools} == {"search", "echo"}
        assert [f for f in registry.drain_flags() if f.get("kind") == "collision"] == []


class TestDegradedServers:
    """Spec §4.6 (#139): a genuine connect failure never retries — the run
    continues degraded with that server's tools omitted and the failure
    flagged via the existing event machinery, naming server and reason."""

    async def test_connect_failure_omits_tools_and_flags_server_and_reason(
        self, _compile_stub
    ):
        failure = RuntimeError("connection refused")
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}, {"name": "echo"}],
        )
        mcp_registry = FakeMcpRegistry(error=failure, session=None, name="ref")
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        assert registry.get_tools_for_agent(worker.id, [_edge(worker, node)]) == []
        assert registry.resolve_tool_node_id("add") is None

        flags = registry.drain_flags()
        degraded = [f for f in flags if f.get("kind") == "degraded_server"]
        assert len(degraded) == 1
        assert degraded[0]["node_id"] == node.id
        assert "ref" in degraded[0]["message"]
        assert "connection refused" in degraded[0]["message"]

    async def test_dangling_server_id_omits_tools_and_flags(self, _compile_stub):
        # Server never opened (unregistered id) — session None, error None.
        node = FakeToolNode(
            name="math", mcp_server_id=uuid.uuid4(), mcp_tools=[{"name": "add"}]
        )
        registry = ToolRegistry()
        await _compile(registry, [node], FakeMcpRegistry())

        worker = FakeAgentNode(name="Worker")
        assert registry.get_tools_for_agent(worker.id, [_edge(worker, node)]) == []
        flags = registry.drain_flags()
        degraded = [f for f in flags if f.get("kind") == "degraded_server"]
        assert len(degraded) == 1
        assert degraded[0]["node_id"] == node.id

    async def test_registry_without_mcp_registry_omits_tools_and_flags(
        self, _compile_stub
    ):
        node = FakeToolNode(
            name="math", mcp_server_id=uuid.uuid4(), mcp_tools=[{"name": "add"}]
        )
        registry = ToolRegistry()
        await registry.compile_all([node], runtime_session_id=None, mcp_registry=None)

        worker = FakeAgentNode(name="Worker")
        assert registry.get_tools_for_agent(worker.id, [_edge(worker, node)]) == []
        degraded = [
            f for f in registry.drain_flags() if f.get("kind") == "degraded_server"
        ]
        assert len(degraded) == 1


class TestRouterExclusion:
    async def test_router_path_skips_mcp_nodes_but_keeps_sandbox_tools(
        self, _compile_stub
    ):
        worker = FakeAgentNode(name="Worker")
        router = FakeAgentNode(name="Router", agent_type="router")
        code_tool = FakeToolNode(name="scribbler")
        mcp_node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}],
        )
        mcp_registry = FakeMcpRegistry(tools=[server_tool("add")], session=object())

        registry = ToolRegistry()
        await _compile(registry, [code_tool, mcp_node], mcp_registry)

        edges = [_edge(worker, code_tool), _edge(worker, mcp_node),
                 _edge(router, code_tool), _edge(router, mcp_node)]

        def names(tools):
            return {getattr(t, "name", getattr(t, "__name__", "")) for t in tools}

        worker_tools = registry.get_tools_for_agent(worker.id, edges)
        router_tools = registry.get_tools_for_agent(router.id, edges, include_mcp=False)

        assert names(worker_tools) == {"compiled_tool", "add"}
        # Behavior change (spec §4.3): routers never receive MCP-backed tools…
        assert "add" not in names(router_tools)
        # …but their sandbox (code) tools are untouched.
        assert names(router_tools) == {"compiled_tool"}


class TestAgentFactoryRouterExclusion:
    """Behavior change (spec §4.3): build_router skips MCP-backed Tool Nodes
    while preserving their sandbox tools."""

    async def test_built_router_has_no_mcp_tools(self, _compile_stub):
        import dspy

        from canvas_server.runner.agent_factory import AgentFactory

        class _Mem:
            def needs_memory(self, node):
                return False

            def build_provider(self, node):
                return None

        router = FakeAgentNode(name="Router", agent_type="router")
        code_tool = FakeToolNode(name="scribbler")
        mcp_node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}],
        )
        mcp_registry = FakeMcpRegistry(tools=[server_tool("add")], session=object())

        registry = ToolRegistry()
        await _compile(registry, [code_tool, mcp_node], mcp_registry)

        def tool_names(agent):
            return {
                getattr(t, "name", getattr(getattr(t, "func", t), "__name__", ""))
                for t in agent.tools.values()
            }

        factory = AgentFactory(
            lm=MagicMock(spec=dspy.LM),
            tool_registry=registry,
            memory_manager=_Mem(),
            edges=[_edge(router, code_tool), _edge(router, mcp_node)],
            agent_names={},
            conversation_id=None,
            conversation_repo=MagicMock(),
            attachment_nodes=[],
        )

        agent = await factory.build_router(router, {}, "Router", None, "", None, None)

        # The sandbox (code) tool survives under its callable name…
        assert "compiled_tool" in tool_names(agent)
        # …and no MCP-backed tool is granted to the router.
        assert "add" not in tool_names(agent)
