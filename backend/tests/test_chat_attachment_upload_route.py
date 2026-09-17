import uuid
from collections.abc import Sequence

import pytest
from sqlalchemy import select

from canvas_server.config import settings
from canvas_server.models.canvas import AttachmentInstance


async def _create_canvas(authed_client, name: str = "Upload Canvas") -> str:
    response = await authed_client.post("/api/canvases", json={"name": name})
    assert response.status_code == 200
    return response.json()["id"]


def _agent_payload(
    agent_id: str,
    *,
    name: str,
    is_entry_point: bool = False,
) -> dict:
    return {
        "id": agent_id,
        "name": name,
        "role": "",
        "instructions": "",
        "model_name": "ollama:llama3.1",
        "agent_type": "worker",
        "enable_plotting": False,
        "enable_coding": False,
        "enable_network": False,
        "enable_hitl": False,
        "enable_memory": False,
        "enable_conversation_history": False,
        "enable_rag": False,
        "rag_chunk_size": 1000,
        "rag_top_k": 5,
        "is_entry_point": is_entry_point,
        "position_x": 0,
        "position_y": 0,
    }


def _attachment_payload(attachment_id: str, *, name: str, file_type: str) -> dict:
    return {
        "id": attachment_id,
        "name": name,
        "file_type": file_type,
        "description": "",
        "position_x": 0,
        "position_y": 0,
    }


def _consume_edge(attachment_id: str, agent_id: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "source_node_id": attachment_id,
        "target_node_id": agent_id,
        "edge_type": "consumes",
    }


