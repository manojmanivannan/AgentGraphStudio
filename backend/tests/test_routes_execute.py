import json
import uuid

from fastapi.testclient import TestClient

from canvas_server.main import app


class FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return None


def test_websocket_run_delegates_to_coordinator_and_forwards_events(monkeypatch):
    conversation_id = uuid.uuid4()
    target_agent_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            captured["session"] = session
            captured["conversation_repo_type"] = type(conversation_repo).__name__
            captured["canvas_repo_type"] = type(canvas_repo).__name__

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
        ):
            captured["conversation_id"] = conversation_id
            captured["user_prompt"] = user_prompt
            captured["target_agent_id"] = target_agent_id
            await send_event({"type": "run_start", "canvas_id": "canvas-1"})
            await send_event({"type": "run_complete", "result": "ok"})

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRunCoordinator",
        FakeCoordinator,
    )

    client = TestClient(app)
    try:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}/run") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "prompt": "solve this",
                        "target_agent_id": str(target_agent_id),
                    }
                )
            )

            first_event = json.loads(websocket.receive_text())
            second_event = json.loads(websocket.receive_text())
    finally:
        client.close()

    assert first_event == {"type": "run_start", "canvas_id": "canvas-1"}
    assert second_event == {"type": "run_complete", "result": "ok"}
    assert captured["conversation_id"] == conversation_id
    assert captured["user_prompt"] == "solve this"
    assert captured["target_agent_id"] == target_agent_id
    assert captured["conversation_repo_type"] == "ConversationRepo"
    assert captured["canvas_repo_type"] == "CanvasRepo"
