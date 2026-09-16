"""Tests for the shared attachment-produced announcement helper (#87).

Both the post-loop output-extraction mechanism (#86) and the mid-loop
``generate_plot`` tool (#87) store an ``AttachmentInstance`` via the same
``ConversationRepo.save_attachment`` call and then announce it to the client
(WS event) and conversation history (persisted message) through this single
function — so there is only one code path for "an agent produced an
attachment," not two parallel ones.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from canvas_server.runner.attachment_events import announce_attachment_produced


@pytest.mark.asyncio
async def test_announce_attachment_produced_fires_event_and_persists_message():
    send_event = AsyncMock()
    conversation_service = AsyncMock()
    agent_id = uuid.uuid4()
    attachment_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()

    await announce_attachment_produced(
        send_event=send_event,
        conversation_service=conversation_service,
        agent_name="Reporter",
        agent_id=agent_id,
        attachment_id=attachment_id,
        name="report",
        file_type="text",
        source="agent_output",
        conversation_id=conversation_id,
        run_id=run_id,
    )

    send_event.assert_awaited_once()
    payload = send_event.await_args.args[0]
    assert payload == {
        "type": "attachment_produced",
        "attachment_id": str(attachment_id),
        "name": "report",
        "file_type": "text",
        "source": "agent_output",
        "conversation_id": str(conversation_id),
        "run_id": str(run_id),
        "agent": "Reporter",
        "node_id": str(agent_id),
    }

    conversation_service.persist_message.assert_awaited_once_with(
        role="assistant",
        content="",
        agent_name="Reporter",
        node_id=agent_id,
        event_type="attachment_produced",
        args={
            "attachment_id": str(attachment_id),
            "name": "report",
            "file_type": "text",
            "source": "agent_output",
            "run_id": str(run_id),
        },
    )


@pytest.mark.asyncio
async def test_announce_attachment_produced_handles_missing_run_id():
    send_event = AsyncMock()
    conversation_service = AsyncMock()
    agent_id = uuid.uuid4()
    attachment_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    await announce_attachment_produced(
        send_event=send_event,
        conversation_service=conversation_service,
        agent_name="Plotter",
        agent_id=agent_id,
        attachment_id=attachment_id,
        name="plot",
        file_type="image",
        source="agent_output",
        conversation_id=conversation_id,
        run_id=None,
    )

    payload = send_event.await_args.args[0]
    assert payload["run_id"] is None
    persisted_args = conversation_service.persist_message.await_args.kwargs["args"]
    assert persisted_args["run_id"] is None


@pytest.mark.asyncio
async def test_announce_attachment_produced_is_a_noop_without_callbacks():
    """Never raises when send_event/conversation_service aren't wired (defensive)."""
    await announce_attachment_produced(
        send_event=None,
        conversation_service=None,
        agent_name="Plotter",
        agent_id=uuid.uuid4(),
        attachment_id=uuid.uuid4(),
        name="plot",
        file_type="image",
        source="agent_output",
        conversation_id=uuid.uuid4(),
        run_id=None,
    )
