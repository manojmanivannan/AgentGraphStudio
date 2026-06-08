import asyncio
import uuid

import pytest
from sqlalchemy import select

from canvas_server.models.api import AgentNodeInput
from canvas_server.models.canvas import AgentDocument, AgentDocumentChunk
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.runner.rag_helper import RAGIndexManager, chunk_text, run_rag_search


def test_chunk_text():
    text = (
        "Paragraph 1\n\nParagraph 2\n\nParagraph 3 is very long and has lots of words."
    )

    # Large chunk size -> should group paragraphs
    chunks = chunk_text(text, 1000)
    assert len(chunks) == 1
    assert "Paragraph 1" in chunks[0]
    assert "Paragraph 3" in chunks[0]

    # Small chunk size -> should split
    chunks_small = chunk_text(text, 15)
    assert len(chunks_small) >= 3
    assert any("Paragraph 1" in c for c in chunks_small)


@pytest.mark.asyncio
async def test_run_rag_search_sqlite_similarity(test_session, blank_canvas):
    repo = CanvasRepo(test_session)
    agent_id = uuid.uuid4()

    # Create RAG enabled agent using save_nodes_and_edges to preserve exact IDs
    await repo.save_nodes_and_edges(
        blank_canvas.id,
        "RAG Canvas",
        agents=[
            AgentNodeInput(
                id=agent_id,
                name="RAGAgent",
                role="Assistant",
                instructions="Context: {{ rag_document }}",
                agent_type="worker",
                model_name="ollama:llama3.1",
                enable_rag=True,
                rag_chunk_size=1000,
            )
        ],
        tools=[],
        edges=[],
    )

    # Store a document
    doc = AgentDocument(
        id=uuid.uuid4(),
        canvas_id=blank_canvas.id,
        agent_node_id=agent_id,
        name="test_doc.txt",
        content="Secret Antigravity Research Document contents.",
    )
    test_session.add(doc)
    await test_session.commit()
    test_session.expire_all()

    # Manually trigger indexing and wait for it to complete
    await RAGIndexManager.trigger_reindex(agent_id)

    # Wait up to 2 seconds for indexing task to complete
    for _ in range(20):
        test_session.expire_all()
        res = await test_session.execute(
            select(AgentDocumentChunk).where(
                AgentDocumentChunk.agent_node_id == agent_id
            )
        )
        chunks = res.scalars().all()
        if chunks:
            break
        await asyncio.sleep(0.1)

    assert len(chunks) > 0
    assert "Secret Antigravity" in chunks[0].content

    # Query similarity search (on SQLite fallback)
    passages = await run_rag_search(agent_id, "Antigravity", session=test_session)
    assert "Secret Antigravity Research" in passages


def test_pgvector_query_operator_compile():
    from sqlalchemy.dialects.postgresql import dialect as pg_dialect
    from sqlalchemy import select
    import uuid

    stmt = (
        select(AgentDocumentChunk)
        .where(AgentDocumentChunk.agent_node_id == uuid.uuid4())
        .order_by(AgentDocumentChunk.embedding.op("<=>")([0.1, 0.2, 0.3]))
        .limit(1)
    )
    compiled = str(stmt.compile(dialect=pg_dialect()))
    assert "<=>" in compiled


