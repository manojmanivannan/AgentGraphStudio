import uuid
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from canvas_server.models.api import (
    AgentNodeInput,
    AgentNodeResponse,
    AttachmentNodeInput,
    AttachmentNodeResponse,
    CanvasNodesInput,
    CanvasNodesResponse,
    CanvasResponse,
    CanvasSaveRequest,
    CreateCanvasRequest,
    EdgeInput,
    ToolNodeInput,
)


def test_attachment_example_canvas_is_importable():
    example_path = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "expense_report_attachment_pipeline.json"
    )

    example = json.loads(example_path.read_text())
    canvas = CanvasSaveRequest.model_validate(example)

    assert len(canvas.nodes.attachments) == 2
    assert {edge.edge_type for edge in canvas.edges} == {"consumes", "produces"}


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

    def test_router_cannot_enable_plotting(self):
        with pytest.raises(ValidationError) as exc_info:
            AgentNodeInput(id=uuid.uuid4(), agent_type="router", enable_plotting=True)
        assert "Plotting is only supported for worker agents, not Router agents." in str(exc_info.value)

    def test_worker_can_enable_plotting(self):
        agent = AgentNodeInput(id=uuid.uuid4(), agent_type="worker", enable_plotting=True)
        assert agent.enable_plotting is True

    def test_router_cannot_enable_coding(self):
        with pytest.raises(ValidationError) as exc_info:
            AgentNodeInput(id=uuid.uuid4(), agent_type="router", enable_coding=True)
        assert "Coding is only supported for worker agents, not Router agents." in str(exc_info.value)

    def test_worker_can_enable_coding(self):
        agent = AgentNodeInput(id=uuid.uuid4(), agent_type="worker", enable_coding=True)
        assert agent.enable_coding is True

    def test_enable_coding_defaults_false(self):
        agent = AgentNodeInput(id=uuid.uuid4())
        assert agent.enable_coding is False

    def test_enable_network_defaults_false(self):
        agent = AgentNodeInput(id=uuid.uuid4())
        assert agent.enable_network is False

    def test_worker_can_enable_network(self):
        agent = AgentNodeInput(id=uuid.uuid4(), agent_type="worker", enable_network=True)
        assert agent.enable_network is True

    def test_router_cannot_enable_network(self):
        with pytest.raises(ValidationError) as exc_info:
            AgentNodeInput(id=uuid.uuid4(), agent_type="router", enable_network=True)
        assert "Network is only supported for worker agents" in str(exc_info.value)



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
            enable_plotting=False,
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


class TestAttachmentNodeInput:
    def test_minimal_creation(self):
        att = AttachmentNodeInput(id=uuid.uuid4())
        assert att.name == "Attachment"
        assert att.file_type == "text"
        assert att.description == ""
        assert att.position_x == 0
        assert att.position_y == 0

    def test_id_required(self):
        with pytest.raises(ValidationError):
            AttachmentNodeInput()

    @pytest.mark.parametrize(
        "file_type", ["csv", "json", "text", "python", "yaml", "image", "pdf", "binary"]
    )
    def test_curated_file_types_accepted(self, file_type):
        att = AttachmentNodeInput(id=uuid.uuid4(), file_type=file_type)
        assert att.file_type == file_type

    def test_freeform_file_type_accepted(self):
        att = AttachmentNodeInput(id=uuid.uuid4(), file_type="parquet")
        assert att.file_type == "parquet"

    def test_file_type_trimmed(self):
        att = AttachmentNodeInput(id=uuid.uuid4(), file_type="  csv  ")
        assert att.file_type == "csv"

    def test_empty_file_type_rejected(self):
        with pytest.raises(ValidationError):
            AttachmentNodeInput(id=uuid.uuid4(), file_type="")

    def test_blank_file_type_rejected(self):
        with pytest.raises(ValidationError):
            AttachmentNodeInput(id=uuid.uuid4(), file_type="   ")

    def test_description_optional(self):
        att = AttachmentNodeInput(id=uuid.uuid4(), description="Sales data")
        assert att.description == "Sales data"


class TestAttachmentNodeResponse:
    def test_creation(self):
        aid = uuid.uuid4()
        cid = uuid.uuid4()
        resp = AttachmentNodeResponse(
            id=aid, canvas_id=cid, name="Data", file_type="csv", description="d"
        )
        assert resp.id == aid
        assert resp.canvas_id == cid
        assert resp.file_type == "csv"


class TestCanvasNodesInputAttachments:
    def test_defaults(self):
        nodes = CanvasNodesInput()
        assert nodes.attachments == []

    def test_with_attachments(self):
        aid = uuid.uuid4()
        nodes = CanvasNodesInput(attachments=[AttachmentNodeInput(id=aid, name="A1")])
        assert len(nodes.attachments) == 1
        assert nodes.attachments[0].id == aid


