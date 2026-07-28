import uuid
from types import SimpleNamespace

import pytest

from canvas_server.execution_service import ExecutionService, RunStartRequest


class FakeSessionContext:
    async def __aenter__(self):
        class _Session:
            async def commit(self):
                return None

        return _Session()

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_get_run_events_after_adds_sequence_and_run_id():
    run_id = uuid.uuid4()

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def list_events(self, requested_run_id, *, after_sequence=0):
            assert requested_run_id == run_id
            assert after_sequence == 3
            return [
                SimpleNamespace(
                    payload={"content": "event-without-type"},
                    event_type="thought",
                    sequence=4,
                )
            ]

    service = ExecutionService(
        session_factory=lambda: FakeSessionContext(),
        durable_run_repo_factory=FakeDurableRunRepo,
    )

    events = await service.get_run_events_after(run_id=run_id, after_sequence=3)

    assert events == [
        {
            "type": "thought",
            "content": "event-without-type",
            "sequence": 4,
            "run_id": str(run_id),
        }
    ]


@pytest.mark.asyncio
async def test_prepare_run_creates_new_run_when_run_id_not_supplied():
    conversation_id = uuid.uuid4()
    target_agent_id = uuid.uuid4()
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
            captured["create_conversation_id"] = conversation_id
            captured["prompt"] = prompt
            captured["target_agent_id"] = target_agent_id
            return SimpleNamespace(id=run_id)

    service = ExecutionService(
        session_factory=lambda: FakeSessionContext(),
        conversation_repo_factory=FakeConversationRepo,
        durable_run_repo_factory=FakeDurableRunRepo,
    )

    result = await service.prepare_run(
        RunStartRequest(
            conversation_id=conversation_id,
            prompt="hello",
            requested_run_id=None,
            target_agent_id=target_agent_id,
        )
    )

    assert result.run_id == run_id
    assert result.is_new_run is True
    assert captured["conversation_id"] == conversation_id
    assert captured["create_conversation_id"] == conversation_id
    assert captured["prompt"] == "hello"
    assert captured["target_agent_id"] == target_agent_id


@pytest.mark.asyncio
async def test_prepare_run_rejects_mismatched_conversation():
    conversation_id = uuid.uuid4()
    other_conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()

    class FakeConversationRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_conversation_id):
            return SimpleNamespace(id=requested_conversation_id)

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=requested_run_id, conversation_id=other_conversation_id)

    service = ExecutionService(
        session_factory=lambda: FakeSessionContext(),
        conversation_repo_factory=FakeConversationRepo,
        durable_run_repo_factory=FakeDurableRunRepo,
    )

    with pytest.raises(ValueError, match="Run does not belong to conversation"):
        await service.prepare_run(
            RunStartRequest(
                conversation_id=conversation_id,
                prompt="",
                requested_run_id=run_id,
            )
        )


@pytest.mark.asyncio
async def test_submit_interrupt_response_persists_event_and_notifies_worker():
    run_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class FakeDurableRunRepo:
        def __init__(self, session):
            pass

        async def get_or_404(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=requested_run_id)

        async def append_event(self, requested_run_id, *, event_type, payload):
            captured["event_type"] = event_type
            captured["payload"] = payload
            return SimpleNamespace(sequence=7)

    class FakeWorker:
        async def submit_interrupt_response(self, request_id, body):
            captured["request_id"] = request_id
            captured["body"] = body
            return True

    service = ExecutionService(
        session_factory=lambda: FakeSessionContext(),
        durable_run_repo_factory=FakeDurableRunRepo,
        worker_provider=lambda: FakeWorker(),
    )

    result = await service.submit_interrupt_response(
        run_id=run_id,
        body={"request_id": "req-1", "content": "yes"},
    )

    assert result == {"ok": True, "request_id": "req-1"}
    assert captured["event_type"] == "interrupt_response"
    assert captured["payload"]["content"] == "yes"
    assert captured["request_id"] == "req-1"
