import io
import json
import logging
import uuid
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.database import get_session
from canvas_server.exceptions import CanvasNotFoundError, ConversationNotFoundError
from canvas_server.models.api import (
    AgentDocumentInput,
    AgentDocumentResponse,
    CanvasImportRequest,
    CanvasListResponse,
    CanvasResponse,
    CanvasSaveRequest,
    ConversationListResponse,
    ConversationResponse,
    CreateCanvasRequest,
    CreateConversationRequest,
)
from canvas_server.models.canvas import Canvas
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.repos.conversation_repo import ConversationRepo

logger = logging.getLogger("canvas_server.routes.canvas")
canvas_router = APIRouter(prefix="/api/canvases", tags=["canvases"])


def _canvas_to_response(canvas: Canvas) -> CanvasResponse:
    from canvas_server.models.api import (
        AgentNodeResponse,
        CanvasNodesResponse,
        EdgeResponse,
        ToolNodeResponse,
    )

    return CanvasResponse(
        id=canvas.id,
        name=canvas.name,
        created_at=canvas.created_at,
        updated_at=canvas.updated_at,
        nodes=CanvasNodesResponse(
            agents=[
                AgentNodeResponse(
                    id=n.id,
                    canvas_id=n.canvas_id,
                    name=n.name,
                    role=n.role,
                    instructions=n.instructions,
                    model_name=n.model_name,
                    agent_type=n.agent_type,
                    enable_plotting=n.enable_plotting,
                    enable_memory=n.enable_memory,
                    enable_conversation_history=n.enable_conversation_history,
                    enable_rag=n.enable_rag,
                    rag_chunk_size=n.rag_chunk_size,
                    is_entry_point=n.is_entry_point,
                    position_x=n.position_x,
                    position_y=n.position_y,
                )
                for n in canvas.agent_nodes
            ],
            tools=[
                ToolNodeResponse(
                    id=n.id,
                    canvas_id=n.canvas_id,
                    name=n.name,
                    code=n.code,
                    packages=",".join(n.dependencies),
                    dependencies=n.dependencies,
                    args=n.args,
                    position_x=n.position_x,
                    position_y=n.position_y,
                )
                for n in canvas.tool_nodes
            ],
        ),
        edges=[
            EdgeResponse(
                id=e.id,
                canvas_id=e.canvas_id,
                source_node_id=e.source_node_id,
                target_node_id=e.target_node_id,
                edge_type=e.edge_type,
            )
            for e in canvas.edges
        ],
    )


@canvas_router.post("", response_model=CanvasResponse)
async def create_canvas(
    body: CreateCanvasRequest = CreateCanvasRequest(),
    session: AsyncSession = Depends(get_session),
):
    logger.info(f"Creating canvas: name={body.name}")
    repo = CanvasRepo(session)
    canvas = await repo.create(name=body.name)
    logger.info(f"Canvas created: id={canvas.id}")
    return _canvas_to_response(canvas)