class TestAttachmentEdgeWiringValidation:
    def _make_ids(self):
        return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def test_agent_to_attachment_edge_allowed(self):
        agent_id, _, attachment_id = self._make_ids()
        req = CanvasSaveRequest(
            nodes=CanvasNodesInput(
                agents=[AgentNodeInput(id=agent_id)],
                attachments=[AttachmentNodeInput(id=attachment_id)],
            ),
            edges=[
                EdgeInput(
                    id=uuid.uuid4(),
                    source_node_id=agent_id,
                    target_node_id=attachment_id,
                    edge_type="produces",
                )
            ],
        )
        assert len(req.edges) == 1

    def test_attachment_to_agent_edge_allowed(self):
        agent_id, _, attachment_id = self._make_ids()
        req = CanvasSaveRequest(
            nodes=CanvasNodesInput(
                agents=[AgentNodeInput(id=agent_id)],
                attachments=[AttachmentNodeInput(id=attachment_id)],
            ),
            edges=[
                EdgeInput(
                    id=uuid.uuid4(),
                    source_node_id=attachment_id,
                    target_node_id=agent_id,
                    edge_type="consumes",
                )
            ],
        )
        assert len(req.edges) == 1

    def test_attachment_to_attachment_edge_rejected(self):
        _, _, attachment_id = self._make_ids()
        other_attachment_id = uuid.uuid4()
        with pytest.raises(ValidationError) as exc_info:
            CanvasSaveRequest(
                nodes=CanvasNodesInput(
                    attachments=[
                        AttachmentNodeInput(id=attachment_id),
                        AttachmentNodeInput(id=other_attachment_id),
                    ],
                ),
                edges=[
                    EdgeInput(
                        id=uuid.uuid4(),
                        source_node_id=attachment_id,
                        target_node_id=other_attachment_id,
                        edge_type="produces",
                    )
                ],
            )
        assert "attachment-to-attachment" in str(exc_info.value)

    def test_attachment_to_tool_edge_rejected(self):
        _, tool_id, attachment_id = self._make_ids()
        with pytest.raises(ValidationError) as exc_info:
            CanvasSaveRequest(
                nodes=CanvasNodesInput(
                    tools=[ToolNodeInput(id=tool_id)],
                    attachments=[AttachmentNodeInput(id=attachment_id)],
                ),
                edges=[
                    EdgeInput(
                        id=uuid.uuid4(),
                        source_node_id=tool_id,
                        target_node_id=attachment_id,
                        edge_type="produces",
                    )
                ],
            )
        assert "attachment-to-tool" in str(exc_info.value)

    def test_tool_to_attachment_edge_rejected(self):
        _, tool_id, attachment_id = self._make_ids()
        with pytest.raises(ValidationError) as exc_info:
            CanvasSaveRequest(
                nodes=CanvasNodesInput(
                    tools=[ToolNodeInput(id=tool_id)],
                    attachments=[AttachmentNodeInput(id=attachment_id)],
                ),
                edges=[
                    EdgeInput(
                        id=uuid.uuid4(),
                        source_node_id=attachment_id,
                        target_node_id=tool_id,
                        edge_type="consumes",
                    )
                ],
            )
        assert "attachment-to-tool" in str(exc_info.value)

    def test_regular_agent_tool_edges_unaffected(self):
        agent_id = uuid.uuid4()
        tool_id = uuid.uuid4()
        req = CanvasSaveRequest(
            nodes=CanvasNodesInput(
                agents=[AgentNodeInput(id=agent_id)],
                tools=[ToolNodeInput(id=tool_id)],
            ),
            edges=[
                EdgeInput(
                    id=uuid.uuid4(),
                    source_node_id=agent_id,
                    target_node_id=tool_id,
                    edge_type="tool_access",
                )
            ],
        )
        assert len(req.edges) == 1

    def test_agent_to_attachment_edge_wrong_edge_type_rejected(self):
        agent_id, _, attachment_id = self._make_ids()
        with pytest.raises(ValidationError) as exc_info:
            CanvasSaveRequest(
                nodes=CanvasNodesInput(
                    agents=[AgentNodeInput(id=agent_id)],
                    attachments=[AttachmentNodeInput(id=attachment_id)],
                ),
                edges=[
                    EdgeInput(
                        id=uuid.uuid4(),
                        source_node_id=agent_id,
                        target_node_id=attachment_id,
                        edge_type="handoff",
                    )
                ],
            )
        assert "edge_type='produces'" in str(exc_info.value)

    def test_attachment_to_agent_edge_wrong_edge_type_rejected(self):
        agent_id, _, attachment_id = self._make_ids()
        with pytest.raises(ValidationError) as exc_info:
            CanvasSaveRequest(
                nodes=CanvasNodesInput(
                    agents=[AgentNodeInput(id=agent_id)],
                    attachments=[AttachmentNodeInput(id=attachment_id)],
                ),
                edges=[
                    EdgeInput(
                        id=uuid.uuid4(),
                        source_node_id=attachment_id,
                        target_node_id=agent_id,
                        edge_type="tool_access",
                    )
                ],
            )
        assert "edge_type='consumes'" in str(exc_info.value)

