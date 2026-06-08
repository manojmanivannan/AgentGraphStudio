import uuid

import pytest

from canvas_server.models.api import AgentNodeInput
from canvas_server.models.canvas import AgentDocument
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.runner import CanvasRunner
from canvas_server.runner.rag_helper import chunk_text, run_rag_search


def test_chunk_text():
    text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3 is very long and has lots of words."

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
async def test_run_rag_search_fallback():
    # Verify fallback when embedding fails
    docs = [
        AgentDocument(content="Context chunk 1\n\nContext chunk 2"),
        AgentDocument(content="Context chunk 3")
    ]
    passages = await run_rag_search(docs, "query", chunk_size=100)
    # Fallback should return concatenated chunks
    assert "Context chunk 1" in passages
    assert "Context chunk 3" in passages


@pytest.mark.asyncio
async def test_rag_api_endpoints(test_client, blank_canvas):
    canvas_id = blank_canvas.id

    # Create agent
    agent_id = uuid.uuid4()
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
                    "position_y": 0
                }
            ],
            "tools": []
        },
        "edges": []
    }
    res = await test_client.put(f"/api/canvases/{canvas_id}", json=canvas_save_req)
    assert res.status_code == 200

    # List documents (should be empty initially)
    res = await test_client.get(f"/api/canvases/{canvas_id}/agents/{agent_id}/documents")
    assert res.status_code == 200
    assert len(res.json()) == 0

    # Upload document
    file_content = b"This is a sample document for testing RAG."
    res = await test_client.post(
        f"/api/canvases/{canvas_id}/agents/{agent_id}/documents",
        files={"file": ("test_doc.txt", file_content, "text/plain")}
    )
    assert res.status_code == 200
    doc_data = res.json()
    assert doc_data["name"] == "test_doc.txt"
    doc_id = doc_data["id"]

    # List documents again
    res = await test_client.get(f"/api/canvases/{canvas_id}/agents/{agent_id}/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 1
    assert docs[0]["name"] == "test_doc.txt"

    # Delete document
    res = await test_client.delete(f"/api/canvases/{canvas_id}/agents/{agent_id}/documents/{doc_id}")
    assert res.status_code == 204

    # Verify deleted
    res = await test_client.get(f"/api/canvases/{canvas_id}/agents/{agent_id}/documents")
    assert len(res.json()) == 0


@pytest.mark.asyncio
async def test_runner_rag_replacement(test_session, blank_canvas):
    repo = CanvasRepo(test_session)
    agent_id = uuid.uuid4()

    # Create canvas with a RAG enabled worker agent
    agents = [
        AgentNodeInput(
            id=agent_id,
            name="RAGAgent",
            role="Summary Assistant",
            instructions="Summary instructions: {{ rag_document }}",
            agent_type="worker",
            model_name="ollama:llama3.1",
            enable_rag=True,
            rag_chunk_size=1000
        )
    ]
    canvas = await repo.create_full(
        name="RAG Workflow",
        agents=agents,
        tools=[],
        edges=[]
    )

    # Add document to DB directly using the actual database node ID
    db_agent_node = canvas.agent_nodes[0]
    db_agent_id = db_agent_node.id

    canvas_db_id = canvas.id
    doc = AgentDocument(
        id=uuid.uuid4(),
        canvas_id=canvas_db_id,
        agent_node_id=db_agent_id,
        name="test.txt",
        content="Secret Antigravity Research Document contents."
    )
    test_session.add(doc)
    await test_session.commit()
    test_session.expire_all()

    # Refresh canvas from database to load relationships
    canvas = await repo.get_or_404(canvas_db_id)

    # Instantiate CanvasRunner
    runner = CanvasRunner(canvas)

    # Verify that setup builds agent signature correctly (cleaning/ignoring the placeholder initially)
    await runner.setup()
    assert runner.agents[db_agent_id] is not None

    # Since we can't easily run real LLM queries without LLM backend,
    # let's verify that we can create the Dynamic RAG agent and it replaces instructions:
    passages = await run_rag_search(canvas.agent_nodes[0].documents, "test", 1000)
    assert "Secret Antigravity Research" in passages

    # Build dynamic agent and check instructions
    rag_agent = await runner._agent_factory.build_worker_with_rag_prompt(canvas.agent_nodes[0], passages)
    assert "Secret Antigravity Research" in rag_agent.react.signature.instructions
    assert "{{ rag_document }}" not in rag_agent.react.signature.instructions
