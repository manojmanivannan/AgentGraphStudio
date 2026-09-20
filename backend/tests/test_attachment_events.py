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

from canvas_server.runner.attachment_events import (
    announce_attachment_consumed,
    announce_attachment_produced,
)


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
        original_filename="report_abc123.txt",
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
        "original_filename": "report_abc123.txt",
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
            "original_filename": "report_abc123.txt",
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


@pytest.mark.asyncio
async def test_announce_attachment_consumed_fires_event_and_persists_message():
    send_event = AsyncMock()
    conversation_service = AsyncMock()
    agent_id = uuid.uuid4()
    attachment_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()

    await announce_attachment_consumed(
        send_event=send_event,
        conversation_service=conversation_service,
        agent_name="Analyst",
        agent_id=agent_id,
        attachment_id=attachment_id,
        name="Report",
        file_type="csv",
        source="chat_upload",
        delivery_method="file_path",
        conversation_id=conversation_id,
        run_id=run_id,
    )

    send_event.assert_awaited_once()
    payload = send_event.await_args.args[0]
    assert payload == {
        "type": "attachment_consumed",
        "attachment_id": str(attachment_id),
        "name": "Report",
        "file_type": "csv",
        "source": "chat_upload",
        "delivery_method": "file_path",
        "conversation_id": str(conversation_id),
        "run_id": str(run_id),
        "agent": "Analyst",
        "node_id": str(agent_id),
        "original_filename": None,
    }

    conversation_service.persist_message.assert_awaited_once_with(
        role="assistant",
        content="",
        agent_name="Analyst",
        node_id=agent_id,
        event_type="attachment_consumed",
        args={
            "attachment_id": str(attachment_id),
            "name": "Report",
            "file_type": "csv",
            "source": "chat_upload",
            "delivery_method": "file_path",
            "run_id": str(run_id),
            "original_filename": None,
        },
    )


@pytest.mark.asyncio
async def test_announce_attachment_consumed_handles_missing_run_id():
    send_event = AsyncMock()
    conversation_service = AsyncMock()

    await announce_attachment_consumed(
        send_event=send_event,
        conversation_service=conversation_service,
        agent_name="Analyst",
        agent_id=uuid.uuid4(),
        attachment_id=uuid.uuid4(),
        name="Report",
        file_type="csv",
        source="chat_upload",
        delivery_method="inline",
        conversation_id=uuid.uuid4(),
        run_id=None,
    )

    payload = send_event.await_args.args[0]
    assert payload["run_id"] is None
    persisted_args = conversation_service.persist_message.await_args.kwargs["args"]
    assert persisted_args["run_id"] is None


@pytest.mark.asyncio
async def test_announce_attachment_consumed_includes_original_filename_when_provided():
    send_event = AsyncMock()
    conversation_service = AsyncMock()

    await announce_attachment_consumed(
        send_event=send_event,
        conversation_service=conversation_service,
        agent_name="Analyst",
        agent_id=uuid.uuid4(),
        attachment_id=uuid.uuid4(),
        name="CityName",
        file_type="json",
        source="chat_upload",
        delivery_method="file_path",
        conversation_id=uuid.uuid4(),
        run_id=None,
        original_filename="city_name.json",
    )

    payload = send_event.await_args.args[0]
    assert payload["original_filename"] == "city_name.json"
    persisted_args = conversation_service.persist_message.await_args.kwargs["args"]
    assert persisted_args["original_filename"] == "city_name.json"


@pytest.mark.asyncio
async def test_announce_attachment_consumed_is_a_noop_without_callbacks():
    """Never raises when send_event/conversation_service aren't wired (defensive)."""
    await announce_attachment_consumed(
        send_event=None,
        conversation_service=None,
        agent_name="Analyst",
        agent_id=uuid.uuid4(),
        attachment_id=uuid.uuid4(),
        name="Report",
        file_type="csv",
        source="chat_upload",
        delivery_method="manifest_only",
        conversation_id=uuid.uuid4(),
        run_id=None,
    )
