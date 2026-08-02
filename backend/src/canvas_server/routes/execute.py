import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect

from canvas_server.auth import get_current_user
from canvas_server.background_run_worker import (
    TERMINAL_RUN_STATUSES,
    get_background_run_worker,
)
from canvas_server.config import settings
from canvas_server.database import get_session_factory
from canvas_server.exceptions import ConversationNotFoundError, DurableRunNotFoundError
from canvas_server.models.auth import User
from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.repos.durable_run_repo import DurableRunRepo

execute_router = APIRouter()


async def _get_run_events_after(
    *,
    run_id: uuid.UUID,
    after_sequence: int,
) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        run_repo = DurableRunRepo(session)
        events = await run_repo.list_events(run_id, after_sequence=after_sequence)

    replay: list[dict] = []
    for event in events:
        payload = dict(event.payload or {})
        payload.setdefault("type", event.event_type)
        payload["sequence"] = event.sequence
        payload["run_id"] = str(run_id)
        replay.append(payload)
    return replay


async def _get_run_status(run_id: uuid.UUID) -> str | None:
    factory = get_session_factory()
    async with factory() as session:
        run_repo = DurableRunRepo(session)
        run = await run_repo.get(run_id)
    return run.status if run else None


@execute_router.get("/api/plots/{plot_id}", response_class=Response)
async def get_plot(
    plot_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    factory = get_session_factory()
    async with factory() as session:
        conv_repo = ConversationRepo(session)
        plot = await conv_repo.get_plot(plot_id)
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        # Plots are gated transitively through their conversation's canvas.
        if (
            plot.conversation is None
            or plot.conversation.canvas is None
            or plot.conversation.canvas.owner_id != current_user.id
        ):
            raise HTTPException(status_code=404, detail="Plot not found")
        return Response(content=plot.content, media_type=f"image/{plot.format}")


@execute_router.get("/api/conversations/{conversation_id}/runs/active")
async def get_active_run(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    factory = get_session_factory()
    async with factory() as session:
        conv_repo = ConversationRepo(session)
        try:
            conv = await conv_repo.get_or_404(conversation_id)
        except ConversationNotFoundError:
            raise HTTPException(status_code=404, detail="Conversation not found") from None
        if conv.canvas is None or conv.canvas.owner_id != current_user.id:
            raise HTTPException(status_code=404, detail="Conversation not found") from None

        run_repo = DurableRunRepo(session)
        run = await run_repo.get_latest_active_for_conversation(conversation_id)

        if run is None:
            return None

        return {
            "run_id": str(run.id),
            "conversation_id": str(run.conversation_id),
            "status": run.status,
            "replay_cursor": run.replay_cursor,
        }


@execute_router.get("/api/runs/{run_id}/events")
async def get_run_events(
    run_id: uuid.UUID,
    after_sequence: int = 0,
    current_user: User = Depends(get_current_user),
):
    factory = get_session_factory()
    async with factory() as session:
        run_repo = DurableRunRepo(session)
        try:
            run = await run_repo.get_or_404(run_id)
        except DurableRunNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found") from None
        if (
            run.conversation is None
            or run.conversation.canvas is None
            or run.conversation.canvas.owner_id != current_user.id
        ):
            raise HTTPException(status_code=404, detail="Run not found") from None
        events = await run_repo.list_events(run_id, after_sequence=after_sequence)

    replay: list[dict] = []
    for event in events:
        payload = dict(event.payload or {})
        payload.setdefault("type", event.event_type)
        payload["sequence"] = event.sequence
        payload["run_id"] = str(run_id)
        replay.append(payload)
    return replay


@execute_router.post("/api/runs/{run_id}/interrupt-response")
async def submit_interrupt_response(
    run_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
):
    request_id = body.get("request_id")
    if not request_id:
        raise HTTPException(status_code=422, detail="request_id is required")

    factory = get_session_factory()
    async with factory() as session:
        run_repo = DurableRunRepo(session)
        try:
            run = await run_repo.get_or_404(run_id)
        except DurableRunNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found") from None
        if (
            run.conversation is None
            or run.conversation.canvas is None
            or run.conversation.canvas.owner_id != current_user.id
        ):
            raise HTTPException(status_code=404, detail="Run not found") from None
        await run_repo.append_event(
            run_id,
            event_type="interrupt_response",
            payload=body,
        )
        await session.commit()

    try:
        worker = get_background_run_worker()
        await worker.submit_interrupt_response(request_id, body)
    except Exception:
        # In API-only mode, there may be no in-process worker to notify.
        pass

    return {"ok": True, "request_id": request_id}


@execute_router.post("/api/runs/{run_id}/abort")
async def abort_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    factory = get_session_factory()
    async with factory() as session:
        run_repo = DurableRunRepo(session)
        try:
            run = await run_repo.get_or_404(run_id)
        except DurableRunNotFoundError:
            raise HTTPException(status_code=404, detail="Run not found") from None
        if (
            run.conversation is None
            or run.conversation.canvas is None
            or run.conversation.canvas.owner_id != current_user.id
        ):
            raise HTTPException(status_code=404, detail="Run not found") from None

        if run.status in TERMINAL_RUN_STATUSES:
            return {
                "run_id": str(run.id),
                "status": run.status,
            }

        updated = await run_repo.mark_aborting(run_id)
        await session.commit()

        return {
            "run_id": str(updated.id),
            "status": updated.status,
        }



@execute_router.websocket("/ws/conversations/{conversation_id}/run")
async def run_conversation(
    websocket: WebSocket,
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    await websocket.accept()
    run_id: uuid.UUID | None = None
    worker = None
    queue = None

    try:
        data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        body = json.loads(data)
        user_prompt = body.get("prompt", "")
        requested_run_id_raw = body.get("run_id")
        requested_run_id = uuid.UUID(requested_run_id_raw) if requested_run_id_raw else None
        after_sequence = int(body.get("after_sequence", 0) or 0)
        target_agent_id_raw = body.get("target_agent_id")
        target_agent_id = (
            uuid.UUID(target_agent_id_raw) if target_agent_id_raw else None
        )

        factory = get_session_factory()
        async with factory() as session:
            conv_repo = ConversationRepo(session)
            try:
                conv = await conv_repo.get_or_404(conversation_id)
            except ConversationNotFoundError:
                raise HTTPException(status_code=404, detail="Conversation not found") from None
            if conv.canvas is None or conv.canvas.owner_id != current_user.id:
                raise HTTPException(status_code=404, detail="Conversation not found") from None
            run_repo = DurableRunRepo(session)

            if requested_run_id is not None:
                existing_run = await run_repo.get_or_404(requested_run_id)
                if existing_run.conversation_id != conversation_id:
                    raise HTTPException(status_code=400, detail="Run does not belong to conversation")
                run_id = existing_run.id
            else:
                if not user_prompt:
                    raise HTTPException(status_code=400, detail="prompt is required when run_id is not provided")

                run = await run_repo.create(
                    conversation_id=conversation_id,
                    prompt=user_prompt,
                    target_agent_id=target_agent_id,
                )
                run_id = run.id

        if settings.execution_mode != "api":
            worker = get_background_run_worker()
            await worker.ensure_started()
            queue = await worker.subscribe(run_id)

        if requested_run_id is None:
            await websocket.send_text(
                json.dumps({"type": "run_queued", "run_id": str(run_id)})
            )
            if worker is not None:
                worker.kick()

        last_sequence = after_sequence

        while True:
            replay_events = await _get_run_events_after(
                run_id=run_id, after_sequence=last_sequence
            )
            for event in replay_events:
                await websocket.send_text(json.dumps(event, default=str))
                last_sequence = max(last_sequence, int(event.get("sequence", 0)))

            status = await _get_run_status(run_id)
            if status in TERMINAL_RUN_STATUSES:
                break

            if queue is None:
                await asyncio.sleep(0.25)
                continue

            try:
                live_event = await asyncio.wait_for(queue.get(), timeout=1.0)
                sequence = int(live_event.get("sequence", 0))
                if sequence > last_sequence:
                    await websocket.send_text(json.dumps(live_event, default=str))
                    last_sequence = sequence
            except TimeoutError:
                continue

    except TimeoutError:
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "No prompt received within 30s",
                    }
                )
            )
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
    finally:
        if run_id and queue is not None and worker is not None:
            await worker.unsubscribe(run_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass
