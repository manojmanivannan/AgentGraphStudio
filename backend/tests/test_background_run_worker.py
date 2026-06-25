from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from canvas_server.background_run_worker import BackgroundRunWorker
from canvas_server.database import get_session_factory
from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.repos.durable_run_repo import DurableRunRepo


@pytest.mark.asyncio
async def test_worker_processes_queued_run_and_marks_completed(
    blank_canvas, test_session, monkeypatch
):
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Worker Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="run in background")

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
        ):
            await send_event({"type": "run_start"})
            await send_event({"type": "run_complete", "result": "ok"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    processed = await worker.process_once()

    assert processed is True

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        updated_run = await fresh_repo.get_or_404(run.id)
        events = await fresh_repo.list_events(run.id)

    assert updated_run.status == "completed"
    assert updated_run.attempt_count == 1
    assert [event.sequence for event in events] == [1, 2]
    assert events[0].event_type == "run_start"
    assert events[1].event_type == "run_complete"


@pytest.mark.asyncio
async def test_worker_reclaims_expired_running_lease(
    blank_canvas, test_session, monkeypatch
):
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Recover Worker Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="recover run")

    expired_lease = datetime.now(UTC) - timedelta(minutes=2)
    await run_repo.mark_running(
        run.id,
        lease_owner="old-worker",
        lease_expires_at=expired_lease,
    )
    await test_session.commit()

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
        ):
            await send_event({"type": "run_complete"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    processed = await worker.process_once()

    assert processed is True

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        updated_run = await fresh_repo.get_or_404(run.id)

    assert updated_run.status == "completed"
    assert updated_run.attempt_count == 2


@pytest.mark.asyncio
async def test_worker_marks_run_aborted_when_abort_requested_mid_execution(
    blank_canvas, test_session, monkeypatch
):
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Abort Worker Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="please abort")

    first_event_sent = asyncio.Event()
    continue_execution = asyncio.Event()

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
        ):
            await send_event({"type": "run_start"})
            first_event_sent.set()
            await continue_execution.wait()
            await send_event({"type": "thought", "agent": "Planner", "content": "late event"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    process_task = asyncio.create_task(worker.process_once())

    await first_event_sent.wait()

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        await fresh_repo.mark_aborting(run.id)
        await session.commit()

    continue_execution.set()
    processed = await process_task
    assert processed is True

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        updated_run = await fresh_repo.get_or_404(run.id)
        events = await fresh_repo.list_events(run.id)

    assert updated_run.status == "aborted"
    assert events[0].event_type == "run_start"
    assert events[-1].event_type == "run_aborted"
