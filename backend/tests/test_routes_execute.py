import asyncio
import json
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from canvas_server.main import app


class FakeSessionContext:
    async def __aenter__(self):
        class _Session:
            async def commit(self):
                return None

        return _Session()

    async def __aexit__(self, exc_type, exc, tb):
        return None


def test_websocket_run_delegates_to_coordinator_and_forwards_events(monkeypatch):
    conversation_id = uuid.uuid4()
    target_agent_id = uuid.uuid4()
    run_id = uuid.uuid4()
    captured: dict[str, object] = {"run_id": run_id}

    class FakeConversationRepo:
        def __init__(self, session):
            captured["session"] = session

        async def get_or_404(self, requested_conversation_id):
            captured["conversation_id"] = requested_conversation_id
            return SimpleNamespace(id=requested_conversation_id)

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def create(self, *, conversation_id, prompt, target_agent_id=None):
            captured["create_conversation_id"] = conversation_id
            captured["prompt"] = prompt
            captured["target_agent_id"] = target_agent_id
            return SimpleNamespace(id=run_id)

        async def list_events(self, requested_run_id, *, after_sequence=0):
            if after_sequence > 0:
                return []
            return [
                SimpleNamespace(
                    payload={"type": "run_start", "canvas_id": "canvas-1"},
                    event_type="run_start",
                    sequence=1,
                ),
                SimpleNamespace(
                    payload={"type": "run_complete", "result": "ok"},
                    event_type="run_complete",
                    sequence=2,
                ),
            ]

        async def get(self, requested_run_id):
            return SimpleNamespace(id=requested_run_id, status="completed")

    class FakeWorker:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.started = False
            self.kicked = False

        async def ensure_started(self):
            self.started = True

        async def subscribe(self, requested_run_id):
            captured["subscribed_run_id"] = requested_run_id
            return self.queue

        async def unsubscribe(self, requested_run_id, queue):
            captured["unsubscribed_run_id"] = requested_run_id

        def kick(self):
            self.kicked = True

    fake_worker = FakeWorker()

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: fake_worker,
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

            queued_event = json.loads(websocket.receive_text())
            first_event = json.loads(websocket.receive_text())
            second_event = json.loads(websocket.receive_text())
    finally:
        client.close()

    assert queued_event == {"type": "run_queued", "run_id": str(run_id)}
    assert first_event == {
        "type": "run_start",
        "canvas_id": "canvas-1",
        "sequence": 1,
        "run_id": str(run_id),
    }
    assert second_event == {
        "type": "run_complete",
        "result": "ok",
        "sequence": 2,
        "run_id": str(run_id),
    }
    assert captured["conversation_id"] == conversation_id
    assert captured["create_conversation_id"] == conversation_id
    assert captured["prompt"] == "solve this"
    assert captured["target_agent_id"] == target_agent_id
    assert captured["subscribed_run_id"] == run_id
    assert captured["unsubscribed_run_id"] == run_id
    assert fake_worker.started is True
    assert fake_worker.kicked is True


def test_websocket_disconnect_does_not_cancel_background_run(monkeypatch):
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()

    class FakeConversationRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_conversation_id):
            return SimpleNamespace(id=requested_conversation_id)

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def create(self, *, conversation_id, prompt, target_agent_id=None):
            return SimpleNamespace(id=run_id)

    class FakeWorker:
        def __init__(self):
            self.active_runs: set[uuid.UUID] = set()
            self.subscribers: set[uuid.UUID] = set()

        async def ensure_started(self):
            return None

        async def subscribe(self, requested_run_id):
            self.active_runs.add(requested_run_id)
            self.subscribers.add(requested_run_id)
            return asyncio.Queue()

        async def unsubscribe(self, requested_run_id, queue):
            self.subscribers.discard(requested_run_id)

        def kick(self):
            return None

        async def get_run_events_after(self, *, run_id, after_sequence):
            return []

        async def get_run_status(self, requested_run_id):
            return "running"

    fake_worker = FakeWorker()

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: fake_worker,
    )

    client = TestClient(app)
    try:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}/run") as websocket:
            websocket.send_text(json.dumps({"prompt": "still running"}))
            queued_event = json.loads(websocket.receive_text())
            assert queued_event == {"type": "run_queued", "run_id": str(run_id)}
    finally:
        client.close()

    deadline = time.time() + 1.0
    while run_id in fake_worker.subscribers and time.time() < deadline:
        time.sleep(0.01)

    assert run_id in fake_worker.active_runs
    assert run_id not in fake_worker.subscribers


