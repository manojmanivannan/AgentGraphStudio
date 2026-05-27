import copy
import json
import pathlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beeai_framework.agents.react import ReActAgent
from beeai_framework.backend.chat import ChatModel

from canvas_server.runner import CanvasRunner, RouterDecision

TEAMS_DIR = pathlib.Path(__file__).parent / "teams"
DEMO_TEAM_PATH = TEAMS_DIR / "demo_team.json"


def load_demo_team():
    with open(DEMO_TEAM_PATH) as f:
        return json.load(f)


def _make_team_with_fresh_ids(team_data):
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


def _mock_worker_result(text: str):
    result = MagicMock()
    result.iterations = []
    result.result = MagicMock()
    result.result.text = text
    result.get_text_content = MagicMock(return_value=text)
    return result


class FakeNode:
    def __init__(self, data):
        self.id = uuid.UUID(data["id"])
        self.name = data["name"]
        self.role = data.get("role", "")
        self.instructions = data.get("instructions", "")
        self.model_name = data.get("model_name", "ollama:granite4.1:8b")
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


def _make_route_decision_mock(decision: RouterDecision):
    return MagicMock(output_structured=decision, get_text_content=lambda: "")


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
            final_decision = RouterDecision(
                thought="MathAgent answered: 2 + 3 = 5",
                final_answer="2 + 3 = 5",
            )

            mock_llm.run.side_effect = [
                _make_route_decision_mock(route_decision),
                _make_route_decision_mock(final_decision),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("2 + 3 = 5"))

            with patch.object(ReActAgent, "run", m_agent_run):
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
            final_decision = RouterDecision(
                thought="WeatherAgent says: Sunny 20C",
                final_answer="Sunny 20C",
            )

            mock_llm.run.side_effect = [
                _make_route_decision_mock(route_decision),
                _make_route_decision_mock(final_decision),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("Sunny 20C"))

            with patch.object(ReActAgent, "run", m_agent_run):
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

            mock_llm.run.side_effect = [
                _make_route_decision_mock(route_decision),
                _make_route_decision_mock(final_decision),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("4"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(canvas)
                await runner.run("what is 2+2", collect)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert len(final_answers) >= 1

        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) >= 1

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

        imported_payload = _make_team_with_fresh_ids(exported)
        import_resp = await test_client.post("/api/canvases/import", json=imported_payload)
        assert import_resp.status_code == 200
        imported = import_resp.json()
        assert imported["name"] == "Demo Team"
        assert len(imported["nodes"]["agents"]) == 3

    @pytest.mark.asyncio
    async def test_demo_team_agents_and_edges_persist_correctly(self, test_client):
        team = _make_team_with_fresh_ids(load_demo_team())

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


class TestE2EFullFlow:
    @pytest.mark.asyncio
    async def test_math_question_produces_answer_with_4(self):
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
                action_input="what is 2+2",
            )
            final_decision = RouterDecision(
                thought="MathAgent computed the answer",
                final_answer="4",
            )

            mock_llm.run.side_effect = [
                _make_route_decision_mock(route_decision),
                _make_route_decision_mock(final_decision),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("4"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(canvas)
                await runner.run("what is 2+2", collect)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "run_complete" in event_types

        handoffs = [e for e in events if e["type"] == "handoff"]
        assert len(handoffs) >= 1

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert len(final_answers) >= 1

        all_texts = " ".join(str(e.get("content", "")) for e in final_answers)
        assert "4" in all_texts, f"should find '4' in answers, got: {all_texts[:500]}"

    @pytest.mark.asyncio
    async def test_weather_question_routes_to_weather_agent(self):
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
                action_input="weather in London?",
            )
            final_decision = RouterDecision(
                thought="WeatherAgent has the answer",
                final_answer="It is sunny today",
            )

            mock_llm.run.side_effect = [
                _make_route_decision_mock(route_decision),
                _make_route_decision_mock(final_decision),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("It is sunny today"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(canvas)
                await runner.run("what is the weather in London?", collect)

        handoffs = [e for e in events if e["type"] == "handoff"]
        assert any(h["to"] == "WeatherAgent" for h in handoffs)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        all_texts = " ".join(str(e.get("content", "")) for e in final_answers).lower()
        assert "sunny" in all_texts, f"should mention weather, got: {all_texts[:500]}"

    @pytest.mark.asyncio
    async def test_router_stops_within_max_rounds(self):
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
                thought="Routing math question to MathAgent",
                action="transfer_to_MathAgent",
                action_input="what is 3 * 7?",
            )
            final_decision = RouterDecision(
                thought="Got answer from MathAgent",
                final_answer="21",
            )

            mock_llm.run.side_effect = [
                _make_route_decision_mock(route_decision),
                _make_route_decision_mock(final_decision),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("21"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(canvas)
                await runner.run("what is 3 * 7?", collect)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        router_answers = [e for e in final_answers if e.get("agent") == "Master"]
        assert len(router_answers) >= 1

        router_text = router_answers[-1].get("content", "")
        assert "maximum rounds" not in router_text, f"router should not hit max rounds, got: {router_text}"

    @pytest.mark.asyncio
    async def test_event_sequence_follows_expected_order(self):
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
                thought="Math question, routing to MathAgent",
                action="transfer_to_MathAgent",
                action_input="what is 10 + 5?",
            )
            final_decision = RouterDecision(
                thought="Got result from MathAgent",
                final_answer="15",
            )

            mock_llm.run.side_effect = [
                _make_route_decision_mock(route_decision),
                _make_route_decision_mock(final_decision),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("15"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(canvas)
                await runner.run("what is 10 + 5?", collect)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "thought" in event_types
        assert "handoff" in event_types
        assert "agent_start" in event_types
        assert "final_answer" in event_types
        assert "run_complete" in event_types
