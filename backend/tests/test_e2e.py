import copy
import json
import pathlib
import uuid
from unittest.mock import AsyncMock, patch

import dspy
import pytest

from canvas_server.runner import CanvasRunner

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


def _make_prediction(process_result="", trajectory=None):
    trajectory = trajectory or {"thought_0": "", "tool_name_0": "finish", "tool_args_0": {}}
    return dspy.Prediction(process_result=process_result, trajectory=trajectory)


def _mock_worker_result(text: str):
    return _make_prediction(process_result=text)


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


class FakeNode:
    def __init__(self, data):
        self.id = uuid.UUID(data["id"])
        self.name = data["name"]
        self.role = data.get("role", "")
        self.instructions = data.get("instructions", "")
        self.model_name = data.get("model_name", "ollama:gemma4:31b")
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

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()

        # Build node map
        for node in canvas.agent_nodes:
            runner.node_map[node.id] = node

        # Register worker agents
        math_agent = canvas.agent_nodes[1]  # MathAgent
        weather_agent = canvas.agent_nodes[2]  # WeatherAgent

        runner.agents[math_agent.id] = _make_agent_mock("2 + 3 = 5")
        runner.agents[weather_agent.id] = _make_agent_mock("Sunny 20C")

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            mock_builder.return_value = _make_router_mock(
                "2 + 3 = 5",
                trajectory={
                    "thought_0": "This is a math question, routing to MathAgent",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 2+3"},
                    "observation_0": "2 + 3 = 5",
                    "thought_1": "I now know the answer",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            await runner.run("what is 2+3", collect, target_agent_id=canvas.agent_nodes[0].id)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "run_complete" in event_types

    @pytest.mark.asyncio
    async def test_router_routes_weather_question_to_weather_agent(self):
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()

        for node in canvas.agent_nodes:
            runner.node_map[node.id] = node

        math_agent = canvas.agent_nodes[1]
        weather_agent = canvas.agent_nodes[2]

        runner.agents[math_agent.id] = _make_agent_mock("2 + 3 = 5")
        runner.agents[weather_agent.id] = _make_agent_mock("Sunny 20C")

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            mock_builder.return_value = _make_router_mock(
                "Sunny 20C",
                trajectory={
                    "thought_0": "This is a weather question, routing to WeatherAgent",
                    "tool_name_0": "transfer_to_WeatherAgent",
                    "tool_args_0": {"task": "what is the weather in Paris?"},
                    "observation_0": "Sunny 20C",
                    "thought_1": "I now know the answer",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            await runner.run("what is the weather in Paris?", collect, target_agent_id=canvas.agent_nodes[0].id)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "run_complete" in event_types

    @pytest.mark.asyncio
    async def test_router_produces_final_answer_after_worker_result(self):
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()

        for node in canvas.agent_nodes:
            runner.node_map[node.id] = node

        math_agent = canvas.agent_nodes[1]
        weather_agent = canvas.agent_nodes[2]

        runner.agents[math_agent.id] = _make_agent_mock("4")
        runner.agents[weather_agent.id] = _make_agent_mock("")

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            mock_builder.return_value = _make_router_mock(
                "4",
                trajectory={
                    "thought_0": "Routing math question",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 2+2"},
                    "observation_0": "4",
                    "thought_1": "I now know the answer",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )

            await runner.run("what is 2+2", collect, target_agent_id=canvas.agent_nodes[0].id)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        assert len(final_answers) >= 1
        assert "run_complete" in [e["type"] for e in events]


class TestE2EAPIIntegration:
    @pytest.mark.asyncio
    async def test_import_demo_team_via_api(self, authed_client):
        team = _make_team_with_fresh_ids(load_demo_team())

        create_resp = await authed_client.post(
            "/api/canvases", json={"name": team["name"]}
        )
        assert create_resp.status_code == 200
        canvas_id = create_resp.json()["id"]

        save_resp = await authed_client.put(
            f"/api/canvases/{canvas_id}",
            json={"name": team["name"], "nodes": team["nodes"], "edges": team["edges"]},
        )
        assert save_resp.status_code == 200

        get_resp = await authed_client.get(f"/api/canvases/{canvas_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["name"] == "Demo Team"
        assert len(body["nodes"]["agents"]) == 3
        assert len(body["edges"]) == 2

    @pytest.mark.asyncio
    async def test_export_import_round_trip_of_demo_team(self, authed_client):
        team = _make_team_with_fresh_ids(load_demo_team())

        create_resp = await authed_client.post(
            "/api/canvases", json={"name": team["name"]}
        )
        canvas_id = create_resp.json()["id"]

        await authed_client.put(
            f"/api/canvases/{canvas_id}",
            json={"name": team["name"], "nodes": team["nodes"], "edges": team["edges"]},
        )

        export_resp = await authed_client.get(f"/api/canvases/{canvas_id}/export")
        assert export_resp.status_code == 200
        exported = export_resp.json()
        assert exported["name"] == "Demo Team"
        assert len(exported["nodes"]["agents"]) == 3
        assert len(exported["edges"]) == 2

        imported_payload = _make_team_with_fresh_ids(exported)
        import_resp = await authed_client.post("/api/canvases/import", json=imported_payload)
        assert import_resp.status_code == 200
        imported = import_resp.json()
        assert imported["name"] == "Demo Team"
        assert len(imported["nodes"]["agents"]) == 3

    @pytest.mark.asyncio
    async def test_demo_team_agents_and_edges_persist_correctly(self, authed_client):
        team = _make_team_with_fresh_ids(load_demo_team())

        create_resp = await authed_client.post(
            "/api/canvases", json={"name": team["name"]}
        )
        canvas_id = create_resp.json()["id"]

        await authed_client.put(
            f"/api/canvases/{canvas_id}",
            json={"name": team["name"], "nodes": team["nodes"], "edges": team["edges"]},
        )

        get_resp = await authed_client.get(f"/api/canvases/{canvas_id}")
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

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()

        for node in canvas.agent_nodes:
            runner.node_map[node.id] = node

        math_agent = canvas.agent_nodes[1]
        weather_agent = canvas.agent_nodes[2]

        runner.agents[math_agent.id] = _make_agent_mock("4")
        runner.agents[weather_agent.id] = _make_agent_mock("")

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            mock_builder.return_value = _make_router_mock(
                "4",
                trajectory={
                    "thought_0": "Math question, routing to MathAgent",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 2+2"},
                    "observation_0": "4",
                    "thought_1": "Got answer from MathAgent",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            await runner.run("what is 2+2", collect, target_agent_id=canvas.agent_nodes[0].id)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "run_complete" in event_types

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

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()

        for node in canvas.agent_nodes:
            runner.node_map[node.id] = node

        math_agent = canvas.agent_nodes[1]
        weather_agent = canvas.agent_nodes[2]

        runner.agents[math_agent.id] = _make_agent_mock("")
        runner.agents[weather_agent.id] = _make_agent_mock("It is sunny today")

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            mock_builder.return_value = _make_router_mock(
                "It is sunny today",
                trajectory={
                    "thought_0": "Weather question, routing to WeatherAgent",
                    "tool_name_0": "transfer_to_WeatherAgent",
                    "tool_args_0": {"task": "what is the weather in London?"},
                    "observation_0": "It is sunny today",
                    "thought_1": "Got answer from WeatherAgent",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            await runner.run("what is the weather in London?", collect, target_agent_id=canvas.agent_nodes[0].id)

        final_answers = [e for e in events if e["type"] == "final_answer"]
        all_texts = " ".join(str(e.get("content", "")) for e in final_answers).lower()
        assert "sunny" in all_texts, f"should mention weather, got: {all_texts[:500]}"

    @pytest.mark.asyncio
    async def test_event_sequence_follows_expected_order(self):
        team = load_demo_team()
        canvas = FakeCanvas(team)
        events = []

        async def collect(event):
            events.append(event)

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()

        for node in canvas.agent_nodes:
            runner.node_map[node.id] = node

        math_agent = canvas.agent_nodes[1]
        weather_agent = canvas.agent_nodes[2]

        runner.agents[math_agent.id] = _make_agent_mock("15")
        runner.agents[weather_agent.id] = _make_agent_mock("")

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
            mock_builder.return_value = _make_router_mock(
                "15",
                trajectory={
                    "thought_0": "Math question, routing to MathAgent",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 10 + 5?"},
                    "observation_0": "15",
                    "thought_1": "Got result from MathAgent",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            await runner.run("what is 10 + 5?", collect, target_agent_id=canvas.agent_nodes[0].id)

        event_types = [e["type"] for e in events]
        assert "run_start" in event_types
        assert "run_complete" in event_types
