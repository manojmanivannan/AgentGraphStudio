import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beeai_framework.backend.chat import ChatModel
from pydantic import ValidationError

from canvas_server.runner import CanvasRunner, RouterDecision


class FakeCanvas:
    def __init__(self, id=None, agent_nodes=None, tool_nodes=None, edges=None):
        self.id = id or uuid.uuid4()
        self.agent_nodes = agent_nodes or []
        self.tool_nodes = tool_nodes or []
        self.edges = edges or []


class FakeAgentNode:
    def __init__(self, id=None, name="", role="", instructions="", model_name="ollama:llama3.1", agent_type="worker"):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = role
        self.instructions = instructions
        self.model_name = model_name
        self.agent_type = agent_type
        self.position_x = 0
        self.position_y = 0


class TestRouterDecision:
    def test_routing_decision(self):
        d = RouterDecision(
            thought="Need to do math",
            action="transfer_to_MathAgent",
            action_input="what is 2+3",
        )
        assert d.thought == "Need to do math"
        assert d.action == "transfer_to_MathAgent"
        assert d.action_input == "what is 2+3"
        assert d.final_answer is None

    def test_final_answer_decision(self):
        d = RouterDecision(
            thought="I have the answer",
            final_answer="The result is 5",
        )
        assert d.final_answer == "The result is 5"
        assert d.action is None

    def test_validate_missing_thought(self):
        with pytest.raises(ValidationError):
            RouterDecision()


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

        with patch.object(ChatModel, "from_name") as mock_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_from_name.return_value = mock_llm

            runner = CanvasRunner(canvas)
            await runner.setup()

            assert len(runner.llms) == 1
            assert len(runner.agents) == 1
            assert list(runner.llms.keys())[0] == agent.id
            assert list(runner.agents.keys())[0] == agent.id

    async def test_setup_with_router_and_workers(self):
        master = FakeAgentNode(name="Master", agent_type="router")
        worker = FakeAgentNode(name="Worker", agent_type="worker")

        canvas = FakeCanvas(agent_nodes=[master, worker])

        with patch.object(ChatModel, "from_name") as mock_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_from_name.return_value = mock_llm

            runner = CanvasRunner(canvas)
            await runner.setup()

            assert len(runner.llms) == 2
            assert len(runner.agents) == 2

    async def test_router_loop_routes_to_worker(self):
        master = FakeAgentNode(
            id=uuid.uuid4(), name="Master", role="Router", agent_type="router", model_name="ollama:llama3.1"
        )
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="MathAgent", role="Math expert", agent_type="worker", model_name="ollama:llama3.1"
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

        with patch.object(ChatModel, "from_name") as mock_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_llm.run = AsyncMock()
            mock_from_name.return_value = mock_llm

            routing_decision = RouterDecision(
                thought="This is a math question",
                action="transfer_to_MathAgent",
                action_input="what is 2+3",
            )

            worker_response = MagicMock()
            worker_response.iterations = []
            worker_response.result = MagicMock()
            worker_response.result.text = "The answer is 5"
            worker_response.get_text_content = MagicMock(return_value="The answer is 5")

            mock_llm.run.side_effect = [
                MagicMock(output_structured=routing_decision, get_text_content=lambda: ""),
                worker_response,
            ]

            runner = CanvasRunner(canvas)
            await runner.run("what is 2+3", collect)

            event_types = [e["type"] for e in events]
            assert "run_start" in event_types
            assert "handoff" in event_types
            assert "agent_start" in event_types
            assert "final_answer" in event_types
            assert "run_complete" in event_types

            handoff_events = [e for e in events if e["type"] == "handoff"]
            assert len(handoff_events) >= 1
            assert handoff_events[0]["from"] == "Master"
            assert handoff_events[0]["to"] == "MathAgent"

    async def test_router_loop_final_answer_direct(self):
        master = FakeAgentNode(
            id=uuid.uuid4(), name="Master", role="Router", agent_type="router", model_name="ollama:llama3.1"
        )

        canvas = FakeCanvas(agent_nodes=[master])
        events = []

        async def collect(event):
            events.append(event)

        with patch.object(ChatModel, "from_name") as mock_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_llm.run = AsyncMock()
            mock_from_name.return_value = mock_llm

            routing_decision = RouterDecision(
                thought="Simple question, I'll answer directly",
                final_answer="The answer is 42",
            )

            mock_llm.run.return_value = MagicMock(
                output_structured=routing_decision,
                get_text_content=lambda: "",
            )

            runner = CanvasRunner(canvas)
            await runner.run("what is the answer?", collect)

            final_answers = [e for e in events if e["type"] == "final_answer"]
            assert len(final_answers) >= 1

    async def test_worker_run_emits_events(self):
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="Worker", agent_type="worker", model_name="ollama:llama3.1"
        )

        canvas = FakeCanvas(agent_nodes=[worker])
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)

        runner.llms[worker.id] = MagicMock(spec=ChatModel)
        runner.node_map[worker.id] = worker
        runner.agents[worker.id] = MagicMock()
        runner.agents[worker.id].run = AsyncMock(side_effect=Exception("test error"))
        runner.setup = AsyncMock()

        await runner.run("do work", collect)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "agent_start" in event_types
        assert "error" in event_types
        assert "run_complete" in event_types