def test_get_plot_route_success(monkeypatch):
    plot_id = uuid.uuid4()

    class FakePlot:
        id = plot_id
        content = b"fake-binary-content"
        format = "png"

    class FakeConversationRepo:
        def __init__(self, session):
            pass
        async def get_plot(self, pid):
            assert pid == plot_id
            return FakePlot()

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )

    client = TestClient(app)
    response = client.get(f"/api/plots/{plot_id}")
    assert response.status_code == 200
    assert response.content == b"fake-binary-content"
    assert response.headers["content-type"] == "image/png"


def test_get_plot_route_not_found(monkeypatch):
    plot_id = uuid.uuid4()

    class FakeConversationRepo:
        def __init__(self, session):
            pass
        async def get_plot(self, pid):
            return None

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )

    client = TestClient(app)
    response = client.get(f"/api/plots/{plot_id}")
    assert response.status_code == 404


def test_get_active_run_route_returns_latest_non_terminal_run(monkeypatch):
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()

    class FakeConversationRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_conversation_id):
            assert requested_conversation_id == conversation_id
            return SimpleNamespace(id=requested_conversation_id)

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_latest_active_for_conversation(self, requested_conversation_id):
            assert requested_conversation_id == conversation_id
            return SimpleNamespace(
                id=run_id,
                conversation_id=conversation_id,
                status="running",
                replay_cursor=7,
            )

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )

    client = TestClient(app)
    response = client.get(f"/api/conversations/{conversation_id}/runs/active")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": str(run_id),
        "conversation_id": str(conversation_id),
        "status": "running",
        "replay_cursor": 7,
    }


def test_get_run_events_route_replays_after_sequence(monkeypatch):
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeEvent:
        def __init__(self, sequence, payload, event_type):
            self.sequence = sequence
            self.payload = payload
            self.event_type = event_type

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def list_events(self, requested_run_id, *, after_sequence=0):
            captured["run_id"] = requested_run_id
            captured["after_sequence"] = after_sequence
            return [
                FakeEvent(
                    sequence=4,
                    payload={"type": "thought", "content": "replayed"},
                    event_type="thought",
                )
            ]

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )

    client = TestClient(app)
    response = client.get(f"/api/runs/{run_id}/events", params={"after_sequence": 3})

    assert response.status_code == 200
    assert response.json() == [
        {
            "type": "thought",
            "content": "replayed",
            "sequence": 4,
            "run_id": str(run_id),
        }
    ]
    assert captured["run_id"] == run_id
    assert captured["after_sequence"] == 3


def test_abort_run_route_marks_running_run_as_aborting(monkeypatch):
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=run_id, status="running", conversation_id=uuid.uuid4())

        async def mark_aborting(self, requested_run_id):
            assert requested_run_id == run_id
            captured["marked"] = True
            return SimpleNamespace(id=run_id, status="aborting", conversation_id=uuid.uuid4())

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )

    client = TestClient(app)
    response = client.post(f"/api/runs/{run_id}/abort")

    assert response.status_code == 200
    assert response.json()["run_id"] == str(run_id)
    assert response.json()["status"] == "aborting"
    assert captured["marked"] is True


