import uuid
from datetime import UTC, datetime, timedelta

from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.repos.durable_run_repo import DurableRunRepo


class TestDurableRunRepoCreate:
    async def test_create_run_persists_control_plane_metadata(
        self, blank_canvas, test_session
    ):
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(blank_canvas.id, "Durable Chat")

        repo = DurableRunRepo(test_session)
        target_agent_id = uuid.uuid4()

        run = await repo.create(
            conversation_id=conversation.id,
            prompt="Plan the work",
            target_agent_id=target_agent_id,
        )

        assert run.conversation_id == conversation.id
        assert run.prompt == "Plan the work"
        assert run.target_agent_id == target_agent_id
        assert run.status == "queued"
        assert run.attempt_count == 0
        assert run.replay_cursor == 0
        assert run.lease_owner is None
        assert run.lease_expires_at is None
        assert run.events == []


class TestDurableRunRepoEvents:
    async def test_append_event_sequences_events_for_replay(
        self, blank_canvas, test_session
    ):
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(blank_canvas.id, "Replay Chat")
        repo = DurableRunRepo(test_session)
        run = await repo.create(conversation.id, prompt="hello")

        first = await repo.append_event(
            run.id,
            event_type="thought",
            payload={"text": "first"},
        )
        second = await repo.append_event(
            run.id,
            event_type="tool_result",
            payload={"text": "second"},
        )

        assert first.sequence == 1
        assert second.sequence == 2

        events = await repo.list_events(run.id)
        assert [event.sequence for event in events] == [1, 2]
        assert events[0].payload == {"text": "first"}
        assert events[1].event_type == "tool_result"

        replay = await repo.list_events(run.id, after_sequence=1)
        assert [event.sequence for event in replay] == [2]


class TestDurableRunRepoTransitions:
    async def test_mark_running_completed_and_failed(
        self, blank_canvas, test_session
    ):
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(
            blank_canvas.id, "Stateful Chat"
        )
        repo = DurableRunRepo(test_session)
        run = await repo.create(conversation.id, prompt="run")

        lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
        await repo.mark_running(
            run.id,
            lease_owner="worker-1",
            lease_expires_at=lease_expires_at,
        )

        running = await repo.get(run.id)
        assert running is not None
        assert running.status == "running"
        assert running.lease_owner == "worker-1"
        assert running.lease_expires_at == lease_expires_at

        await repo.mark_completed(run.id, result="done")
        completed = await repo.get(run.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.final_result == "done"
        assert completed.final_error is None

        failed_run = await repo.create(conversation.id, prompt="fail")
        await repo.mark_failed(failed_run.id, error_message="boom")
        failed = await repo.get(failed_run.id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.final_result is None
        assert failed.final_error == "boom"

    async def test_mark_aborting_and_aborted(self, blank_canvas, test_session):
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(
            blank_canvas.id, "Abort Chat"
        )
        repo = DurableRunRepo(test_session)
        run = await repo.create(conversation.id, prompt="run")

        lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
        await repo.mark_running(
            run.id,
            lease_owner="worker-1",
            lease_expires_at=lease_expires_at,
        )

        await repo.mark_aborting(run.id)
        aborting = await repo.get(run.id)
        assert aborting is not None
        assert aborting.status == "aborting"

        await repo.mark_aborted(run.id, reason="Stopped by user")
        aborted = await repo.get(run.id)
        assert aborted is not None
        assert aborted.status == "aborted"
        assert aborted.final_result is None
        assert aborted.final_error == "Stopped by user"


class TestDurableRunRepoClaims:
    async def test_claim_next_runnable_claims_only_one_run_at_a_time(
        self, blank_canvas, test_session
    ):
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(blank_canvas.id, "Claim Chat")
        repo = DurableRunRepo(test_session)

        first = await repo.create(conversation.id, prompt="first")
        await repo.create(conversation.id, prompt="second")

        now = datetime.now(UTC)
        lease_expires = now + timedelta(minutes=1)

        claimed = await repo.claim_next_runnable(
            lease_owner="worker-a",
            lease_expires_at=lease_expires,
            now=now,
        )
        assert claimed is not None
        assert claimed.id == first.id
        assert claimed.status == "running"
        assert claimed.lease_owner == "worker-a"

        second_claim = await repo.claim_next_runnable(
            lease_owner="worker-b",
            lease_expires_at=lease_expires,
            now=now,
        )
        assert second_claim is not None
        assert second_claim.id != first.id
        assert second_claim.lease_owner == "worker-b"

        third_claim = await repo.claim_next_runnable(
            lease_owner="worker-c",
            lease_expires_at=lease_expires,
            now=now,
        )
        assert third_claim is None

    async def test_claim_next_runnable_recovers_stale_running_lease(
        self, blank_canvas, test_session
    ):
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(blank_canvas.id, "Recover Chat")
        repo = DurableRunRepo(test_session)
        run = await repo.create(conversation.id, prompt="recover me")

        old_now = datetime.now(UTC)
        old_expiry = old_now + timedelta(seconds=5)
        await repo.mark_running(
            run.id,
            lease_owner="worker-old",
            lease_expires_at=old_expiry,
        )
        await test_session.commit()

        reclaim_now = old_now + timedelta(minutes=5)
        reclaim_expiry = reclaim_now + timedelta(minutes=1)
        reclaimed = await repo.claim_next_runnable(
            lease_owner="worker-new",
            lease_expires_at=reclaim_expiry,
            now=reclaim_now,
        )

        assert reclaimed is not None
        assert reclaimed.id == run.id
        assert reclaimed.lease_owner == "worker-new"
        assert reclaimed.lease_expires_at == reclaim_expiry
        assert reclaimed.attempt_count == 2