@pytest.mark.asyncio
async def test_rag_api_endpoints(test_client, blank_canvas, test_session):
    canvas_id = blank_canvas.id
    agent_id = uuid.uuid4()

    # Create agent
    canvas_save_req = {
        "name": "RAG Canvas",
        "nodes": {
            "agents": [
                {
                    "id": str(agent_id),
                    "name": "RAG Agent",
                    "role": "Assistant",
                    "instructions": "Context: {{ rag_document }}",
                    "model_name": "ollama:llama3.1",
                    "agent_type": "worker",
                    "enable_memory": False,
                    "enable_conversation_history": False,
                    "enable_rag": True,
                    "rag_chunk_size": 1000,
                    "position_x": 0,
                    "position_y": 0,
                }
            ],
            "tools": [],
        },
        "edges": [],
    }
    res = await test_client.put(f"/api/canvases/{canvas_id}", json=canvas_save_req)
    assert res.status_code == 200

    # List documents (should be empty initially)
    res = await test_client.get(
        f"/api/canvases/{canvas_id}/agents/{agent_id}/documents"
    )
    assert res.status_code == 200
    assert len(res.json()) == 0

    # Upload document
    file_content = (
        b"This is a sample document for testing RAG chunk persistent storage."
    )
    res = await test_client.post(
        f"/api/canvases/{canvas_id}/agents/{agent_id}/documents",
        files={"file": ("test_doc.txt", file_content, "text/plain")},
    )
    assert res.status_code == 200
    doc_data = res.json()
    assert doc_data["name"] == "test_doc.txt"
    doc_id = doc_data["id"]

    # Wait up to 2 seconds for indexing task to complete
    for _ in range(20):
        # We query the DB via session to verify chunks were created
        test_session.expire_all()
        chunks_res = await test_session.execute(
            select(AgentDocumentChunk).where(
                AgentDocumentChunk.agent_node_id == agent_id
            )
        )
        chunks = chunks_res.scalars().all()
        if chunks:
            break
        await asyncio.sleep(0.1)

    assert len(chunks) == 1
    assert "testing RAG chunk" in chunks[0].content

    # Delete document
    res = await test_client.delete(
        f"/api/canvases/{canvas_id}/agents/{agent_id}/documents/{doc_id}"
    )
    assert res.status_code == 204

    # Wait to ensure delete background indexing completes
    for _ in range(20):
        test_session.expire_all()
        chunks_res = await test_session.execute(
            select(AgentDocumentChunk).where(
                AgentDocumentChunk.agent_node_id == agent_id
            )
        )
        chunks = chunks_res.scalars().all()
        if not chunks:
            break
        await asyncio.sleep(0.1)

    assert len(chunks) == 0


@pytest.mark.asyncio
async def test_rag_chunk_size_invalidation(test_session, blank_canvas):
    repo = CanvasRepo(test_session)
    agent_id = uuid.uuid4()

    # Create canvas with a RAG enabled worker agent (chunk size 1000)
    await repo.save_nodes_and_edges(
        blank_canvas.id,
        "RAG Canvas",
        agents=[
            AgentNodeInput(
                id=agent_id,
                name="RAGAgent",
                role="Summary Assistant",
                instructions="Summary instructions: {{ rag_document }}",
                agent_type="worker",
                model_name="ollama:llama3.1",
                enable_rag=True,
                rag_chunk_size=1000,
            )
        ],
        tools=[],
        edges=[],
    )

    # Add document
    doc = AgentDocument(
        id=uuid.uuid4(),
        canvas_id=blank_canvas.id,
        agent_node_id=agent_id,
        name="test.txt",
        content="First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here.",
    )
    test_session.add(doc)
    await test_session.commit()

    # Trigger initial indexing
    await RAGIndexManager.trigger_reindex(agent_id)
    for _ in range(20):
        test_session.expire_all()
        chunks_res = await test_session.execute(
            select(AgentDocumentChunk).where(
                AgentDocumentChunk.agent_node_id == agent_id
            )
        )
        chunks = chunks_res.scalars().all()
        if chunks:
            break
        await asyncio.sleep(0.1)

    # With chunk size 1000, all three paragraphs fit in a single chunk
    assert len(chunks) == 1

    # Now change chunk size to 30 via save_nodes_and_edges, which triggers re-indexing
    updated_agents = [
        AgentNodeInput(
            id=agent_id,
            name="RAGAgent",
            role="Summary Assistant",
            instructions="Summary instructions: {{ rag_document }}",
            agent_type="worker",
            model_name="ollama:llama3.1",
            enable_rag=True,
            rag_chunk_size=30,
        )
    ]
    await repo.save_nodes_and_edges(
        canvas_id=blank_canvas.id,
        name="RAG Canvas",
        agents=updated_agents,
        tools=[],
        edges=[],
    )

    # Wait for the reindexing task to complete
    await asyncio.sleep(0.5)
    for _ in range(20):
        test_session.expire_all()
        chunks_res = await test_session.execute(
            select(AgentDocumentChunk).where(
                AgentDocumentChunk.agent_node_id == agent_id
            )
        )
        chunks = chunks_res.scalars().all()
        # Chunks should be split into 3 separate ones now
        if len(chunks) == 3:
            break
        await asyncio.sleep(0.1)

    assert len(chunks) == 3
