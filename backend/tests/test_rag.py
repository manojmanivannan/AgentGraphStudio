import asyncio
import re
import uuid

import pytest
from sqlalchemy import select

from canvas_server.models.api import AgentDocumentInput, AgentNodeInput
from canvas_server.models.canvas import AgentDocument, AgentDocumentChunk
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.runner.rag_helper import RAGIndexManager, chunk_text, run_rag_search


def test_chunk_embedding_column_is_not_dimension_pinned():
    """A pinned pgvector width rejects binds once the provider dimension changes."""
    column_type = AgentDocumentChunk.__table__.c.embedding.type
    assert column_type.dimensions is None


def test_chunk_text():
    text = "Paragraph 1. Paragraph 2 is short. Paragraph 3 is very long and has lots of words."

    # Large chunk size -> should preserve sentence grouping
    chunks = chunk_text(text, 1000)
    assert len(chunks) == 1
    assert "Paragraph 1." in chunks[0]
    assert "Paragraph 3 is very long" in chunks[0]

    # Small chunk size -> should split at sentence boundaries
    chunks_small = chunk_text(text, 5)
    assert len(chunks_small) >= 2
    assert chunks_small[0].endswith("Paragraph 1.")
    assert any("Paragraph 2 is short." in c for c in chunks_small)


def test_chunk_text_preserves_sentence_boundaries():
    text = "Sentence one. Sentence two. Sentence three."
    chunks = chunk_text(text, 3)
    assert chunks == ["Sentence one.", "Sentence two.", "Sentence three."]


def test_chunk_text_splits_long_sentence_by_tokens():
    sentence = "word " * 20
    chunks = chunk_text(sentence.strip(), 5)
    assert len(chunks) == 4
    assert all(len(re.findall(r"\w+", chunk)) <= 5 for chunk in chunks)


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


@pytest.mark.asyncio
async def test_rag_indexing_timeout_fallback(monkeypatch, test_session, blank_canvas):
    from canvas_server.runner import rag_helper

    repo = CanvasRepo(test_session)
    agent_id = uuid.uuid4()
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

    doc = AgentDocument(
        id=uuid.uuid4(),
        canvas_id=blank_canvas.id,
        agent_node_id=agent_id,
        name="test_doc.txt",
        content="Timeout embedding fallback content.",
    )
    test_session.add(doc)
    await test_session.commit()
    test_session.expire_all()

    monkeypatch.setattr(
        rag_helper.asyncio,
        "wait_for",
        lambda coro, timeout: (_ for _ in ()).throw(TimeoutError()),
    )

    await RAGIndexManager.trigger_reindex(agent_id)

    chunks = []
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

    assert len(chunks) == 1
    assert "Timeout embedding fallback" in chunks[0].content


@pytest.mark.asyncio
async def test_rag_query_timeout_fallback(monkeypatch, test_session, blank_canvas):
    from canvas_server.runner import rag_helper

    repo = CanvasRepo(test_session)
    agent_id = uuid.uuid4()
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

    doc = AgentDocument(
        id=uuid.uuid4(),
        canvas_id=blank_canvas.id,
        agent_node_id=agent_id,
        name="test_doc.txt",
        content="Antigravity fallback query document.",
    )
    test_session.add(doc)
    await test_session.commit()
    test_session.expire_all()

    await RAGIndexManager.trigger_reindex(agent_id)

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

    assert chunks, "Expected chunks to exist before query fallback"

    monkeypatch.setattr(
        rag_helper.asyncio,
        "wait_for",
        lambda coro, timeout: (_ for _ in ()).throw(TimeoutError()),
    )

    from canvas_server.exceptions import RAGEmbeddingError
    with pytest.raises(RAGEmbeddingError) as exc_info:
        await run_rag_search(agent_id, "Antigravity", session=test_session)
    assert "timed out" in str(exc_info.value)


def test_pgvector_query_operator_compile():
    import uuid

    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import dialect as pg_dialect

    stmt = (
        select(AgentDocumentChunk)
        .where(AgentDocumentChunk.agent_node_id == uuid.uuid4())
        .order_by(AgentDocumentChunk.embedding.op("<=>")([0.1, 0.2, 0.3]))
        .limit(1)
    )
    compiled = str(stmt.compile(dialect=pg_dialect()))
    assert "<=>" in compiled