@canvas_router.get("", response_model=list[CanvasListResponse])
async def list_canvases(session: AsyncSession = Depends(get_session)):
    logger.debug("Listing all canvases")
    repo = CanvasRepo(session)
    canvases = await repo.list_all()
    logger.debug(f"Found {len(canvases)} canvases")
    return [
        CanvasListResponse(
            id=c.id,
            name=c.name,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in canvases
    ]


@canvas_router.get("/{canvas_id}", response_model=CanvasResponse)
async def get_canvas(canvas_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.debug(f"Getting canvas: id={canvas_id}")
    repo = CanvasRepo(session)
    try:
        canvas = await repo.get_or_404(canvas_id)
    except CanvasNotFoundError:
        logger.warning(f"Canvas not found: id={canvas_id}")
        raise HTTPException(status_code=404, detail="Canvas not found") from None
    logger.debug(
        f"Canvas fetched: id={canvas_id}, agents={len(canvas.agent_nodes)}, "
        f"tools={len(canvas.tool_nodes)}, edges={len(canvas.edges)}"
    )
    return _canvas_to_response(canvas)


@canvas_router.put("/{canvas_id}", response_model=CanvasResponse)
async def save_canvas(
    canvas_id: uuid.UUID,
    body: CanvasSaveRequest,
    session: AsyncSession = Depends(get_session),
):
    logger.info(
        f"Saving canvas: id={canvas_id}, name={body.name}, "
        f"agents={len(body.nodes.agents)}, "
        f"tools={len(body.nodes.tools)}, edges={len(body.edges)}"
    )
    for a in body.nodes.agents:
        logger.debug(f"  agent: id={a.id}, name={a.name}, model={a.model_name}")
    for t in body.nodes.tools:
        logger.debug(f"  tool: id={t.id}, name={t.name}")
    for e in body.edges:
        logger.debug(f"  edge: id={e.id}, {e.source_node_id} -> {e.target_node_id} [{e.edge_type}]")
    repo = CanvasRepo(session)
    try:
        canvas = await repo.save_nodes_and_edges(
            canvas_id=canvas_id,
            name=body.name,
            agents=body.nodes.agents,
            tools=body.nodes.tools,
            edges=body.edges,
        )
    except CanvasNotFoundError:
        logger.warning(f"Canvas not found for save: id={canvas_id}")
        raise HTTPException(status_code=404, detail="Canvas not found") from None
    logger.info(f"Canvas saved: id={canvas_id}")
    return _canvas_to_response(canvas)


@canvas_router.delete("/{canvas_id}", status_code=204)
async def delete_canvas(canvas_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.info(f"Deleting canvas: id={canvas_id}")
    repo = CanvasRepo(session)
    deleted = await repo.delete(canvas_id)
    if not deleted:
        logger.warning(f"Canvas not found for delete: id={canvas_id}")
        raise HTTPException(status_code=404, detail="Canvas not found") from None
    logger.info(f"Canvas deleted: id={canvas_id}")


def _canvas_to_import_payload(canvas: Canvas) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for agent in canvas.agent_nodes:
        for doc in agent.documents:
            documents.append(
                {
                    "id": doc.id,
                    "agent_node_id": doc.agent_node_id,
                    "name": doc.name,
                    "created_at": doc.created_at,
                    "path": f"documents/{doc.agent_node_id}/{doc.id}.txt",
                }
            )

    return {
        "name": canvas.name,
        "nodes": {
            "agents": [
                {
                    "id": n.id,
                    "name": n.name,
                    "role": n.role,
                    "instructions": n.instructions,
                    "model_name": n.model_name,
                    "agent_type": n.agent_type,
                    "enable_plotting": n.enable_plotting,
                    "enable_memory": n.enable_memory,
                    "enable_conversation_history": n.enable_conversation_history,
                    "enable_rag": n.enable_rag,
                    "rag_chunk_size": n.rag_chunk_size,
                    "is_entry_point": n.is_entry_point,
                    "position_x": n.position_x,
                    "position_y": n.position_y,
                }
                for n in canvas.agent_nodes
            ],
            "tools": [
                {
                    "id": n.id,
                    "name": n.name,
                    "code": n.code,
                    "packages": ",".join(n.dependencies),
                    "dependencies": n.dependencies,
                    "args": n.args,
                    "position_x": n.position_x,
                    "position_y": n.position_y,
                }
                for n in canvas.tool_nodes
            ],
        },
        "edges": [
            {
                "id": e.id,
                "source_node_id": e.source_node_id,
                "target_node_id": e.target_node_id,
                "edge_type": e.edge_type,
            }
            for e in canvas.edges
        ],
        "documents": documents,
    }


@canvas_router.get("/{canvas_id}/export")
async def export_canvas(canvas_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.info(f"Exporting canvas: id={canvas_id}")
    repo = CanvasRepo(session)
    try:
        canvas = await repo.get_or_404(canvas_id)
    except CanvasNotFoundError:
        logger.warning(f"Canvas not found for export: id={canvas_id}")
        raise HTTPException(status_code=404, detail="Canvas not found") from None

    data = _canvas_to_response(canvas).model_dump(mode="json")
    content = json.dumps(data, indent=2, default=str)
    safe_name = canvas.name.replace(" ", "_").replace("/", "_")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="canvas-{safe_name}.json"'},
    )


@canvas_router.get("/{canvas_id}/export-zip")
async def export_canvas_zip(canvas_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    logger.info(f"Exporting canvas ZIP: id={canvas_id}")
    repo = CanvasRepo(session)
    try:
        canvas = await repo.get_or_404(canvas_id)
    except CanvasNotFoundError:
        logger.warning(f"Canvas not found for export: id={canvas_id}")
        raise HTTPException(status_code=404, detail="Canvas not found") from None

    payload = _canvas_to_import_payload(canvas)
    manifest = json.dumps(payload, indent=2, default=str)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest)
        for agent in canvas.agent_nodes:
            for doc in agent.documents:
                path = f"documents/{doc.agent_node_id}/{doc.id}.txt"
                zf.writestr(path, doc.content)
    buffer.seek(0)

    safe_name = canvas.name.replace(" ", "_").replace("/", "_")
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="canvas-{safe_name}.zip"'},
    )


@canvas_router.post("/import", response_model=CanvasResponse)
async def import_canvas(body: CanvasImportRequest, session: AsyncSession = Depends(get_session)):
    logger.info(
        f"Importing canvas: name={body.name}, "
        f"agents={len(body.nodes.agents)}, "
        f"tools={len(body.nodes.tools)}, edges={len(body.edges)}, documents={len(body.documents)}"
    )
    repo = CanvasRepo(session)
    canvas = await repo.create_full(
        name=body.name,
        agents=body.nodes.agents,
        tools=body.nodes.tools,
        edges=body.edges,
        documents=body.documents,
    )
    logger.info(f"Canvas imported: id={canvas.id}")
    return _canvas_to_response(canvas)


@canvas_router.post("/import-zip", response_model=CanvasResponse)
async def import_canvas_zip(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    logger.info("Importing canvas ZIP file")
    content_bytes = await file.read()
    try:
        archive = zipfile.ZipFile(io.BytesIO(content_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP archive") from None

    if "manifest.json" not in archive.namelist():
        raise HTTPException(status_code=400, detail="ZIP archive missing manifest.json")

    manifest_bytes = archive.read("manifest.json")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid manifest.json") from None

    documents = []
    for item in manifest.get("documents", []):
        path = item.get("path")
        if not path:
            raise HTTPException(status_code=400, detail="Document metadata must include path")
        try:
            doc_bytes = archive.read(path)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Missing document file: {path}") from None
        try:
            content_text = doc_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content_text = doc_bytes.decode("latin-1")
        documents.append(
            {
                "id": item.get("id"),
                "agent_node_id": item.get("agent_node_id"),
                "name": item.get("name"),
                "content": content_text,
                "created_at": item.get("created_at"),
            }
        )

    try:
        body = CanvasImportRequest.model_validate(manifest)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid manifest payload") from exc

    body.documents = [AgentDocumentInput(**doc) for doc in documents]
    repo = CanvasRepo(session)
    canvas = await repo.create_full(
        name=body.name,
        agents=body.nodes.agents,
        tools=body.nodes.tools,
        edges=body.edges,
        documents=body.documents,
    )
    logger.info(f"Canvas imported from ZIP: id={canvas.id}")
    return _canvas_to_response(canvas)


@canvas_router.post("/{canvas_id}/conversations", response_model=ConversationResponse)
async def create_conversation(
    canvas_id: uuid.UUID,
    body: CreateConversationRequest = CreateConversationRequest(),
    session: AsyncSession = Depends(get_session),
):
    logger.info("Creating conversation for canvas=%s name=%s", canvas_id, body.name)
    canvas_repo = CanvasRepo(session)
    try:
        await canvas_repo.get_or_404(canvas_id)
    except CanvasNotFoundError:
        raise HTTPException(status_code=404, detail="Canvas not found") from None

    repo = ConversationRepo(session)
    conv = await repo.create(canvas_id=canvas_id, name=body.name)
    logger.info("Conversation created: id=%s", conv.id)
    return conv


@canvas_router.get("/{canvas_id}/conversations", response_model=list[ConversationListResponse])
async def list_conversations(
    canvas_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    logger.debug("Listing conversations for canvas=%s", canvas_id)
    repo = ConversationRepo(session)
    conversations = await repo.list_for_canvas(canvas_id)
    return conversations


@canvas_router.get(
    "/{canvas_id}/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_conversation(
    canvas_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    logger.debug("Getting conversation: canvas=%s conv=%s", canvas_id, conversation_id)
    repo = ConversationRepo(session)
    try:
        conv = await repo.get_or_404(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    if conv.canvas_id != canvas_id:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    return conv


@canvas_router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_conversation_by_id(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    logger.debug("Getting conversation by id: conv=%s", conversation_id)
    repo = ConversationRepo(session)
    try:
        conv = await repo.get_or_404(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    return conv


@canvas_router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation_by_id(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    logger.info("Deleting conversation by id: conv=%s", conversation_id)
    repo = ConversationRepo(session)
    conv = await repo.get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    await repo.delete(conversation_id)
    logger.info("Conversation deleted by id: id=%s", conversation_id)


@canvas_router.delete("/{canvas_id}/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    canvas_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    logger.info("Deleting conversation: canvas=%s conv=%s", canvas_id, conversation_id)
    repo = ConversationRepo(session)
    conv = await repo.get(conversation_id)
    if not conv or conv.canvas_id != canvas_id:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    await repo.delete(conversation_id)
    logger.info("Conversation deleted: id=%s", conversation_id)


@canvas_router.get(
    "/{canvas_id}/agents/{agent_id}/documents",
    response_model=list[AgentDocumentResponse],
)
async def list_agent_documents(
    canvas_id: uuid.UUID,
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select

    from canvas_server.models.canvas import AgentDocument, AgentNode

    logger.info("Listing documents for canvas=%s agent=%s", canvas_id, agent_id)
    stmt = select(AgentNode).where(AgentNode.id == agent_id, AgentNode.canvas_id == canvas_id)
    res = await session.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc_stmt = (
        select(AgentDocument)
        .where(
            AgentDocument.agent_node_id == agent_id,
            AgentDocument.canvas_id == canvas_id,
        )
        .order_by(AgentDocument.created_at.desc())
    )
    res = await session.execute(doc_stmt)
    docs = res.scalars().all()
    return docs


@canvas_router.post("/{canvas_id}/agents/{agent_id}/documents", response_model=AgentDocumentResponse)
async def upload_agent_document(
    canvas_id: uuid.UUID,
    agent_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select

    from canvas_server.models.canvas import AgentDocument, AgentNode

    logger.info(
        "Uploading document for canvas=%s agent=%s name=%s",
        canvas_id,
        agent_id,
        file.filename,
    )
    stmt = select(AgentNode).where(AgentNode.id == agent_id, AgentNode.canvas_id == canvas_id)
    res = await session.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    content_bytes = await file.read()
    try:
        content_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content_text = content_bytes.decode("latin-1")

    doc = AgentDocument(
        id=uuid.uuid4(),
        canvas_id=canvas_id,
        agent_node_id=agent_id,
        name=file.filename or "Unnamed Document",
        content=content_text,
    )
    session.add(doc)
    await session.commit()
    logger.info("Document saved: id=%s", doc.id)

    from canvas_server.runner.rag_helper import RAGIndexManager

    await RAGIndexManager.trigger_reindex(agent_id)

    return doc


@canvas_router.delete("/{canvas_id}/agents/{agent_id}/documents/{document_id}", status_code=204)
async def delete_agent_document(
    canvas_id: uuid.UUID,
    agent_id: uuid.UUID,
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select

    from canvas_server.models.canvas import AgentDocument

    logger.info("Deleting document canvas=%s agent=%s doc=%s", canvas_id, agent_id, document_id)
    stmt = select(AgentDocument).where(
        AgentDocument.id == document_id,
        AgentDocument.agent_node_id == agent_id,
        AgentDocument.canvas_id == canvas_id,
    )
    res = await session.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await session.delete(doc)
    await session.commit()
    logger.info("Document deleted: id=%s", document_id)

    from canvas_server.runner.rag_helper import RAGIndexManager

    await RAGIndexManager.trigger_reindex(agent_id)
