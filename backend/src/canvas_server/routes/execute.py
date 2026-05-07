import uuid
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from canvas_server.database import async_session_factory
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.runner import CanvasRunner

execute_router = APIRouter()


@execute_router.websocket("/ws/canvases/{canvas_id}/run")
async def run_canvas(websocket: WebSocket, canvas_id: uuid.UUID):
    await websocket.accept()

    try:
        data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        body = json.loads(data)
        user_prompt = body.get("prompt", "")

        async with async_session_factory() as session:
            repo = CanvasRepo(session)
            canvas = await repo.get_or_404(canvas_id)

            runner = CanvasRunner(canvas)

            async def send_event(event: dict):
                try:
                    await websocket.send_text(json.dumps(event, default=str))
                except Exception:
                    pass

            async def run_task():
                try:
                    await runner.run(user_prompt, send_event)
                except Exception as e:
                    await send_event({"type": "error", "message": str(e)})

            task = asyncio.create_task(run_task())

            try:
                await task
            except asyncio.CancelledError:
                pass

    except asyncio.TimeoutError:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": "No prompt received within 30s"}))
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
        try:
            await websocket.close()
        except Exception:
            pass
