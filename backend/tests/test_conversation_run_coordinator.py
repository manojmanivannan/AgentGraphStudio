import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from canvas_server.conversation_run_coordinator import ConversationRunCoordinator


class FakeConversationRepo:
    def __init__(self, conversation):
        self.conversation = conversation
        self.update_name = AsyncMock()

    async def get_or_404(self, conversation_id):
        assert conversation_id == self.conversation.id
        return self.conversation


class FakeCanvasRepo:
    def __init__(self, canvas):
        self.canvas = canvas

    async def get_or_404(self, canvas_id):
        assert canvas_id == self.canvas.id
        return self.canvas


class FakeSession:
    def __init__(self):
        self.commit = AsyncMock()


@pytest.mark.asyncio
async def test_coordinator_renames_new_conversation_and_runs_targeted_agent():
    conversation_id = uuid.uuid4()
    canvas_id = uuid.uuid4()
    target_agent_id = uuid.uuid4()

    conversation = SimpleNamespace(
        id=conversation_id,
        canvas_id=canvas_id,
        name="New Conversation",
        messages=[],
    )
    canvas = SimpleNamespace(id=canvas_id)
    session = FakeSession()
    conv_repo = FakeConversationRepo(conversation)
    canvas_repo = FakeCanvasRepo(canvas)

    runner = SimpleNamespace(
        generate_conversation_title=AsyncMock(return_value="Math Help"),
        run=AsyncMock(),
        _conversation=SimpleNamespace(persist_message=AsyncMock()),
    )
    runner_factory = AsyncMock(return_value=runner)
    send_event = AsyncMock()

    coordinator = ConversationRunCoordinator(
        session=session,
        conversation_repo=conv_repo,
        canvas_repo=canvas_repo,
        runner_factory=runner_factory,
    )

    await coordinator.run(
        conversation_id=conversation_id,
        user_prompt="what is 2 + 2?",
        send_event=send_event,
        target_agent_id=target_agent_id,
    )

    runner_factory.assert_awaited_once_with(
        canvas=canvas,
        conversation_repo=conv_repo,
        conversation_id=conversation_id,
    )
    conv_repo.update_name.assert_awaited_once_with(conversation_id, "Math Help")
    send_event.assert_any_await(
        {
            "type": "conversation_renamed",
            "conversation_id": str(conversation_id),
            "name": "Math Help",
        }
    )
    runner.run.assert_awaited_once_with(
        "what is 2 + 2?",
        send_event,
        target_agent_id=target_agent_id,
        get_client_response=None,
    )
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_coordinator_persists_runner_errors_and_emits_final_answer_event():
    conversation_id = uuid.uuid4()
    canvas_id = uuid.uuid4()
    master_agent_id = uuid.uuid4()
    failure = RuntimeError("runner exploded")

    conversation = SimpleNamespace(
        id=conversation_id,
        canvas_id=canvas_id,
        name="Existing Conversation",
        messages=[object()],
    )
    canvas = SimpleNamespace(
        id=canvas_id,
        agent_nodes=[SimpleNamespace(id=master_agent_id, name="Master")],
    )
    session = FakeSession()
    conv_repo = FakeConversationRepo(conversation)
    canvas_repo = FakeCanvasRepo(canvas)

    persist_message = AsyncMock()
    runner = SimpleNamespace(
        generate_conversation_title=AsyncMock(),
        run=AsyncMock(side_effect=failure),
        _conversation=SimpleNamespace(persist_message=persist_message),
    )
    runner_factory = AsyncMock(return_value=runner)
    send_event = AsyncMock()

    coordinator = ConversationRunCoordinator(
        session=session,
        conversation_repo=conv_repo,
        canvas_repo=canvas_repo,
        runner_factory=runner_factory,
    )

    await coordinator.run(
        conversation_id=conversation_id,
        user_prompt="boom",
        send_event=send_event,
    )

    persist_message.assert_awaited_once_with(
        role="assistant",
        content="runner exploded",
        agent_name="Master",
        node_id=str(master_agent_id),
        event_type="final_answer",
    )
    send_event.assert_any_await(
        {
            "type": "final_answer",
            "content": "runner exploded",
            "agent": "Master",
            "node_id": str(master_agent_id),
        }
    )
    assert session.commit.await_count == 2