def test_abort_run_route_keeps_terminal_run_unchanged(monkeypatch):
    run_id = uuid.uuid4()

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=run_id, status="aborted", conversation_id=uuid.uuid4())

        async def mark_aborting(self, requested_run_id):
            raise AssertionError("mark_aborting should not be called for terminal runs")

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )

    client = TestClient(app)
    response = client.post(f"/api/runs/{run_id}/abort")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": str(run_id),
        "status": "aborted",
    }


def test_websocket_run_supports_resuming_existing_run(monkeypatch):
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeConversationRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_conversation_id):
            captured["conversation_id"] = requested_conversation_id
            return SimpleNamespace(id=requested_conversation_id)

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def create(self, *, conversation_id, prompt, target_agent_id=None):
            raise AssertionError("create should not be called in resume mode")

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=requested_run_id, conversation_id=conversation_id)

        async def list_events(self, requested_run_id, *, after_sequence=0):
            captured["after_sequence"] = after_sequence
            return [
                SimpleNamespace(
                    payload={"type": "final_answer", "content": "resumed"},
                    event_type="final_answer",
                    sequence=6,
                )
            ]

        async def get(self, requested_run_id):
            return SimpleNamespace(id=requested_run_id, status="completed")

    class FakeWorker:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def ensure_started(self):
            return None

        async def subscribe(self, requested_run_id):
            captured["subscribed_run_id"] = requested_run_id
            return self.queue

        async def unsubscribe(self, requested_run_id, queue):
            captured["unsubscribed_run_id"] = requested_run_id

        def kick(self):
            return None

    fake_worker = FakeWorker()

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: fake_worker,
    )

    client = TestClient(app)
    try:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}/run") as websocket:
            websocket.send_text(
                json.dumps(
                    {
                        "run_id": str(run_id),
                        "after_sequence": 5,
                    }
                )
            )
            replayed_event = json.loads(websocket.receive_text())
    finally:
        client.close()

    assert replayed_event == {
        "type": "final_answer",
        "content": "resumed",
        "sequence": 6,
        "run_id": str(run_id),
    }
    assert captured["conversation_id"] == conversation_id
    assert captured["subscribed_run_id"] == run_id
    assert captured["unsubscribed_run_id"] == run_id
    assert captured["after_sequence"] == 5


def test_websocket_resume_does_not_restart_aborted_run(monkeypatch):
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeConversationRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_conversation_id):
            return SimpleNamespace(id=requested_conversation_id)

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            return SimpleNamespace(id=requested_run_id, conversation_id=conversation_id, status="aborted")

        async def list_events(self, requested_run_id, *, after_sequence=0):
            return []

        async def get(self, requested_run_id):
            return SimpleNamespace(id=requested_run_id, status="aborted")

    class FakeWorker:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def ensure_started(self):
            return None

        async def subscribe(self, requested_run_id):
            captured["subscribed"] = requested_run_id
            return self.queue

        async def unsubscribe(self, requested_run_id, queue):
            captured["unsubscribed"] = requested_run_id

        def kick(self):
            return None

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: FakeWorker(),
    )

    client = TestClient(app)
    with client.websocket_connect(f"/ws/conversations/{conversation_id}/run") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "run_id": str(run_id),
                    "after_sequence": 0,
                }
            )
        )
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()

    assert captured["subscribed"] == run_id
    assert captured["unsubscribed"] == run_id


