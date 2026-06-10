import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import dspy

from canvas_server.runner import CanvasRunner


class FakeCanvas:
    def __init__(self, id=None, agent_nodes=None, tool_nodes=None, edges=None):
        self.id = id or uuid.uuid4()
        self.agent_nodes = agent_nodes or []
        self.tool_nodes = tool_nodes or []
        self.edges = edges or []


class FakeAgentNode:
    def __init__(
        self,
        id=None,
        name="",
        role="",
        instructions="",
        model_name="ollama:llama3.1",
        agent_type="worker",
    ):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = role
        self.instructions = instructions
        self.model_name = model_name
        self.agent_type = agent_type
        self.position_x = 0
        self.position_y = 0


def _make_prediction(process_result="", trajectory=None):
    trajectory = trajectory or {
        "thought_0": "",
        "tool_name_0": "finish",
        "tool_args_0": {},
    }
    return dspy.Prediction(process_result=process_result, trajectory=trajectory)


def _make_agent_mock(text="Done!"):
    pred = _make_prediction(process_result=text)
    agent = AsyncMock(return_value=pred)
    agent.aforward = AsyncMock(return_value=pred)
    return agent


def _make_router_mock(result_text="", trajectory=None):
    pred = _make_prediction(process_result=result_text, trajectory=trajectory or {})
    router = AsyncMock(return_value=pred)
    router.aforward = AsyncMock(return_value=pred)
    return router


