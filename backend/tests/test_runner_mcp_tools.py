"""Runner wiring + end-to-end MCP tool execution (ticket #138, spec §4.1–4.5).

``CanvasRunner.setup()`` serves each worker-granted MCP Tool Node from the
per-run session registry through ``ToolRegistry.compile_all``; the built
worker agent then invokes the remote tool over the live reference server and
the result renders as the ReAct observation — no new execution path, no new
event types.

Worker runs are driven through the public ``StreamingReAct.aforward`` seam
with staged fake LM predictions (same pattern as
``test_streaming_react_unknown_tool.py``); the tool calls themselves go over
the wire to a real MCP server for granted tools.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    def __init__(self, id=None, name="", mcp_server_id=None, mcp_tools=None):
        self.id = id or uuid.uuid4()
        self.name = name
        self.code = ""
        self.dependencies = []
        self.args = []
        self.requires_approval = False
        self.mcp_server_id = mcp_server_id
        self.mcp_tools = mcp_tools or []


def _tool_access(agent, tool):
    return SimpleNamespace(
        edge_type="tool_access",
        source_node_id=agent.id,
        target_node_id=tool.id,
    )


async def _noop_tool(*args, **kwargs):
    """Stand-in compiled author tool."""


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


async def _register_server(test_session, url, name="ref"):
    test_session.add(McpServer(name=name, url=url))
    await test_session.flush()
    servers = await mcp_config.refresh_mcp_servers(test_session)
    return [cfg for cfg in servers if cfg.name == name][0]


def make_prediction(tool_name="finish", thought="", args=None):
    pred = MagicMock()
    pred.next_thought = thought
    pred.next_tool_name = tool_name
    pred.next_tool_args = args or {}
    return pred


async def drive_agent(agent, predictions):
    """Drive the worker's ReAct loop with staged LM predictions; the tools
    themselves execute for real."""
    with patch.object(
        agent, "_async_call_with_potential_trajectory_truncation"
    ) as mock_call:
        mock_call.side_effect = predictions
        return await agent.aforward(user_request="run the tool")


class TestSetupServesMcpGrants:
    async def test_worker_agent_receives_exactly_the_granted_tools(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        obs = make_ref_mcp_server(tools=("add", "echo", "secret"))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="math",
            mcp_server_id=server.id,
            mcp_tools=[{"name": "add", "requires_approval": True}, {"name": "echo"}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()

        agent = runner.agents[worker.id]
        # Granted tools served; never all server tools (no self-grant).
        assert "add" in agent.tools and "echo" in agent.tools
        assert "secret" not in agent.tools
        assert agent.tools["add"].func.requires_approval is True
        assert agent.tools["echo"].func.requires_approval is False
        assert agent.tools["add"].func.node_id == tool.id

        await runner.release_mcp_sessions()

    async def test_enabled_tool_missing_from_catalog_is_omitted(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        obs = make_ref_mcp_server(tools=("add",))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="math",
            mcp_server_id=server.id,
            mcp_tools=[{"name": "add"}, {"name": "vanished"}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()

        agent = runner.agents[worker.id]
        assert "add" in agent.tools
        assert "vanished" not in agent.tools

        await runner.release_mcp_sessions()

    async def test_dangling_server_id_degrades_to_omitted_tools(
        self, make_ref_mcp_server, _compile_stub
    ):
        make_ref_mcp_server()  # exists, but its id is not registered anywhere
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="math",
            mcp_server_id=uuid.uuid4(),
            mcp_tools=[{"name": "add"}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()

        agent = runner.agents[worker.id]
        assert "add" not in agent.tools

        await runner.release_mcp_sessions()

    async def test_dead_server_degrades_the_run_with_failure_event(
        self, test_session, _compile_stub
    ):
        """Spec §4.6 acceptance: an unreachable server never fails the run —
        even when an agent's entire toolset came from it. The failure is
        surfaced as a warning event naming the server and reason."""
        dead = await _register_server(
            test_session, "http://127.0.0.1:9/mcp", name="dead-server"
        )
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="math",
            mcp_server_id=dead.id,
            mcp_tools=[{"name": "add", "requires_approval": False}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        events = []

        async def capture(event):
            events.append(event)

        await runner.setup(send_event=capture)

        # Tools are omitted; the failure is flagged, naming server + reason.
        agent = runner.agents[worker.id]
        assert agent.tools.get("add") is None
        warnings = [e for e in events if e.get("type") == "warning"]
        assert len(warnings) == 1
        assert "dead-server" in warnings[0]["message"]
        assert warnings[0]["node_id"] == str(tool.id)
        # The reason names the underlying failure, not just "TaskGroup".
        assert "connection" in warnings[0]["message"].lower()

        # The agent (whose only toolset came from the dead server) still runs.
        result = await drive_agent(
            agent,
            [
                make_prediction("finish", thought="nothing to call"),
                {"process_result": "The MCP server is down."},
            ],
        )
        assert result.process_result == "The MCP server is down."

        await runner.release_mcp_sessions()


class TestEndToEndWorkerInvocation:
    """Acceptance criterion: an agent with a wired MCP grant invokes the
    remote tool and the result is rendered as the observation."""

    async def test_worker_invokes_remote_add_and_observes_result(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        obs = make_ref_mcp_server(tools=("add",))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="math",
            mcp_server_id=server.id,
            mcp_tools=[{"name": "add", "requires_approval": False}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()
        agent = runner.agents[worker.id]

        events = []
        agent.on_event(events.append)
        result = await drive_agent(
            agent,
            [
                make_prediction("add", args={"a": 2, "b": 3}, thought="compute"),
                make_prediction("finish", thought="done"),
                {"process_result": "The sum is 5."},
            ],
        )

        # The remote result is rendered as the observation.
        assert result.trajectory["observation_0"] == "5"
        tool_result = [e for e in events if e["type"] == "tool_result"][0]
        assert tool_result["output"] == "5"
        assert tool_result["raw_content"][0]["text"] == "5"
        assert result.process_result == "The sum is 5."

        await runner.release_mcp_sessions()

    async def test_is_error_result_observed_as_ordinary_observation(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        obs = make_ref_mcp_server(tools=("flaky",))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="flaky-node",
            mcp_server_id=server.id,
            mcp_tools=[{"name": "flaky", "requires_approval": False}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()
        agent = runner.agents[worker.id]

        result = await drive_agent(
            agent,
            [
                make_prediction("flaky", args={}, thought="try it"),
                make_prediction("finish", thought="done"),
                {"process_result": "Reported the failure."},
            ],
        )

        # The call never raises for tool errors; the run continues.
        assert result.trajectory["observation_0"] == (
            "Error executing tool flaky: deliberate boom"
        )

        await runner.release_mcp_sessions()

    async def test_big_output_reference_tool_is_truncated_with_note(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        from canvas_server.runner.mcp_tools import MCP_RESULT_MAX_CHARS

        obs = make_ref_mcp_server(tools=("big_output",))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="big",
            mcp_server_id=server.id,
            mcp_tools=[{"name": "big_output", "requires_approval": False}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()
        agent = runner.agents[worker.id]

        result = await drive_agent(
            agent,
            [
                make_prediction("big_output", args={}, thought="fetch"),
                make_prediction("finish", thought="done"),
                {"process_result": "Truncated."},
            ],
        )

        observation = result.trajectory["observation_0"]
        assert observation.startswith("A" * MCP_RESULT_MAX_CHARS)
        assert "truncated" in observation
        assert len(observation) <= MCP_RESULT_MAX_CHARS + 100

        await runner.release_mcp_sessions()

    async def test_slow_tool_times_out_into_observation_and_run_continues(
        self, make_ref_mcp_server, test_session, _compile_stub, monkeypatch
    ):
        """Spec §4.4: the per-call timeout converts a hung remote call into the
        standard execution-error observation; the loop keeps going."""
        from canvas_server.config import settings

        obs = make_ref_mcp_server(tools=("slow",))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="slow-node",
            mcp_server_id=server.id,
            mcp_tools=[{"name": "slow", "requires_approval": False}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        monkeypatch.setattr(settings, "mcp_tool_call_timeout_seconds", 0.3)
        runner = CanvasRunner(canvas)
        await runner.setup()
        agent = runner.agents[worker.id]

        events = []
        agent.on_event(events.append)
        result = await drive_agent(
            agent,
            [
                make_prediction("slow", args={}, thought="patience"),
                make_prediction("finish", thought="done"),
                {"process_result": "The tool timed out."},
            ],
        )

        assert result.trajectory["observation_0"] == (
            "Execution error in slow: timed out after 0.3s"
        )
        tool_result = [e for e in events if e["type"] == "tool_result"][0]
        assert tool_result["output"].startswith("Execution error in slow: timed out")
        assert result.process_result == "The tool timed out."

        await runner.release_mcp_sessions()


class TestSetupFlagsSurfaceThroughWarningEvents:
    """Spec §4.5: staleness flagging rides the existing event machinery —
    a "warning" event naming the N-of-M count, on the Tool Node's node_id."""

    async def test_vanished_tools_flag_a_warning_event_on_the_node(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        obs = make_ref_mcp_server(tools=("add",))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="math",
            mcp_server_id=server.id,
            mcp_tools=[{"name": "add"}, {"name": "vanished"}],
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        events = []

        async def capture(event):
            events.append(event)

        await runner.setup(send_event=capture)
        agent = runner.agents[worker.id]

        # The vanished tool is never granted; the live one still is.
        assert "add" in agent.tools
        assert "vanished" not in agent.tools

        warnings = [e for e in events if e.get("type") == "warning"]
        assert len(warnings) == 1
        assert warnings[0]["node_id"] == str(tool.id)
        assert "1 of 2 enabled tools unavailable" in warnings[0]["message"]

        await runner.release_mcp_sessions()

    async def test_stale_session_mid_run_rehandshakes_once_and_survives(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        """Spec §4.6 acceptance: a stale ``Mcp-Session-Id`` mid-run gets
        exactly one re-handshake and the run continues to a correct answer."""
        obs = make_ref_mcp_server(tools=("add",), stale_calls="once")
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        tool = FakeToolNode(
            name="math", mcp_server_id=server.id, mcp_tools=[{"name": "add"}]
        )
        canvas = FakeCanvas(
            agent_nodes=[worker], tool_nodes=[tool], edges=[_tool_access(worker, tool)]
        )

        runner = CanvasRunner(canvas)
        await runner.setup()
        agent = runner.agents[worker.id]

        result = await drive_agent(
            agent,
            [
                make_prediction("add", args={"a": 2, "b": 3}, thought="compute"),
                make_prediction("finish", thought="done"),
                {"process_result": "The sum is 5."},
            ],
        )

        assert result.trajectory["observation_0"] == "5"
        assert obs.initialize_count == 2  # one handshake + exactly one re-handshake

        await runner.release_mcp_sessions()

    async def test_colliding_grants_excluded_and_flagged_per_agent(
        self, make_ref_mcp_server, test_session, _compile_stub
    ):
        """Spec §4.5: two Tool Nodes granting the same tool name — per-agent
        first-come wins, the later collider is dropped and flagged."""
        obs = make_ref_mcp_server(tools=("add",))
        server = await _register_server(test_session, obs.url)
        worker = FakeAgentNode(name="Worker")
        node_a = FakeToolNode(
            name="first", mcp_server_id=server.id, mcp_tools=[{"name": "add"}]
        )
        node_b = FakeToolNode(
            name="second", mcp_server_id=server.id, mcp_tools=[{"name": "add"}]
        )
        canvas = FakeCanvas(
            agent_nodes=[worker],
            tool_nodes=[node_a, node_b],
            edges=[
                _tool_access(worker, node_a),
                _tool_access(worker, node_b),
            ],
        )

        runner = CanvasRunner(canvas)
        events = []

        async def capture(event):
            events.append(event)

        await runner.setup(send_event=capture)
        agent = runner.agents[worker.id]

        # First-come wins inside the ReAct tool dict — no silent later-merge.
        assert agent.tools["add"].func.node_id == node_a.id
        warnings = [
            e for e in events if e.get("type") == "warning" and "dropped" in e.get("message", "")
        ]
        assert len(warnings) == 1
        assert warnings[0]["node_id"] == str(node_b.id)

        await runner.release_mcp_sessions()