def test_websocket_run_in_api_mode_streams_events_without_local_worker(monkeypatch):
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()

    class FakeConversationRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_conversation_id):
            return SimpleNamespace(id=requested_conversation_id)

    class FakeEvent:
        def __init__(self, sequence, payload, event_type):
            self.sequence = sequence
            self.payload = payload
            self.event_type = event_type

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def create(self, *, conversation_id, prompt, target_agent_id=None):
            return SimpleNamespace(id=run_id)

        async def list_events(self, requested_run_id, *, after_sequence=0):
            if requested_run_id != run_id:
                return []
            if after_sequence >= 1:
                return []
            return [
                FakeEvent(
                    sequence=1,
                    payload={"type": "run_complete", "result": "ok"},
                    event_type="run_complete",
                )
            ]

        async def get(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=run_id, status="completed")

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.ConversationRepo",
        FakeConversationRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.settings.execution_mode",
        "api",
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: (_ for _ in ()).throw(AssertionError("worker should not be used in api mode")),
    )

    client = TestClient(app)
    try:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}/run") as websocket:
            websocket.send_text(json.dumps({"prompt": "run in api-only mode"}))

            queued_event = json.loads(websocket.receive_text())
            completed_event = json.loads(websocket.receive_text())
    finally:
        client.close()

    assert queued_event == {"type": "run_queued", "run_id": str(run_id)}
    assert completed_event == {
        "type": "run_complete",
        "result": "ok",
        "sequence": 1,
        "run_id": str(run_id),
    }


def test_submit_interrupt_response_route_resolves_pending_interrupt(monkeypatch):
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=run_id, status="running")

        async def append_event(self, requested_run_id, *, event_type, payload):
            captured["event_type"] = event_type
            captured["payload"] = payload
            return SimpleNamespace(sequence=5)

    class FakeWorker:
        async def submit_interrupt_response(self, request_id, response):
            captured["request_id"] = request_id
            captured["response"] = response
            return True

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: FakeWorker(),
    )

    client = TestClient(app)
    response = client.post(
        f"/api/runs/{run_id}/interrupt-response",
        json={"request_id": "req-abc", "type": "human_input_response", "content": "yes"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["request_id"] == "req-abc"
    assert captured["request_id"] == "req-abc"
    assert captured["response"]["content"] == "yes"
    assert captured["event_type"] == "interrupt_response"


def test_submit_interrupt_response_route_persists_durable_event_for_external_worker(monkeypatch):
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=run_id, status="running")

        async def append_event(self, requested_run_id, *, event_type, payload):
            captured["run_id"] = requested_run_id
            captured["event_type"] = event_type
            captured["payload"] = payload
            return SimpleNamespace(sequence=9)

    class FakeWorker:
        async def submit_interrupt_response(self, request_id, response):
            return False

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: FakeWorker(),
    )

    client = TestClient(app)
    response = client.post(
        f"/api/runs/{run_id}/interrupt-response",
        json={"request_id": "req-durable", "type": "human_input_response", "content": "yes"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "request_id": "req-durable"}
    assert captured["run_id"] == run_id
    assert captured["event_type"] == "interrupt_response"
    assert captured["payload"]["request_id"] == "req-durable"


def test_submit_interrupt_response_route_returns_200_even_without_local_pending_interrupt(
    monkeypatch,
):
    run_id = uuid.uuid4()

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=run_id, status="running")

        async def append_event(self, requested_run_id, *, event_type, payload):
            return SimpleNamespace(sequence=11)

    class FakeWorker:
        async def submit_interrupt_response(self, request_id, response):
            return False  # no pending interrupt for that request_id

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_session_factory",
        lambda: (lambda: FakeSessionContext()),
    )
    monkeypatch.setattr(
        "canvas_server.routes.execute.DurableRunRepo",
        FakeDurableRunRepo,
    )

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: FakeWorker(),
    )

    client = TestClient(app)
    response = client.post(
        f"/api/runs/{run_id}/interrupt-response",
        json={"request_id": "req-unknown", "type": "human_input_response", "content": "hi"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "request_id": "req-unknown"}


def test_submit_interrupt_response_route_returns_422_when_request_id_missing(monkeypatch):
    run_id = uuid.uuid4()

    class FakeWorker:
        async def submit_interrupt_response(self, request_id, response):
            raise AssertionError("should not reach submit")

    monkeypatch.setattr(
        "canvas_server.routes.execute.get_background_run_worker",
        lambda: FakeWorker(),
    )

    client = TestClient(app)
    response = client.post(
        f"/api/runs/{run_id}/interrupt-response",
        json={"type": "human_input_response", "content": "hi"},
    )

    assert response.status_code == 422
