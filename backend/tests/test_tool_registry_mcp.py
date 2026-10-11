"""ToolRegistry grant semantics for MCP-backed Tool Nodes (ticket #138).

Seam: ``ToolRegistry.compile_all(..., mcp_registry)`` + ``get_tools_for_agent``.
The Agent→Tool ``tool_access`` edge grants **exactly** the node's enabled
``mcp_tools`` selection — never all server tools; enabled-but-vanished tools
are omitted; connect-time failures and dangling server ids degrade to
call-time error stubs; routers are excluded while keeping sandbox tools.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import mcp.types as mcp_types
import pytest

from canvas_server.runner.tool_registry import ToolRegistry


class FakeMcpRegistry:
    """The #137 registry surface ToolRegistry consumes."""

    def __init__(self, tools=None, session=None, error=None, sessions_by_id=None):
        self.tools = tools or []
        self.session = session
        self.error = error
        self.sessions_by_id = sessions_by_id or {}

    def get_session(self, server_id):
        if self.sessions_by_id:
            return self.sessions_by_id.get(server_id, self.session)
        return self.session

    def error_for(self, server_id):
        return self.error

    async def list_tools(self, server_id):
        return self.tools


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


class TestDegradedServers:
    async def test_connect_failure_makes_error_stubs_that_raise_at_call_time(
        self, _compile_stub
    ):
        failure = RuntimeError("connection refused")
        node = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}, {"name": "echo"}],
        )
        mcp_registry = FakeMcpRegistry(error=failure, session=None)
        registry = ToolRegistry()
        await _compile(registry, [node], mcp_registry)

        worker = FakeAgentNode(name="Worker")
        tools = registry.get_tools_for_agent(worker.id, [_edge(worker, node)])
        assert {t.name for t in tools} == {"add", "echo"}

        for tool in tools:
            with pytest.raises(RuntimeError, match="connection refused"):
                await tool.acall()

    async def test_dangling_server_id_makes_call_time_error_stubs(
        self, _compile_stub
    ):
        # Server never opened (unregistered id) — session None, error None.
        node = FakeToolNode(
            name="math", mcp_server_id=uuid.uuid4(), mcp_tools=[{"name": "add"}]
        )
        registry = ToolRegistry()
        await _compile(registry, [node], FakeMcpRegistry())

        worker = FakeAgentNode(name="Worker")
        (tool,) = registry.get_tools_for_agent(worker.id, [_edge(worker, node)])
        assert tool.name == "add"
        with pytest.raises(RuntimeError, match="not connected"):
            await tool.acall()

    async def test_registry_without_mcp_registry_grants_error_stubs(
        self, _compile_stub
    ):
        node = FakeToolNode(
            name="math", mcp_server_id=uuid.uuid4(), mcp_tools=[{"name": "add"}]
        )
        registry = ToolRegistry()
        await registry.compile_all([node], runtime_session_id=None, mcp_registry=None)

        worker = FakeAgentNode(name="Worker")
        (tool,) = registry.get_tools_for_agent(worker.id, [_edge(worker, node)])
        with pytest.raises(RuntimeError, match="not connected"):
            await tool.acall()


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
