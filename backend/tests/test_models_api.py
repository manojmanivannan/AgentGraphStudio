import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from canvas_server.models.api import (
    AgentNodeInput,
    AgentNodeResponse,
    CanvasNodesInput,
    CanvasNodesResponse,
    CanvasResponse,
    CanvasSaveRequest,
    CreateCanvasRequest,
    EdgeInput,
    ToolNodeInput,
)


class TestAgentNodeInput:
    def test_minimal_creation(self):
        agent = AgentNodeInput(id=uuid.uuid4())
        assert agent.name == "Agent"
        assert agent.agent_type == "worker"
        assert agent.model_name == "ollama:llama3.1"
        assert agent.position_x == 0
        assert agent.position_y == 0

    def test_all_fields(self):
        aid = uuid.uuid4()
        agent = AgentNodeInput(
            id=aid,
            name="WeatherBot",
            role="Weather expert",
            instructions="Answer weather queries",
            model_name="ollama:mistral",
            agent_type="router",
            position_x=100.5,
            position_y=200.3,
        )
        assert agent.id == aid
        assert agent.name == "WeatherBot"
        assert agent.role == "Weather expert"
        assert agent.instructions == "Answer weather queries"
        assert agent.model_name == "ollama:mistral"
        assert agent.agent_type == "router"
        assert agent.position_x == 100.5
        assert agent.position_y == 200.3

    def test_id_required(self):
        with pytest.raises(ValidationError):
            AgentNodeInput()


class TestAgentNodeResponse:
    def test_is_not_input_subclass(self):
        assert not issubclass(AgentNodeResponse, AgentNodeInput)

    def test_creation(self):
        aid = uuid.uuid4()
        cid = uuid.uuid4()
        resp = AgentNodeResponse(
            id=aid,
            canvas_id=cid,
            name="WeatherBot",
            role="Weather expert",
            instructions="Answer weather queries",
            model_name="ollama:mistral",
            agent_type="router",
            enable_plotting=True,
            enable_memory=True,
            enable_conversation_history=True,
            enable_rag=True,
            rag_chunk_size=1337,
            position_x=100.5,
            position_y=200.3,
        )
        assert resp.id == aid
        assert resp.canvas_id == cid
        assert resp.enable_rag is True
        assert resp.rag_chunk_size == 1337


class TestToolNodeInput:
    def test_minimal_creation(self):
        tool = ToolNodeInput(id=uuid.uuid4())
        assert tool.name == "Tool"
        assert tool.code == ""

    def test_with_code(self):
        tid = uuid.uuid4()
        tool = ToolNodeInput(
            id=tid,
            name="Calculator",
            code="def add(a, b): return a + b",
            position_x=50,
            position_y=60,
        )
        assert tool.id == tid
        assert tool.name == "Calculator"
        assert tool.code == "def add(a, b): return a + b"

    def test_id_required(self):
        with pytest.raises(ValidationError):
            ToolNodeInput()


class TestEdgeInput:
    def test_creation(self):
        eid = uuid.uuid4()
        src = uuid.uuid4()
        tgt = uuid.uuid4()
        edge = EdgeInput(id=eid, source_node_id=src, target_node_id=tgt, edge_type="handoff")
        assert edge.id == eid
        assert edge.source_node_id == src
        assert edge.target_node_id == tgt
        assert edge.edge_type == "handoff"

    def test_default_edge_type(self):
        edge = EdgeInput(id=uuid.uuid4(), source_node_id=uuid.uuid4(), target_node_id=uuid.uuid4())
        assert edge.edge_type == "tool_access"


class TestCanvasNodesInput:
    def test_defaults(self):
        nodes = CanvasNodesInput()
        assert nodes.agents == []
        assert nodes.tools == []

    def test_with_data(self):
        aid = uuid.uuid4()
        tid = uuid.uuid4()
        nodes = CanvasNodesInput(
            agents=[AgentNodeInput(id=aid, name="A1")],
            tools=[ToolNodeInput(id=tid, name="T1")],
        )
        assert len(nodes.agents) == 1
        assert len(nodes.tools) == 1
        assert nodes.agents[0].id == aid
        assert nodes.tools[0].id == tid


class TestCanvasSaveRequest:
    def test_minimal(self):
        req = CanvasSaveRequest()
        assert req.name == "Untitled Canvas"
        assert req.nodes.agents == []
        assert req.edges == []

    def test_with_nodes_and_edges(self):
        aid = uuid.uuid4()
        eid = uuid.uuid4()
        req = CanvasSaveRequest(
            name="My Canvas",
            nodes=CanvasNodesInput(agents=[AgentNodeInput(id=aid)]),
            edges=[EdgeInput(id=eid, source_node_id=aid, target_node_id=uuid.uuid4())],
        )
        assert req.name == "My Canvas"
        assert len(req.nodes.agents) == 1
        assert len(req.edges) == 1


class TestCanvasResponse:
    def test_creation(self):
        now = datetime.now(UTC)
        cid = uuid.uuid4()
        resp = CanvasResponse(
            id=cid,
            name="Test",
            created_at=now,
            updated_at=now,
            nodes=CanvasNodesResponse(),
            edges=[],
        )
        assert resp.id == cid
        assert resp.name == "Test"
        assert resp.created_at == now


class TestCreateCanvasRequest:
    def test_default(self):
        req = CreateCanvasRequest()
        assert req.name == "Untitled Canvas"

    def test_custom_name(self):
        req = CreateCanvasRequest(name="Custom")
        assert req.name == "Custom"
