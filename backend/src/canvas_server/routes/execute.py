import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from canvas_server.database import get_session_factory
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.runner import CanvasRunner

execute_router = APIRouter()


@execute_router.websocket("/ws/conversations/{conversation_id}/run")
async def run_conversation(websocket: WebSocket, conversation_id: uuid.UUID):
    await websocket.accept()

    try:
        data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        body = json.loads(data)
        user_prompt = body.get("prompt", "")
        target_agent_id_raw = body.get("target_agent_id")
        target_agent_id = (
            uuid.UUID(target_agent_id_raw) if target_agent_id_raw else None
        )

        factory = get_session_factory()
        async with factory() as session:
            conv_repo = ConversationRepo(session)
            conv = await conv_repo.get_or_404(conversation_id)

            canvas_repo = CanvasRepo(session)
            canvas = await canvas_repo.get_or_404(conv.canvas_id)

            runner = CanvasRunner(
                canvas,
                conversation_repo=conv_repo,
                conversation_id=conversation_id,
            )

            async def send_event(event: dict):
                try:
                    await websocket.send_text(json.dumps(event, default=str))
                except Exception:
                    pass

            async def run_task():
                try:
                    await runner.run(
                        user_prompt,
                        send_event,
                        target_agent_id=target_agent_id,
                    )
                except Exception as e:
                    await send_event(
                        {"type": "error", "message": str(e)}
                    )

            task = asyncio.create_task(run_task())

            try:
                await task
            except asyncio.CancelledError:
                pass

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
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(e)})
            )
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