async def _save_canvas(
    authed_client,
    canvas_id: str,
    *,
    agents: Sequence[dict],
    attachments: Sequence[dict],
    edges: Sequence[dict],
    name: str = "Upload Canvas",
) -> dict:
    response = await authed_client.put(
        f"/api/canvases/{canvas_id}",
        json={
            "name": name,
            "nodes": {
                "agents": list(agents),
                "tools": [],
                "attachments": list(attachments),
            },
            "edges": list(edges),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_conversation(authed_client, canvas_id: str, name: str = "Upload Conversation") -> str:
    response = await authed_client.post(
        f"/api/canvases/{canvas_id}/conversations",
        json={"name": name},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _conversation_attachments(test_session, conversation_id: str) -> list[AttachmentInstance]:
    test_session.expire_all()
    result = await test_session.execute(
        select(AttachmentInstance).where(
            AttachmentInstance.conversation_id == uuid.UUID(conversation_id)
        )
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_upload_matches_entry_agent_declared_input_node(authed_client, test_session):
    canvas_id = await _create_canvas(authed_client)
    entry_agent_id = str(uuid.uuid4())
    attachment_node_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[_agent_payload(entry_agent_id, name="Entry", is_entry_point=True)],
        attachments=[_attachment_payload(attachment_node_id, name="Csv Input", file_type="csv")],
        edges=[_consume_edge(attachment_node_id, entry_agent_id)],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    response = await authed_client.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["filename"] == "data.csv"
    assert result["success"] is True
    assert result["attachment_id"]
    assert result["node_id"] == attachment_node_id
    assert result["file_type"] == "csv"
    assert result["error"] is None

    download = await authed_client.get(f"/api/attachments/{result['attachment_id']}")
    assert download.status_code == 200
    assert download.content == b"a,b\n1,2\n"

    attachments = await _conversation_attachments(test_session, conversation_id)
    assert len(attachments) == 1
    assert str(attachments[0].attachment_node_id) == attachment_node_id
    assert attachments[0].file_type == "csv"
    assert attachments[0].source == "chat_upload"
    assert attachments[0].format == "csv"


@pytest.mark.asyncio
async def test_upload_rejects_file_type_without_declared_input_node(authed_client, test_session):
    canvas_id = await _create_canvas(authed_client)
    entry_agent_id = str(uuid.uuid4())
    attachment_node_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[_agent_payload(entry_agent_id, name="Entry", is_entry_point=True)],
        attachments=[_attachment_payload(attachment_node_id, name="Json Input", file_type="json")],
        edges=[_consume_edge(attachment_node_id, entry_agent_id)],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    response = await authed_client.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["success"] is False
    assert result["attachment_id"] is None
    assert result["node_id"] is None
    assert result["error"]

    attachments = await _conversation_attachments(test_session, conversation_id)
    assert attachments == []


@pytest.mark.asyncio
async def test_upload_matches_multiple_files_to_distinct_declared_nodes(authed_client, test_session):
    canvas_id = await _create_canvas(authed_client)
    entry_agent_id = str(uuid.uuid4())
    csv_node_id = str(uuid.uuid4())
    pdf_node_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[_agent_payload(entry_agent_id, name="Entry", is_entry_point=True)],
        attachments=[
            _attachment_payload(csv_node_id, name="Csv Input", file_type="csv"),
            _attachment_payload(pdf_node_id, name="Pdf Input", file_type="pdf"),
        ],
        edges=[
            _consume_edge(csv_node_id, entry_agent_id),
            _consume_edge(pdf_node_id, entry_agent_id),
        ],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    response = await authed_client.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        files=[
            ("files", ("data.csv", b"a,b\n1,2\n", "text/csv")),
            ("files", ("guide.pdf", b"%PDF-1.4", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [result["success"] for result in results] == [True, True]
    assert {results[0]["node_id"], results[1]["node_id"]} == {csv_node_id, pdf_node_id}

    attachments = await _conversation_attachments(test_session, conversation_id)
    assert len(attachments) == 2
    assert {str(attachment.attachment_node_id) for attachment in attachments} == {
        csv_node_id,
        pdf_node_id,
    }


@pytest.mark.asyncio
async def test_upload_rejects_ambiguous_declared_input_type(authed_client, test_session):
    canvas_id = await _create_canvas(authed_client)
    entry_agent_id = str(uuid.uuid4())
    first_attachment_id = str(uuid.uuid4())
    second_attachment_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[_agent_payload(entry_agent_id, name="Entry", is_entry_point=True)],
        attachments=[
            _attachment_payload(first_attachment_id, name="Csv Input A", file_type="csv"),
            _attachment_payload(second_attachment_id, name="Csv Input B", file_type="csv"),
        ],
        edges=[
            _consume_edge(first_attachment_id, entry_agent_id),
            _consume_edge(second_attachment_id, entry_agent_id),
        ],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    response = await authed_client.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["success"] is False
    assert "Ambiguous" in result["error"]

    attachments = await _conversation_attachments(test_session, conversation_id)
    assert attachments == []


@pytest.mark.asyncio
async def test_upload_uses_explicit_agent_id_instead_of_entry_agent(authed_client, test_session):
    canvas_id = await _create_canvas(authed_client)
    entry_agent_id = str(uuid.uuid4())
    hitl_agent_id = str(uuid.uuid4())
    entry_attachment_id = str(uuid.uuid4())
    hitl_attachment_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[
            _agent_payload(entry_agent_id, name="Entry", is_entry_point=True),
            _agent_payload(hitl_agent_id, name="Reviewer"),
        ],
        attachments=[
            _attachment_payload(entry_attachment_id, name="Entry Json", file_type="json"),
            _attachment_payload(hitl_attachment_id, name="Hitl Csv", file_type="csv"),
        ],
        edges=[
            _consume_edge(entry_attachment_id, entry_agent_id),
            _consume_edge(hitl_attachment_id, hitl_agent_id),
        ],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    response = await authed_client.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        data={"agent_id": hitl_agent_id},
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["success"] is True
    assert result["node_id"] == hitl_attachment_id
    assert result["file_type"] == "csv"

    attachments = await _conversation_attachments(test_session, conversation_id)
    assert len(attachments) == 1
    assert str(attachments[0].attachment_node_id) == hitl_attachment_id


@pytest.mark.asyncio
async def test_upload_rejects_agent_id_not_present_on_canvas(authed_client):
    canvas_id = await _create_canvas(authed_client)
    entry_agent_id = str(uuid.uuid4())
    attachment_node_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[_agent_payload(entry_agent_id, name="Entry", is_entry_point=True)],
        attachments=[_attachment_payload(attachment_node_id, name="Csv Input", file_type="csv")],
        edges=[_consume_edge(attachment_node_id, entry_agent_id)],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    response = await authed_client.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        data={"agent_id": str(uuid.uuid4())},
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"


@pytest.mark.asyncio
async def test_upload_requires_entry_agent_when_agent_id_omitted(authed_client):
    canvas_id = await _create_canvas(authed_client)
    agent_id = str(uuid.uuid4())
    attachment_node_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[_agent_payload(agent_id, name="Worker", is_entry_point=False)],
        attachments=[_attachment_payload(attachment_node_id, name="Csv Input", file_type="csv")],
        edges=[_consume_edge(attachment_node_id, agent_id)],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    response = await authed_client.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Canvas has no entry agent configured"


@pytest.mark.asyncio
async def test_upload_hides_foreign_conversation_existence(make_authed_client):
    owner = await make_authed_client()
    stranger = await make_authed_client()

    canvas_id = await _create_canvas(owner)
    entry_agent_id = str(uuid.uuid4())
    attachment_node_id = str(uuid.uuid4())
    await _save_canvas(
        owner,
        canvas_id,
        agents=[_agent_payload(entry_agent_id, name="Entry", is_entry_point=True)],
        attachments=[_attachment_payload(attachment_node_id, name="Csv Input", file_type="csv")],
        edges=[_consume_edge(attachment_node_id, entry_agent_id)],
    )
    conversation_id = await _create_conversation(owner, canvas_id)

    response = await stranger.post(
        f"/api/canvases/conversations/{conversation_id}/attachments",
        files=[("files", ("data.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


@pytest.mark.asyncio
async def test_upload_keeps_other_files_succeeding_when_one_is_oversized(
    authed_client, test_session
):
    canvas_id = await _create_canvas(authed_client)
    entry_agent_id = str(uuid.uuid4())
    csv_node_id = str(uuid.uuid4())
    pdf_node_id = str(uuid.uuid4())
    await _save_canvas(
        authed_client,
        canvas_id,
        agents=[_agent_payload(entry_agent_id, name="Entry", is_entry_point=True)],
        attachments=[
            _attachment_payload(csv_node_id, name="Csv Input", file_type="csv"),
            _attachment_payload(pdf_node_id, name="Pdf Input", file_type="pdf"),
        ],
        edges=[
            _consume_edge(csv_node_id, entry_agent_id),
            _consume_edge(pdf_node_id, entry_agent_id),
        ],
    )
    conversation_id = await _create_conversation(authed_client, canvas_id)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(settings, "max_attachment_size_bytes", 10)
        response = await authed_client.post(
            f"/api/canvases/conversations/{conversation_id}/attachments",
            files=[
                ("files", ("data.csv", b"a,b\n1,2\n", "text/csv")),
                ("files", ("guide.pdf", b"%PDF-1.4 and more bytes", "application/pdf")),
            ],
        )

    assert response.status_code == 200
    first, second = response.json()["results"]
    assert first["success"] is True
    assert second["success"] is False
    assert "exceeds the 10 byte limit" in second["error"]

    attachments = await _conversation_attachments(test_session, conversation_id)
    assert len(attachments) == 1
    assert attachments[0].file_type == "csv"