class TestCanvasRunner:
    async def test_empty_canvas_run_emits_error(self):
        canvas = FakeCanvas()
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        await runner.run("test prompt", collect)

        assert len(events) >= 1
        assert events[0]["type"] == "error"
        assert "no agents" in events[0]["message"]

    async def test_setup_with_single_worker(self):
        agent = FakeAgentNode(name="Worker1", agent_type="worker")
        canvas = FakeCanvas(agent_nodes=[agent])

        runner = CanvasRunner(canvas)
        await runner.setup()

        assert len(runner.agents) == 1
        assert list(runner.agents.keys())[0] == agent.id

    async def test_setup_with_router_and_workers(self):
        master = FakeAgentNode(name="Master", agent_type="router")
        worker = FakeAgentNode(name="Worker", agent_type="worker")
        math_agent = FakeAgentNode(name="MathAgent", agent_type="worker")

        canvas = FakeCanvas(agent_nodes=[master, worker, math_agent])

        runner = CanvasRunner(canvas)
        await runner.setup()

        # Router agents are built at run time, so only workers are in agents
        assert runner.agents.keys() == {worker.id, math_agent.id}

    async def test_setup_with_router_only(self):
        master = FakeAgentNode(name="Master", agent_type="router")
        canvas = FakeCanvas(agent_nodes=[master])

        runner = CanvasRunner(canvas)
        await runner.setup()

        assert len(runner.agents) == 0  # no workers to build

    async def test_worker_run_returns_result(self):
        worker = FakeAgentNode(
            id=uuid.uuid4(),
            name="Worker",
            agent_type="worker",
            model_name="ollama:llama3.1",
        )

        canvas = FakeCanvas(agent_nodes=[worker])
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        runner.node_map[worker.id] = worker
        runner.setup = AsyncMock()
        runner.agents[worker.id] = _make_agent_mock("The answer is 42")

        await runner.run("what is the answer?", collect)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "final_answer" in event_types
        assert "run_complete" in event_types

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert any("42" in str(e.get("content", "")) for e in final_answers)

    async def test_worker_run_emits_events_on_error(self):
        worker = FakeAgentNode(
            id=uuid.uuid4(),
            name="Worker",
            agent_type="worker",
            model_name="ollama:llama3.1",
        )

        canvas = FakeCanvas(agent_nodes=[worker])
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)

        runner.node_map[worker.id] = worker
        runner.setup = AsyncMock()
        runner.agents[worker.id] = AsyncMock(side_effect=Exception("test error"))

        await runner.run("do work", collect)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "run_complete" in event_types

    async def test_router_routes_to_worker_and_produces_final_answer(self):
        master = FakeAgentNode(
            id=uuid.uuid4(),
            name="Master",
            role="Router",
            agent_type="router",
            model_name="ollama:llama3.1",
        )
        worker = FakeAgentNode(
            id=uuid.uuid4(),
            name="MathAgent",
            role="Math expert",
            agent_type="worker",
            model_name="ollama:llama3.1",
        )

        class FakeEdge:
            def __init__(self, source, target, edge_type):
                self.id = uuid.uuid4()
                self.canvas_id = uuid.uuid4()
                self.source_node_id = source
                self.target_node_id = target
                self.edge_type = edge_type

        canvas = FakeCanvas(
            agent_nodes=[master, worker],
            edges=[FakeEdge(master.id, worker.id, "handoff")],
        )

        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}
        runner.agents[worker.id] = _make_agent_mock("2 + 3 = 5")

        # router_result = _make_prediction(
        #     process_result="The answer is 5",
        #     trajectory={
        #         "thought_0": "This is a math question",
        #         "tool_name_0": "transfer_to_MathAgent",
        #         "tool_args_0": {"task": "what is 2+3"},
        #         "observation_0": "2 + 3 = 5",
        #         "thought_1": "I now know the answer",
        #         "tool_name_1": "finish",
        #         "tool_args_1": {},
        #     },
        # )

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            router_mock = _make_router_mock(
                "The answer is 5",
                trajectory={
                    "thought_0": "This is a math question",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 2+3"},
                    "observation_0": "2 + 3 = 5",
                    "thought_1": "I now know the answer",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            mock_builder.return_value = router_mock

            # Use target_agent_id so RouterExecution is selected (not ChainExecution)
            await runner.run("what is 2+3", collect, target_agent_id=master.id)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "final_answer" in event_types
        assert "run_complete" in event_types

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert len(final_answers) >= 1

    async def test_make_handoff_tool_defers_agent_lookup(self):
        """Router→router handoff: target agent lookup is deferred to call time."""
        master = FakeAgentNode(
            id=uuid.uuid4(),
            name="Master",
            role="Router",
            agent_type="router",
        )
        math_router = FakeAgentNode(
            id=uuid.uuid4(),
            name="MathTeam",
            role="Math expert team",
            agent_type="router",
        )
        math_worker = FakeAgentNode(
            id=uuid.uuid4(),
            name="FactorialAgent",
            role="FactorialExpert",
            agent_type="worker",
        )

        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(FakeCanvas(agent_nodes=[master, math_router, math_worker]))
        runner.node_map = {master.id: master, math_router.id: math_router, math_worker.id: math_worker}
        runner.agents[math_worker.id] = _make_agent_mock("6")

        # _make_handoff_tool should NOT crash even though math_router
        # is not yet in self.agents (it's a router, built lazily)
        tool = runner._make_handoff_tool(
            math_router.id, master.name, collect, history=""
        )
        assert tool.__name__ == "transfer_to_MathTeam"

    async def test_router_produces_final_answer_directly(self):
        master = FakeAgentNode(
            id=uuid.uuid4(),
            name="Master",
            role="Router",
            agent_type="router",
            model_name="ollama:llama3.1",
        )

        canvas = FakeCanvas(agent_nodes=[master])
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master}

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            router_mock = _make_router_mock(
                "The answer is 42",
                trajectory={
                    "thought_0": "Simple question, answering directly",
                    "tool_name_0": "finish",
                    "tool_args_0": {},
                },
            )
            mock_builder.return_value = router_mock

            await runner.run("what is the answer?", collect, target_agent_id=master.id)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert len(final_answers) >= 1

    async def test_setup_installs_tool_dependencies(self):
        class FakeToolNode:
            def __init__(self, name, code, dependencies=None):
                self.id = uuid.uuid4()
                self.name = name
                self.code = code
                self.dependencies = dependencies or []

        tool = FakeToolNode(
            name="dummy_tool",
            code="def dummy_tool():\n    pass",
            dependencies=["pandas", "numpy", "numpy"]
        )
        canvas = FakeCanvas(tool_nodes=[tool])
        runner = CanvasRunner(canvas)

        # Mock compile_tool_from_code to avoid actually calling the sandbox during compilation
        # and mock AgentFactory.build_workers to avoid building workers
        with patch("canvas_server.runner.runner.PackageManager") as mock_pm_class, \
             patch("canvas_server.runner.tool_registry.compile_tool_from_code", new_callable=AsyncMock) as mock_compile, \
             patch("canvas_server.runner.agent_factory.AgentFactory.build_workers", new_callable=AsyncMock) as mock_build_workers:

            mock_pm = MagicMock()
            mock_pm.install_packages = AsyncMock()
            mock_pm_class.return_value = mock_pm

            await runner.setup()

            # Verify that install_packages was called with the sorted list of unique dependencies
            mock_pm.install_packages.assert_called_once_with(["numpy", "pandas"])

    async def test_llm_validation_failure_raises_configuration_error(self):
        import pytest
        from canvas_server.exceptions import LLMConfigurationError
        canvas = FakeCanvas()
        runner = CanvasRunner(canvas)
        runner._lm.acall = AsyncMock(side_effect=Exception("Connection refused"))

        import os
        with patch.dict(os.environ, {"TEST_VALIDATE_LLM": "true"}):
            with pytest.raises(LLMConfigurationError) as exc_info:
                await runner.setup()
            assert "LLM configuration is incorrect" in str(exc_info.value)

    async def test_memory_validation_failure_emits_warning(self):
        from canvas_server.runner.memory import MemoryManager
        MemoryManager._shared_memory = None

        agent = FakeAgentNode(name="Worker1", agent_type="worker")
        agent.enable_memory = True
        canvas = FakeCanvas(agent_nodes=[agent])

        runner = CanvasRunner(canvas)
        events = []
        async def collect(event):
            events.append(event)

        with patch.object(runner._lm, "acall", new_callable=AsyncMock), \
             patch("mem0.Memory.from_config", side_effect=Exception("Vector DB offline")):
            runner._conversation.persist_message = AsyncMock()

            await runner.setup(send_event=collect)

            assert len(events) == 1
            assert events[0]["type"] == "warning"
            assert "Memory/Message configuration is wrong" in events[0]["message"]

    async def test_memory_failure_propagates_to_agent_prompt_and_tools(self):
        from canvas_server.runner.memory import MemoryManager
        MemoryManager._shared_memory = None

        agent_node = FakeAgentNode(name="MemoryAgent", agent_type="worker")
        agent_node.enable_memory = True
        canvas = FakeCanvas(agent_nodes=[agent_node])

        runner = CanvasRunner(canvas)
        runner._conversation.persist_message = AsyncMock()

        import pytest
        # Mock memory initialization to fail with a Vector DB exception
        with patch.object(runner._lm, "acall", new_callable=AsyncMock), \
             patch("mem0.Memory.from_config", side_effect=Exception("Vector DB offline")):
            await runner.setup()

            # The agent should be constructed
            assert agent_node.id in runner.agents
            agent = runner.agents[agent_node.id]

            # The agent signature instructions should contain the warning about memory failure
            instructions = agent.react.signature.instructions
            assert "[SYSTEM WARNING]" in instructions
            assert "Vector DB offline" in instructions

            # The memory tools should be registered on the agent
            tool_names = list(agent.tools.keys())
            assert "store_memory" in tool_names
            assert "search_memories" in tool_names
            assert "get_all_memories" in tool_names

            # When calling store_memory tool, it should raise the Vector DB offline exception
            with pytest.raises(Exception) as exc_info:
                await agent.tools["store_memory"].acall(content="I am in Mumbai")
            assert "Vector DB offline" in str(exc_info.value)

    async def test_python_syntax_error_propagates_to_tool_output(self):
        from canvas_server.runner.memory import MemoryManager
        MemoryManager._shared_memory = None

        agent_node = FakeAgentNode(name="WorkerAgent", agent_type="worker")
        
        class FakeToolNode:
            def __init__(self, name, code, dependencies=None):
                self.id = uuid.uuid4()
                self.name = name
                self.code = code
                self.dependencies = dependencies or []

        # Tool node has bad python syntax
        tool_node = FakeToolNode(
            name="broken_tool",
            code="def broken_tool(:",
        )
        
        class FakeEdge:
            def __init__(self, source, target, edge_type):
                self.id = uuid.uuid4()
                self.canvas_id = uuid.uuid4()
                self.source_node_id = source
                self.target_node_id = target
                self.edge_type = edge_type

        edges = [FakeEdge(agent_node.id, tool_node.id, "tool_access")]
        canvas = FakeCanvas(agent_nodes=[agent_node], tool_nodes=[tool_node], edges=edges)

        runner = CanvasRunner(canvas)
        runner._conversation.persist_message = AsyncMock()

        # Compile should NOT raise an exception during setup
        with patch.object(runner._lm, "acall", new_callable=AsyncMock):
            await runner.setup()

            # The agent should be constructed
            assert agent_node.id in runner.agents
            agent = runner.agents[agent_node.id]

            # The tool should be registered
            assert "broken_tool" in agent.tools

            # Calling the tool should raise PythonSyntaxError
            import pytest
            from canvas_server.exceptions import PythonSyntaxError
            with pytest.raises(PythonSyntaxError):
                await agent.tools["broken_tool"].acall()

