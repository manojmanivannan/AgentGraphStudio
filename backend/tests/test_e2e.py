import json
import uuid
import copy
import pathlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from canvas_server.runner import CanvasRunner, RouterDecision
from beeai_framework.backend.chat import ChatModel

TEAMS_DIR = pathlib.Path(__file__).parent / "teams"
DEMO_TEAM_PATH = TEAMS_DIR / "demo_team.json"


def load_demo_team():
    with open(DEMO_TEAM_PATH) as f:
        return json.load(f)


def _make_team_with_fresh_ids(team_data):
    """Clone team data with fresh random UUIDs for isolation."""
    team = copy.deepcopy(team_data)
    id_map = {}
    for agent in team["nodes"]["agents"]:
        new_id = str(uuid.uuid4())
        id_map[agent["id"]] = new_id
        agent["id"] = new_id
    for tool in team["nodes"]["tools"]:
        new_id = str(uuid.uuid4())
        id_map[tool["id"]] = new_id
        tool["id"] = new_id
    for edge in team["edges"]:
        edge["id"] = str(uuid.uuid4())
        edge["source_node_id"] = id_map.get(
            edge["source_node_id"], edge["source_node_id"]
        )
        edge["target_node_id"] = id_map.get(
            edge["target_node_id"], edge["target_node_id"]
        )
    return team


class FakeNode:
    def __init__(self, data):
        self.id = uuid.UUID(data["id"])
        self.name = data["name"]
        self.role = data.get("role", "")
        self.instructions = data.get("instructions", "")
        self.model_name = data.get("model_name", "ollama:granite4.1:3b")
        self.agent_type = data.get("agent_type", "worker")
        self.position_x = data.get("position_x", 0)
        self.position_y = data.get("position_y", 0)
        self.code = data.get("code", "")


class FakeEdge:
    def __init__(self, data):
        self.id = uuid.UUID(data["id"])
        self.canvas_id = uuid.uuid4()
        self.source_node_id = uuid.UUID(data["source_node_id"])
        self.target_node_id = uuid.UUID(data["target_node_id"])
        self.edge_type = data.get("edge_type", "handoff")


class FakeCanvas:
    def __init__(self, team_data):
        self.id = uuid.uuid4()
        self.name = team_data.get("name", "Untitled Canvas")
        self.agent_nodes = []
        self.tool_nodes = []
        self.edges = []

        nodes = team_data.get("nodes", {})
        for agent_data in nodes.get("agents", []):
            self.agent_nodes.append(FakeNode(agent_data))
        for tool_data in nodes.get("tools", []):
            self.tool_nodes.append(FakeNode(tool_data))
        for edge_data in team_data.get("edges", []):
            self.edges.append(FakeEdge(edge_data))


class TestDemoTeamValidation:
    def test_demo_team_file_exists(self):
        assert DEMO_TEAM_PATH.exists(), f"demo_team.json not found at {DEMO_TEAM_PATH}"

    def test_demo_team_is_valid_json(self):
        data = load_demo_team()
        assert isinstance(data, dict)
        assert "name" in data
        assert "nodes" in data
        assert "edges" in data

    def test_demo_team_has_required_agents(self):
        data = load_demo_team()
        agents = data["nodes"]["agents"]
        assert len(agents) >= 3
        names = {a["name"] for a in agents}
        assert "Master" in names
        assert "MathAgent" in names
        assert "WeatherAgent" in names

    def test_demo_team_router_has_handoff_edges(self):
        data = load_demo_team()
        master = next(a for a in data["nodes"]["agents"] if a["agent_type"] == "router")
        edges = data["edges"]
        handoffs = [
            e
            for e in edges
            if e["source_node_id"] == master["id"] and e["edge_type"] == "handoff"
        ]
        assert len(handoffs) >= 2

    def test_demo_team_validates_against_pydantic_models(self):
        from canvas_server.models.api import CanvasSaveRequest

        data = load_demo_team()
        canvas = CanvasSaveRequest(**data)
        assert canvas.name == "Demo Team"


