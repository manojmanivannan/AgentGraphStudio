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
from canvas_server.conversation_run_coordinator import ConversationRunCoordinator
from canvas_server.mcp_config import McpServerConfig
from canvas_server.models.mcp import McpServer
from canvas_server.runner.mcp_sessions import McpSessionRegistry
from canvas_server.runner.runner import CanvasRunner


class FakeSession:
    def __init__(self):
        self.commit = AsyncMock()


class FakeConversationRepo:
    def __init__(self, conversation):
        self.conversation = conversation

    async def get_or_404(self, conversation_id):
        assert conversation_id == self.conversation.id
        return self.conversation


class FakeCanvasRepo:
    def __init__(self, canvas):
        self.canvas = canvas

    async def get_or_404(self, canvas_id):
        assert canvas_id == self.canvas.id
        return self.canvas


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

class TestCoordinatorClosesSessionsAtRunEnd:
    """The run's MCP sessions terminate in ConversationRunCoordinator.run's
    finally — next to sandbox.release_session — even when the run errors."""

    def _coordinator(self, conversation, canvas, runner):
        return ConversationRunCoordinator(
            session=FakeSession(),
            conversation_repo=FakeConversationRepo(conversation),
            canvas_repo=FakeCanvasRepo(canvas),
            runner_factory=AsyncMock(return_value=runner),
        )

    def _conversation(self, canvas_id=None):
        return SimpleNamespace(
            id=uuid.uuid4(),
            canvas_id=canvas_id or uuid.uuid4(),
            name="Existing Conversation",
            messages=[object()],
        )

    def _canvas(self, canvas_id):
        return SimpleNamespace(id=canvas_id)

    def _runner(self, failure=None):
        reg = McpSessionRegistry(servers=())
        runner = SimpleNamespace(
            generate_conversation_title=AsyncMock(),
            run=AsyncMock(side_effect=failure) if failure else AsyncMock(),
            _conversation=SimpleNamespace(persist_message=AsyncMock()),
            mcp_session_registry=reg,
            release_mcp_sessions=AsyncMock(),
        )
        return runner

    async def _open_sessions(self, runner, make_ref_mcp_server):
        obs = make_ref_mcp_server()
        cfg = McpServerConfig(
            id=uuid.uuid4(), name="ref", url=obs.url,
            credential_header=None, credential_value=None,
        )
        runner.mcp_session_registry = McpSessionRegistry(servers=(cfg,))
        await runner.mcp_session_registry.open([cfg.id])

        async def _release():
            await runner.mcp_session_registry.close()
        runner.release_mcp_sessions = AsyncMock(side_effect=_release)
        return runner, obs, cfg.id

    async def test_closes_sessions_after_success(self, make_ref_mcp_server):
        runner = self._runner()
        runner, obs, sid = await self._open_sessions(runner, make_ref_mcp_server)
        canvas = self._canvas(uuid.uuid4())
        conversation = self._conversation(canvas.id)

        await self._coordinator(conversation, canvas, runner).run(
            conversation_id=conversation.id, user_prompt="hi",
            send_event=AsyncMock(),
        )

        assert runner.release_mcp_sessions.await_count == 1
        assert runner.mcp_session_registry.get_session(sid) is None
        assert obs.delete_count == 1  # server sees the session terminate

    async def test_closes_sessions_when_run_errors(self, make_ref_mcp_server):
        runner = self._runner(failure=RuntimeError("boom"))
        runner, obs, sid = await self._open_sessions(runner, make_ref_mcp_server)
        canvas = SimpleNamespace(
            id=uuid.uuid4(), agent_nodes=[SimpleNamespace(id=uuid.uuid4(), name="A")]
        )
        conversation = self._conversation(canvas.id)

        await self._coordinator(conversation, canvas, runner).run(
            conversation_id=conversation.id, user_prompt="hi",
            send_event=AsyncMock(),
        )

        assert runner.release_mcp_sessions.await_count == 1
        assert runner.mcp_session_registry.get_session(sid) is None
        assert obs.delete_count == 1

    async def test_release_failure_does_not_break_the_turn(self, make_ref_mcp_server):
        runner = self._runner()
        runner, _obs, _sid = await self._open_sessions(runner, make_ref_mcp_server)
        runner.release_mcp_sessions = AsyncMock(side_effect=RuntimeError("release boom"))
        canvas = self._canvas(uuid.uuid4())
        conversation = self._conversation(canvas.id)

        # No raise — cleanup must never block the turn.
        await self._coordinator(conversation, canvas, runner).run(
            conversation_id=conversation.id, user_prompt="hi",
            send_event=AsyncMock(),
        )