@pytest.mark.asyncio
async def test_rag_api_endpoints(authed_client, owned_canvas, test_session):
    canvas_id = owned_canvas.id
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
    res = await authed_client.put(f"/api/canvases/{canvas_id}", json=canvas_save_req)
    assert res.status_code == 200

    # List documents (should be empty initially)
    res = await authed_client.get(
        f"/api/canvases/{canvas_id}/agents/{agent_id}/documents"
    )
    assert res.status_code == 200
    assert len(res.json()) == 0

    # Upload document
    file_content = (
        b"This is a sample document for testing RAG chunk persistent storage."
    )
    res = await authed_client.post(
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
    res = await authed_client.delete(
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

    # Now change chunk size to 3 via save_nodes_and_edges, which triggers re-indexing
    updated_agents = [
        AgentNodeInput(
            id=agent_id,
            name="RAGAgent",
            role="Summary Assistant",
            instructions="Summary instructions: {{ rag_document }}",
            agent_type="worker",
            model_name="ollama:llama3.1",
            enable_rag=True,
            rag_chunk_size=3,
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


@pytest.mark.asyncio
async def test_create_full_indexes_rag_documents(test_session, test_user):
    repo = CanvasRepo(test_session)
    agent_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    agents = [
        AgentNodeInput(
            id=agent_id,
            name="RAGAgent",
            role="Worker",
            instructions="Context: {{ rag_document }}",
            agent_type="worker",
            model_name="ollama:llama3.1",
            enable_rag=True,
            rag_chunk_size=1000,
        )
    ]
    documents = [
        AgentDocumentInput(
            id=doc_id,
            agent_node_id=agent_id,
            name="imported_notes.txt",
            content="Imported document knowledge base about Antigravity system.",
        )
    ]

    canvas = await repo.create_full(
        name="Imported RAG Canvas",
        agents=agents,
        tools=[],
        edges=[],
        documents=documents,
        owner_id=test_user.id,
    )

    imported_agent = canvas.agent_nodes[0]

    # Verify that run_rag_search finds passages from the imported document
    passages = await run_rag_search(
        imported_agent.id, "Antigravity system", session=test_session
    )
    assert "Imported document knowledge base" in passages


@pytest.mark.asyncio
async def test_rag_search_on_demand_indexing_when_unindexed(test_session, blank_canvas):
    repo = CanvasRepo(test_session)
    agent_id = uuid.uuid4()

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

    # Insert document directly without triggering background indexing
    doc = AgentDocument(
        id=uuid.uuid4(),
        canvas_id=blank_canvas.id,
        agent_node_id=agent_id,
        name="direct_doc.txt",
        content="Direct document content on artificial intelligence.",
    )
    test_session.add(doc)
    await test_session.commit()
    test_session.expire_all()

    # Search should trigger on-demand indexing and return retrieved content
    passages = await run_rag_search(
        agent_id, "artificial intelligence", session=test_session
    )
    assert "Direct document content on artificial intelligence" in passages


@pytest.mark.asyncio
async def test_import_example_rag_zip_retrieves_context(authed_client, test_session):
    from pathlib import Path
    zip_path = Path(__file__).resolve().parent.parent.parent / "examples" / "team_math_weather_with_plot_with_rag.zip"
    if not zip_path.exists():
        pytest.skip("Example zip file not found")

    with open(zip_path, "rb") as f:
        zip_bytes = f.read()

    res = await authed_client.post(
        "/api/canvases/import-zip",
        files={"file": ("team_math_weather_with_plot_with_rag.zip", zip_bytes, "application/zip")},
    )
    assert res.status_code == 200
    canvas_data = res.json()
    weather_agent = next(a for a in canvas_data["nodes"]["agents"] if a["name"] == "WeatherAgent")
    weather_agent_id = uuid.UUID(weather_agent["id"])

    # Search RAG for WeatherAgent
    passages = await run_rag_search(weather_agent_id, "weather story", session=test_session)
    assert len(passages) > 0
    assert "Lorem ipsum" in passages
