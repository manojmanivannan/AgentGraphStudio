"""Auth + ownership integration for the execute routes (issue #36).

These exercise the real DB + real cookie auth (via ``make_authed_client``),
complementing the faked orchestration tests in ``test_routes_execute.py``.
Covers: unauthed execute routes -> 401; cross-user plot/run/active-run/events
-> 404.
"""

import uuid

import pytest

ORIGIN = {"Origin": "http://test"}


async def _make_canvas(session, owner_id, name="C"):
    from canvas_server.repos.canvas_repo import CanvasRepo

    return await CanvasRepo(session).create(name=name, owner_id=owner_id)


async def _make_conversation(session, canvas_id, name="Conv"):
    from canvas_server.repos.conversation_repo import ConversationRepo

    return await ConversationRepo(session).create(canvas_id=canvas_id, name=name)


async def _make_plot(session, conversation_id):
    from canvas_server.repos.conversation_repo import ConversationRepo

    return await ConversationRepo(session).save_plot(
        conversation_id=conversation_id, content=b"png-bytes", format="png"
    )


async def _make_run(session, conversation_id, prompt="hi"):
    from canvas_server.repos.durable_run_repo import DurableRunRepo

    return await DurableRunRepo(session).create(
        conversation_id=conversation_id, prompt=prompt
    )


@pytest.mark.asyncio
class TestExecuteRoutesRequireAuth:
    async def test_unauthed_execute_routes_return_401(self, test_client, fresh_db):
        pid = uuid.uuid4()
        cid = uuid.uuid4()
        rid = uuid.uuid4()
        assert (await test_client.get(f"/api/plots/{pid}")).status_code == 401
        assert (
            await test_client.get(f"/api/conversations/{cid}/runs/active")
        ).status_code == 401
        assert (await test_client.get(f"/api/runs/{rid}/events")).status_code == 401
        assert (await test_client.post(f"/api/runs/{rid}/abort")).status_code == 401
        assert (
            await test_client.post(
                f"/api/runs/{rid}/interrupt-response",
                json={"request_id": "r", "type": "human_input_response"},
            )
        ).status_code == 401


@pytest.mark.asyncio
class TestExecuteRoutesPerUserIsolation:
    async def test_cross_user_plot_returns_404(self, make_authed_client, test_session):
        alice = await make_authed_client()
        bob = await make_authed_client()

        canvas = await _make_canvas(test_session, alice.auth_user_id)
        conv = await _make_conversation(test_session, canvas.id)
        plot = await _make_plot(test_session, conv.id)
        await test_session.commit()

        # Bob cannot fetch Alice's plot; Alice can.
        assert (await bob.get(f"/api/plots/{plot.id}")).status_code == 404
        assert (await alice.get(f"/api/plots/{plot.id}")).status_code == 200

    async def test_cross_user_active_run_returns_404(
        self, make_authed_client, test_session
    ):
        alice = await make_authed_client()
        bob = await make_authed_client()

        canvas = await _make_canvas(test_session, alice.auth_user_id)
        conv = await _make_conversation(test_session, canvas.id)
        await _make_run(test_session, conv.id, prompt="alice run")
        await test_session.commit()

        # Bob probing Alice's conversation's active run -> 404 (not owned).
        assert (
            await bob.get(f"/api/conversations/{conv.id}/runs/active")
        ).status_code == 404
        # Alice sees her (terminal-less) conversation -> 200 with null body.
        assert (
            await alice.get(f"/api/conversations/{conv.id}/runs/active")
        ).status_code == 200

    async def test_cross_user_run_events_returns_404(
        self, make_authed_client, test_session
    ):
        alice = await make_authed_client()
        bob = await make_authed_client()

        canvas = await _make_canvas(test_session, alice.auth_user_id)
        conv = await _make_conversation(test_session, canvas.id)
        run = await _make_run(test_session, conv.id, prompt="alice run")
        await test_session.commit()

        assert (await bob.get(f"/api/runs/{run.id}/events")).status_code == 404
        assert (await alice.get(f"/api/runs/{run.id}/events")).status_code == 200

    async def test_cross_user_abort_returns_404(self, make_authed_client, test_session):
        alice = await make_authed_client()
        bob = await make_authed_client()

        canvas = await _make_canvas(test_session, alice.auth_user_id)
        conv = await _make_conversation(test_session, canvas.id)
        run = await _make_run(test_session, conv.id, prompt="alice run")
        await test_session.commit()

        assert (await bob.post(f"/api/runs/{run.id}/abort")).status_code == 404
        # Alice can abort her own run.
        resp = await alice.post(f"/api/runs/{run.id}/abort")
        assert resp.status_code == 200
        assert resp.json()["status"] == "aborting"

    async def test_cross_user_interrupt_response_returns_404(
        self, make_authed_client, test_session
    ):
        alice = await make_authed_client()
        bob = await make_authed_client()

        canvas = await _make_canvas(test_session, alice.auth_user_id)
        conv = await _make_conversation(test_session, canvas.id)
        run = await _make_run(test_session, conv.id, prompt="alice run")
        await test_session.commit()

        assert (
            await bob.post(
                f"/api/runs/{run.id}/interrupt-response",
                json={"request_id": "r", "type": "human_input_response", "content": "x"},
            )
        ).status_code == 404
