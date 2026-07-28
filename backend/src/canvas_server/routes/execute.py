import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect

from canvas_server.background_run_worker import TERMINAL_RUN_STATUSES, get_background_run_worker
from canvas_server.config import settings
from canvas_server.database import get_session_factory
from canvas_server.execution_service import ExecutionService, RunStartRequest
from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.repos.durable_run_repo import DurableRunRepo

execute_router = APIRouter()


def get_execution_service() -> ExecutionService:
    factory = get_session_factory()
    return ExecutionService(
        session_factory=factory,
        conversation_repo_factory=ConversationRepo,
        durable_run_repo_factory=DurableRunRepo,
        worker_provider=get_background_run_worker,
        execution_mode=settings.execution_mode,
    )


@execute_router.get("/api/plots/{plot_id}", response_class=Response)
async def get_plot(
    plot_id: uuid.UUID,
    service: ExecutionService = Depends(get_execution_service),
):
    try:
        plot = await service.get_plot_payload(plot_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return Response(content=plot.content, media_type=plot.media_type)


@execute_router.get("/api/conversations/{conversation_id}/runs/active")
async def get_active_run(
    conversation_id: uuid.UUID,
    service: ExecutionService = Depends(get_execution_service),
):
    return await service.get_active_run(conversation_id)


@execute_router.get("/api/runs/{run_id}/events")
async def get_run_events(
    run_id: uuid.UUID,
    after_sequence: int = 0,
    service: ExecutionService = Depends(get_execution_service),
):
    return await service.get_run_events_after(
        run_id=run_id,
        after_sequence=after_sequence,
    )


@execute_router.post("/api/runs/{run_id}/interrupt-response")
async def submit_interrupt_response(
    run_id: uuid.UUID,
    body: dict,
    service: ExecutionService = Depends(get_execution_service),
):
    try:
        return await service.submit_interrupt_response(run_id=run_id, body=body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@execute_router.post("/api/runs/{run_id}/abort")
async def abort_run(
    run_id: uuid.UUID,
    service: ExecutionService = Depends(get_execution_service),
):
    return await service.abort_run(run_id)



@execute_router.websocket("/ws/conversations/{conversation_id}/run")
async def run_conversation(websocket: WebSocket, conversation_id: uuid.UUID):
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

        service = get_execution_service()
        try:
            start_result = await service.prepare_run(
                RunStartRequest(
                    conversation_id=conversation_id,
                    prompt=user_prompt,
                    requested_run_id=requested_run_id,
                    target_agent_id=target_agent_id,
                )
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        run_id = start_result.run_id

        if service.should_use_local_worker():
            worker = service.get_worker()
            await worker.ensure_started()
            queue = await worker.subscribe(run_id)

        if start_result.is_new_run:
            await websocket.send_text(
                json.dumps({"type": "run_queued", "run_id": str(run_id)})
            )
            if worker is not None:
                worker.kick()

        last_sequence = after_sequence

        while True:
            replay_events = await service.get_run_events_after(
                run_id=run_id, after_sequence=last_sequence
            )
            for event in replay_events:
                await websocket.send_text(json.dumps(event, default=str))
                last_sequence = max(last_sequence, int(event.get("sequence", 0)))

            status = await service.get_run_status(run_id)
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
