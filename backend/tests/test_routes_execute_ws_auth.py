"""WebSocket run-route auth + ownership integration (issue #37).

Real DB + real cookie auth. The WebSocket run route
``/ws/conversations/{conversation_id}/run`` authenticates at the upgrade
handshake via ``Depends(get_current_user)`` (FastAPI rejects the upgrade before
``accept()`` when the dependency raises ``HTTPException``) and re-checks
ownership of the path conversation before reading the prompt, so a cross-user
connection is rejected with an error event and no run is created.

These complement the faked orchestration tests in ``test_routes_execute.py``
(which override ``get_current_user`` and stub the repos) and the REST
isolation tests in ``test_routes_execute_auth.py``. The sync ``TestClient`` is
the only WS-capable client available (httpx has no websocket_connect); we drive
it from async tests using ``test_session`` for setup — the same sync-in-async
pattern the ``authed_sync_client`` fixture already uses.
"""

import json
import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.repos.durable_run_repo import DurableRunRepo


async def _setup_canvas_and_conversation(session, owner_id, name="C", conv_name="V"):
    canvas = await CanvasRepo(session).create(name=name, owner_id=owner_id)
    conv = await ConversationRepo(session).create(canvas_id=canvas.id, name=conv_name)
    await session.commit()
    return canvas, conv


@pytest.mark.asyncio
class TestWebSocketRunAuth:
    async def test_unauthenticated_upgrade_is_rejected(
        self, make_authed_sync_client, fresh_db
    ):
        # The factory fixture wires the test-DB get_session override + teardown.
        from fastapi.testclient import TestClient

        from canvas_server.main import app

        unauthed = TestClient(app, base_url="http://test")
        cid = uuid.uuid4()
        with pytest.raises(WebSocketDisconnect), unauthed.websocket_connect(
            f"/ws/conversations/{cid}/run"
        ) as ws:
            ws.send_text(json.dumps({"prompt": "hi"}))
            ws.receive_text()

    async def test_cross_user_run_rejected_no_run_created(
        self, make_authed_sync_client, test_session
    ):
        alice = make_authed_sync_client()
        bob = make_authed_sync_client()

        _, alice_conv = await _setup_canvas_and_conversation(
            test_session, alice.auth_user_id
        )

        # Bob cannot run a conversation inside Alice's canvas: the route checks
        # ownership before reading the prompt, so Bob gets an error event
        # immediately (no prompt sent) and the socket closes.
        with bob.websocket_connect(f"/ws/conversations/{alice_conv.id}/run") as ws:
            event = json.loads(ws.receive_text())
        assert event == {"type": "error", "message": "Conversation not found"}

        # No run was created for Alice's conversation.
        active = alice.get(f"/api/conversations/{alice_conv.id}/runs/active")
        assert active.status_code == 200
        assert active.json() is None

    async def test_own_user_run_proceeds(self, make_authed_sync_client, test_session, monkeypatch):
        alice = make_authed_sync_client()

        _, alice_conv = await _setup_canvas_and_conversation(
            test_session, alice.auth_user_id
        )

        # Avoid driving the real worker/LLM: api mode skips the worker, a
        # terminal _get_run_status lets the streaming loop exit after queuing,
        # and _get_run_events_after is stubbed so the loop does zero DB I/O.
        #
        # The event-replay DB read MUST be stubbed here (not just status):
        # ``alice`` is a sync Starlette ``TestClient``, which runs the WS route
        # in a separate portal event loop while the test's loop is blocked
        # inside the ``with websocket_connect(...)`` block. The route shares the
        # real async engine (one pool) across both loops; a ``list_events``
        # SELECT scheduled on the test loop while that loop is blocked in
        # ``receive_text``/``__exit__`` deadlocks the aiosqlite worker. (The
        # handshake-time reads — ownership check + run create+commit — happen
        # before the client blocks, so they don't hit this; the loop's first
        # read does.) The faked WS tests in ``test_routes_execute.py`` avoid it
        # by stubbing ``get_session_factory``/repos wholesale; here we keep the
        # real handshake + real run persistence and only stub the loop's read so
        # the loop terminates cleanly. This test asserts run_queued + persistence
        # — not event replay, which the faked suite already covers.
        monkeypatch.setattr(
            "canvas_server.routes.execute.settings.execution_mode", "api"
        )

        async def _terminal_status(_run_id):
            return "completed"

        monkeypatch.setattr(
            "canvas_server.routes.execute._get_run_status", _terminal_status
        )

        async def _no_events(*, run_id, after_sequence):
            return []

        monkeypatch.setattr(
            "canvas_server.routes.execute._get_run_events_after", _no_events
        )

        with alice.websocket_connect(f"/ws/conversations/{alice_conv.id}/run") as ws:
            ws.send_text(json.dumps({"prompt": "hi"}))
            queued = json.loads(ws.receive_text())

        assert queued["type"] == "run_queued"
        run_id = uuid.UUID(queued["run_id"])

        # The run was actually persisted for Alice's conversation.
        active = alice.get(f"/api/conversations/{alice_conv.id}/runs/active")
        assert active.status_code == 200
        assert active.json()["run_id"] == str(run_id)

    async def test_cross_user_replay_via_own_conversation_rejected(
        self, make_authed_sync_client, test_session
    ):
        alice = make_authed_sync_client()
        bob = make_authed_sync_client()

        _, alice_conv = await _setup_canvas_and_conversation(
            test_session, alice.auth_user_id, name="alice-canvas"
        )
        # An existing run owned by Alice, in Alice's conversation.
        alice_run = await DurableRunRepo(test_session).create(
            conversation_id=alice_conv.id, prompt="alice run"
        )
        # Bob owns his own canvas + conversation.
        _, bob_conv = await _setup_canvas_and_conversation(
            test_session, bob.auth_user_id, name="bob-canvas", conv_name="bob-conv"
        )

        # Bob owns bob_conv (ownership check passes), but tries to replay
        # Alice's run_id against it. The resume guard rejects a run that does
        # not belong to the path conversation — no run created in Bob's conv.
        with bob.websocket_connect(f"/ws/conversations/{bob_conv.id}/run") as ws:
            ws.send_text(json.dumps({"run_id": str(alice_run.id)}))
            event = json.loads(ws.receive_text())
        assert event["type"] == "error"
        assert "does not belong" in event["message"]

        active = bob.get(f"/api/conversations/{bob_conv.id}/runs/active")
        assert active.status_code == 200
        assert active.json() is None