class TestE2ERouterMath:
    @pytest.mark.asyncio
    async def test_router_routes_math_question_to_math_agent(self):
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        with patch.object(ChatModel, "from_name") as m_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_llm.run = AsyncMock()
            m_from_name.return_value = mock_llm

            route_decision = RouterDecision(
                thought="This is a math question, routing to MathAgent",
                action="transfer_to_MathAgent",
                action_input="what is 2+3",
            )

            worker_response = MagicMock()
            worker_response.iterations = []
            worker_response.result = MagicMock()
            worker_response.result.text = "2 + 3 = 5"
            worker_response.get_text_content = MagicMock(return_value="2 + 3 = 5")

            mock_llm.run.side_effect = [
                MagicMock(
                    output_structured=route_decision, get_text_content=lambda: ""
                ),
                worker_response,
            ]

            runner = CanvasRunner(canvas)
            await runner.run("what is 2+3", collect)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "handoff" in event_types
        assert "run_complete" in event_types

        handoffs = [e for e in events if e["type"] == "handoff"]
        assert len(handoffs) >= 1
        assert handoffs[0]["from"] == "Master"
        assert handoffs[0]["to"] == "MathAgent"

        agent_starts = [e for e in events if e["type"] == "agent_start"]
        assert any(e["agent"] == "MathAgent" for e in agent_starts)

    @pytest.mark.asyncio
    async def test_router_routes_weather_question_to_weather_agent(self):
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        with patch.object(ChatModel, "from_name") as m_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_llm.run = AsyncMock()
            m_from_name.return_value = mock_llm

            route_decision = RouterDecision(
                thought="This is a weather question, routing to WeatherAgent",
                action="transfer_to_WeatherAgent",
                action_input="what is the weather in Paris?",
            )

            worker_response = MagicMock()
            worker_response.iterations = []
            worker_response.result = MagicMock()
            worker_response.result.text = "Sunny 20C"
            worker_response.get_text_content = MagicMock(return_value="Sunny 20C")

            mock_llm.run.side_effect = [
                MagicMock(
                    output_structured=route_decision, get_text_content=lambda: ""
                ),
                worker_response,
            ]

            runner = CanvasRunner(canvas)
            await runner.run("what is the weather in Paris?", collect)

        handoffs = [e for e in events if e["type"] == "handoff"]
        assert len(handoffs) >= 1
        assert handoffs[0]["from"] == "Master"
        assert handoffs[0]["to"] == "WeatherAgent"

    @pytest.mark.asyncio
    async def test_router_produces_final_answer_after_worker_result(self):
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        with patch.object(ChatModel, "from_name") as m_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_llm.run = AsyncMock()
            m_from_name.return_value = mock_llm

            route_decision = RouterDecision(
                thought="Routing math question",
                action="transfer_to_MathAgent",
                action_input="what is 2+2",
            )

            final_decision = RouterDecision(
                thought="I now know the final answer from MathAgent",
                final_answer="4",
            )

            worker_response = MagicMock()
            worker_response.iterations = []
            worker_response.result = MagicMock()
            worker_response.result.text = "4"
            worker_response.get_text_content = MagicMock(return_value="4")

            mock_llm.run.side_effect = [
                MagicMock(
                    output_structured=route_decision, get_text_content=lambda: ""
                ),
                worker_response,
                MagicMock(
                    output_structured=final_decision, get_text_content=lambda: ""
                ),
            ]

            runner = CanvasRunner(canvas)
            await runner.run("what is 2+2", collect)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert len(final_answers) >= 2

        event_types = [e["type"] for e in events]
        assert "run_complete" in event_types


