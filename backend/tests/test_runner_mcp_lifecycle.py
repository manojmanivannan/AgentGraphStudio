"""Runner-side MCP session lifecycle wiring (ticket #137, spec §4.3).

``CanvasRunner.setup()`` opens one session per worker-granted MCP server via
the per-run ``McpSessionRegistry``; routers and MCP-free canvases open
nothing; the registry rides ``CanvasRunState`` for the run's agents.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from canvas_server import mcp_config
from canvas_server.models.mcp import McpServer
from canvas_server.runner.runner import CanvasRunner


class FakeCanvas:
    def __init__(self, id=None, agent_nodes=None, tool_nodes=None, edges=None):
        self.id = id or uuid.uuid4()
        self.agent_nodes = agent_nodes or []
        self.tool_nodes = tool_nodes or []
        self.edges = edges or []


class FakeAgentNode:
    def __init__(self, id=None, name="", agent_type="worker"):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = ""
        self.instructions = ""
        self.agent_type = agent_type
        self.model_name = "ollama:llama3.1"
        self.is_entry_point = False
        self.rag_top_k = 5
        self.position_x = 0
        self.position_y = 0


class FakeToolNode:
    def __init__(self, id=None, name="", mcp_server_id=None):
        self.id = id or uuid.uuid4()
        self.name = name
        self.code = ""
        self.dependencies = []
        self.mcp_server_id = mcp_server_id
        self.mcp_tools = []


def _tool_access(agent, tool):
    return SimpleNamespace(
        edge_type="tool_access",
        source_node_id=agent.id,
        target_node_id=tool.id,
    )


async def _noop_tool(*args, **kwargs):
    """Stand-in compiled tool."""


async def _compile_stub_tool(name, code, dependencies=None, runtime_session_id=None):
    return _noop_tool


@pytest.fixture
def _compile_stub():
    with patch(
        "canvas_server.runner.tool_registry.compile_tool_from_code",
        new=_compile_stub_tool,
    ):
        yield


@pytest.fixture(autouse=True)
def _clean_mcp_cache():
    mcp_config.reset_mcp_servers_cache()
    yield
    mcp_config.reset_mcp_servers_cache()


class TestSetupOpensSessionsForWorkerGrants:
    async def test_setup_opens_session_for_worker_granted_server(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        obs = make_ref_mcp_server()
        test_session.add(McpServer(name="ref", url=obs.url))
        await test_session.flush()
        registry_server = (await mcp_config.refresh_mcp_servers(test_session))[0]

        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(name="math", mcp_server_id=registry_server.id)
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()

        assert obs.initialize_count == 1  # handshake happened during setup
        assert runner.mcp_session_registry is not None
        assert runner.mcp_session_registry.get_session(registry_server.id) is not None
        assert runner.run_state.mcp_session_registry is runner.mcp_session_registry

        await runner.release_mcp_sessions()

    async def test_setup_handles_tool_node_without_worker_grant(self, make_ref_mcp_server, test_session, _compile_stub):
        obs = make_ref_mcp_server()
        test_session.add(McpServer(name="ref", url=obs.url))
        await test_session.flush()
        registry_server = (await mcp_config.refresh_mcp_servers(test_session))[0]

        # MCP tool node exists but nothing grants it tool_access from a worker.
        tool = FakeToolNode(name="math", mcp_server_id=registry_server.id)
        canvas = FakeCanvas(tool_nodes=[tool])

        runner = CanvasRunner(canvas)
        await runner.setup()

        assert obs.initialize_count == 0
        assert runner.mcp_session_registry.server_ids == set()

        await runner.release_mcp_sessions()

    async def test_router_grants_open_no_sessions(self, make_ref_mcp_server, test_session, _compile_stub):
        obs = make_ref_mcp_server()
        test_session.add(McpServer(name="ref", url=obs.url))
        await test_session.flush()
        registry_server = (await mcp_config.refresh_mcp_servers(test_session))[0]

        router = FakeAgentNode(name="Router", agent_type="router")
        tool = FakeToolNode(name="math", mcp_server_id=registry_server.id)
        canvas = FakeCanvas(
            agent_nodes=[router], tool_nodes=[tool], edges=[_tool_access(router, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()

        assert obs.initialize_count == 0  # routers never get network surfaces (arch 8)
        assert runner.mcp_session_registry.server_ids == set()

        await runner.release_mcp_sessions()

    async def test_dangling_mcp_server_id_opens_nothing(self, make_ref_mcp_server, _compile_stub):
        make_ref_mcp_server()  # server exists but is not in the registry cache
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(name="math", mcp_server_id=uuid.uuid4())  # not registered
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()  # never raises

        assert runner.mcp_session_registry.server_ids == set()

        await runner.release_mcp_sessions()

    async def test_mcp_free_canvas_performs_no_connects(self, make_ref_mcp_server, test_session, _compile_stub):
        obs = make_ref_mcp_server()
        test_session.add(McpServer(name="ref", url=obs.url))
        await test_session.flush()
        await mcp_config.refresh_mcp_servers(test_session)

        worker = FakeAgentNode(name="Worker")
        canvas = FakeCanvas(agent_nodes=[worker])

        runner = CanvasRunner(canvas)
        await runner.setup()

        assert obs.initialize_count == 0 and obs.post_count == 0
        assert runner.mcp_session_registry.server_ids == set()

        await runner.release_mcp_sessions()