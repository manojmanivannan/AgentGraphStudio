import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.database import get_session
from canvas_server.exceptions import CanvasNotFoundError, ConversationNotFoundError
from canvas_server.models.api import (
    CanvasListResponse,
    CanvasResponse,
    CanvasSaveRequest,
    ConversationListResponse,
    ConversationResponse,
    CreateCanvasRequest,
    CreateConversationRequest,
)
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.repos.conversation_repo import ConversationRepo

logger = logging.getLogger("canvas_server.routes.canvas")
canvas_router = APIRouter(prefix="/api/canvases", tags=["canvases"])


def _canvas_to_response(canvas) -> CanvasResponse:
    from canvas_server.models.api import (
        AgentNodeResponse,
        CanvasNodesInput,
        EdgeResponse,
        ToolNodeResponse,
    )

    return CanvasResponse(
        id=canvas.id,
        name=canvas.name,
        created_at=canvas.created_at,
        updated_at=canvas.updated_at,
        nodes=CanvasNodesInput(
            agents=[
                AgentNodeResponse(
                    id=n.id,
                    canvas_id=n.canvas_id,
                    name=n.name,
                    role=n.role,
                    instructions=n.instructions,
                    model_name=n.model_name,
                    agent_type=n.agent_type,
                    enable_memory=n.enable_memory,
                    enable_conversation_history=n.enable_conversation_history,
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
    logger.debug(f"Canvas fetched: id={canvas_id}, agents={len(canvas.agent_nodes)}, "
                 f"tools={len(canvas.tool_nodes)}, edges={len(canvas.edges)}")
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


@canvas_router.get("/{canvas_id}/export")
async def export_canvas(
    canvas_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
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
        headers={
            "Content-Disposition": f'attachment; filename="canvas-{safe_name}.json"'
        },
    )


@canvas_router.post("/import", response_model=CanvasResponse)
async def import_canvas(
    body: CanvasSaveRequest, session: AsyncSession = Depends(get_session)
):
    logger.info(
        f"Importing canvas: name={body.name}, "
        f"agents={len(body.nodes.agents)}, "
        f"tools={len(body.nodes.tools)}, edges={len(body.edges)}"
    )
    repo = CanvasRepo(session)
    canvas = await repo.create_full(
        name=body.name,
        agents=body.nodes.agents,
        tools=body.nodes.tools,
        edges=body.edges,
    )
    logger.info(f"Canvas imported: id={canvas.id}")
    return _canvas_to_response(canvas)


@canvas_router.post(
    "/{canvas_id}/conversations", response_model=ConversationResponse
)
async def create_conversation(
    canvas_id: uuid.UUID,
    body: CreateConversationRequest = CreateConversationRequest(),
    session: AsyncSession = Depends(get_session),
):
    logger.info(
        "Creating conversation for canvas=%s name=%s", canvas_id, body.name
    )
    canvas_repo = CanvasRepo(session)
    try:
        await canvas_repo.get_or_404(canvas_id)
    except CanvasNotFoundError:
        raise HTTPException(status_code=404, detail="Canvas not found") from None

    repo = ConversationRepo(session)
    conv = await repo.create(canvas_id=canvas_id, name=body.name)
    logger.info("Conversation created: id=%s", conv.id)
    return conv


@canvas_router.get(
    "/{canvas_id}/conversations", response_model=list[ConversationListResponse]
)
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
    logger.debug(
        "Getting conversation: canvas=%s conv=%s", canvas_id, conversation_id
    )
    repo = ConversationRepo(session)
    try:
        conv = await repo.get_or_404(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=404, detail="Conversation not found"
        ) from None
    if conv.canvas_id != canvas_id:
        raise HTTPException(
            status_code=404, detail="Conversation not found"
        ) from None
    return conv


@canvas_router.delete("/{canvas_id}/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    canvas_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    logger.info(
        "Deleting conversation: canvas=%s conv=%s", canvas_id, conversation_id
    )
    repo = ConversationRepo(session)
    conv = await repo.get(conversation_id)
    if not conv or conv.canvas_id != canvas_id:
        raise HTTPException(
            status_code=404, detail="Conversation not found"
        ) from None
    await repo.delete(conversation_id)
    logger.info("Conversation deleted: id=%s", conversation_id)