class TestE2EAPIIntegration:
    @pytest.mark.asyncio
    async def test_import_demo_team_via_api(self, test_client):
        team = _make_team_with_fresh_ids(load_demo_team())

        create_resp = await test_client.post(
            "/api/canvases", json={"name": team["name"]}
        )
        assert create_resp.status_code == 200
        canvas_id = create_resp.json()["id"]

        save_resp = await test_client.put(
            f"/api/canvases/{canvas_id}",
            json={"name": team["name"], "nodes": team["nodes"], "edges": team["edges"]},
        )
        assert save_resp.status_code == 200

        get_resp = await test_client.get(f"/api/canvases/{canvas_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["name"] == "Demo Team"
        assert len(body["nodes"]["agents"]) == 3
        assert len(body["edges"]) == 2

    @pytest.mark.asyncio
    async def test_export_import_round_trip_of_demo_team(self, test_client):
        team = _make_team_with_fresh_ids(load_demo_team())

        create_resp = await test_client.post(
            "/api/canvases", json={"name": team["name"]}
        )
        canvas_id = create_resp.json()["id"]

        await test_client.put(
            f"/api/canvases/{canvas_id}",
            json={"name": team["name"], "nodes": team["nodes"], "edges": team["edges"]},
        )

        export_resp = await test_client.get(f"/api/canvases/{canvas_id}/export")
        assert export_resp.status_code == 200
        exported = export_resp.json()
        assert exported["name"] == "Demo Team"
        assert len(exported["nodes"]["agents"]) == 3
        assert len(exported["edges"]) == 2

        import_resp = await test_client.post("/api/canvases/import", json=exported)
        assert import_resp.status_code == 200
        imported = import_resp.json()
        assert imported["name"] == "Demo Team"
        assert len(imported["nodes"]["agents"]) == 3

    @pytest.mark.asyncio
    async def test_demo_team_agents_and_edges_persist_correctly(self, test_client):
        team = load_demo_team()

        create_resp = await test_client.post(
            "/api/canvases", json={"name": team["name"]}
        )
        canvas_id = create_resp.json()["id"]

        await test_client.put(
            f"/api/canvases/{canvas_id}",
            json={"name": team["name"], "nodes": team["nodes"], "edges": team["edges"]},
        )

        get_resp = await test_client.get(f"/api/canvases/{canvas_id}")
        body = get_resp.json()

        agent_types = {a["agent_type"] for a in body["nodes"]["agents"]}
        assert "router" in agent_types
        assert "worker" in agent_types

        edge_types = {e["edge_type"] for e in body["edges"]}
        assert edge_types == {"handoff"}

        agent_names = {a["name"] for a in body["nodes"]["agents"]}
        assert agent_names == {"Master", "MathAgent", "WeatherAgent"}


class TestE2ERealLLM:
    """End-to-end tests that call actual LLMs. Requires Ollama running at LLM_BASE_URL."""

    @pytest.mark.asyncio
    async def test_real_llm_math_question_returns_answer(self):
        """Ask 'what is 2+2' and verify the system produces a final answer with '4'."""
        from canvas_server.config import settings

        team = _make_team_with_fresh_ids(load_demo_team())
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        await runner.run("what is 2+2", collect)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types, "should emit run_start"
        assert "run_complete" in event_types, "should complete"

        handoffs = [e for e in events if e["type"] == "handoff"]
        assert len(handoffs) >= 1, "should hand off to a worker agent"

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert (
            len(final_answers) >= 2
        ), "should have router final_answer + worker final_answer"

        all_texts = " ".join(str(e.get("content", "")) for e in final_answers)
        assert "4" in all_texts, f"should find '4' in answers, got: {all_texts[:500]}"

    @pytest.mark.asyncio
    async def test_real_llm_weather_question_gets_routed(self):
        """Ask about weather and verify it routes to WeatherAgent."""
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        await runner.run("what is the weather in London?", collect)

        handoffs = [e for e in events if e["type"] == "handoff"]
        assert any(
            h["to"] == "WeatherAgent" for h in handoffs
        ), f"should route to WeatherAgent, handoffs: {handoffs}"

        final_answers = [e for e in events if e["type"] == "final_answer"]
        all_texts = " ".join(str(e.get("content", "")) for e in final_answers).lower()
        assert (
            "sunny" in all_texts or "20c" in all_texts
        ), f"should mention weather, got: {all_texts[:500]}"

    @pytest.mark.asyncio
    async def test_real_llm_does_not_loop_infinitely(self):
        """Verify the router stops within max_rounds (10) and produces a result."""
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        await runner.run("what is 3 * 7?", collect)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        router_answers = [e for e in final_answers if e.get("agent") == "Master"]

        assert (
            len(router_answers) >= 1
        ), "router should produce at least one final answer"

        router_text = router_answers[-1].get("content", "")
        assert (
            "maximum rounds" not in router_text
        ), f"router should not hit max rounds, got: {router_text}"

    @pytest.mark.asyncio
    async def test_real_llm_handoff_event_sequence(self):
        """Verify the event sequence follows: run_start -> thought -> handoff -> agent_start -> final_answer -> run_complete."""
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        await runner.run("what is 10 + 5?", collect)

        event_types = [e["type"] for e in events]

        assert "run_start" in event_types
        assert "thought" in event_types, "router should emit thoughts"
        assert "handoff" in event_types, "should hand off to a worker"
        assert "agent_start" in event_types, "worker should start"
        assert "final_answer" in event_types, "should produce final answer"
        assert "run_complete" in event_types, "should complete"
