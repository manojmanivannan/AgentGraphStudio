"""Shared "attachment produced"/"attachment consumed" announcements (#86/#87/#88).

Once an ``AttachmentInstance`` has been stored (via
``ConversationRepo.save_attachment``), it needs to be announced to the
client over the WebSocket and durably persisted to conversation history so
it survives a page reload. ``announce_attachment_produced`` is the single
announcement path for *any* produced attachment — whether it came from the
post-loop output-extraction mechanism (#86, ``runner/execution.py``) or the
mid-loop ``generate_plot`` tool (#87, ``runner/plot_provider.py``) — so there
is only one code path for "an agent produced an attachment," not two
parallel ones. ``announce_attachment_consumed`` mirrors it for the input
side (#88): once ``runner/input_attachment_delivery.py`` has resolved and
delivered a declared input attachment to a consuming agent.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from canvas_server.events import EventCallback
    from canvas_server.runner.conversation import ConversationService


async def announce_attachment_consumed(
    *,
    send_event: EventCallback | None,
    conversation_service: ConversationService | None,
    agent_name: str,
    agent_id: uuid.UUID,
    attachment_id: uuid.UUID,
    name: str,
    file_type: str,
    source: str,
    delivery_method: str,
    conversation_id: uuid.UUID | str,
    run_id: uuid.UUID | None,
    original_filename: str | None = None,
) -> None:
    """Fires the ``attachment_consumed`` WS event and persists a durable message (#88).

    Mirrors :func:`announce_attachment_produced`'s shape exactly — the only
    difference is ``delivery_method`` (the *resolved* delivery: ``"inline"``,
    ``"file_path"``, ``"dual"``, or ``"manifest_only"``) in place of
    ``source``. Never raises: both callbacks are optional and simply skipped
    when absent.

    Args:
        send_event: Async callback to stream the event over the websocket, if any.
        conversation_service: Service used to durably persist the message, if any.
        agent_name: Display name of the consuming agent.
        agent_id: The consuming agent's node id.
        attachment_id: The id of the consumed ``AttachmentInstance``.
        name: The declared input Attachment node's name.
        file_type: The attachment's declared file type (e.g. ``"csv"``).
        source: Whether the attachment originated as a chat upload or agent output.
        delivery_method: The resolved delivery method for this attachment.
        conversation_id: The conversation the attachment belongs to.
        run_id: The durable run consuming this attachment, if any.
        original_filename: The filename the user actually uploaded it under
            (#90), distinct from ``name`` (the node's own canvas label).
            ``None`` for agent-produced attachments, which were never uploaded.
    """
    run_id_str = str(run_id) if run_id else None

    if send_event:
        await send_event(
            {
                "type": "attachment_consumed",
                "attachment_id": str(attachment_id),
                "name": name,
                "file_type": file_type,
                "source": source,
                "delivery_method": delivery_method,
                "conversation_id": str(conversation_id),
                "run_id": run_id_str,
                "agent": agent_name,
                "node_id": str(agent_id),
                "original_filename": original_filename,
            }
        )

    if conversation_service:
        await conversation_service.persist_message(
            role="assistant",
            content="",
            agent_name=agent_name,
            node_id=agent_id,
            event_type="attachment_consumed",
            args={
                "attachment_id": str(attachment_id),
                "name": name,
                "file_type": file_type,
                "source": source,
                "delivery_method": delivery_method,
                "run_id": run_id_str,
                "original_filename": original_filename,
            },
        )


async def announce_attachment_produced(
    *,
    send_event: EventCallback | None,
    conversation_service: ConversationService | None,
    agent_name: str,
    agent_id: uuid.UUID,
    attachment_id: uuid.UUID,
    name: str,
    file_type: str,
    source: str,
    conversation_id: uuid.UUID | str,
    run_id: uuid.UUID | None,
) -> None:
    """Fires the ``attachment_produced`` WS event and persists a durable message.

    Never raises: both ``send_event`` and ``conversation_service`` are
    optional and simply skipped when absent (e.g. outside a live run
    context), mirroring how the rest of the runner treats these ephemeral
    callbacks as best-effort.

    Args:
        send_event: Async callback to stream the event over the websocket, if any.
        conversation_service: Service used to durably persist the message, if any.
        agent_name: Display name of the producing agent.
        agent_id: The producing agent's node id.
        attachment_id: The id of the just-stored ``AttachmentInstance``.
        name: A human-readable label for the attachment (a declared output
            Attachment node's name, or a synthesized one like ``"plot"``).
        file_type: The attachment's declared/inferred file type (e.g. ``"image"``).
        source: Either ``"agent_output"`` or ``"chat_upload"``.
        conversation_id: The conversation the attachment belongs to.
        run_id: The durable run that produced this attachment, if any.
    """
    run_id_str = str(run_id) if run_id else None

    if send_event:
        await send_event(
            {
                "type": "attachment_produced",
                "attachment_id": str(attachment_id),
                "name": name,
                "file_type": file_type,
                "source": source,
                "conversation_id": str(conversation_id),
                "run_id": run_id_str,
                "agent": agent_name,
                "node_id": str(agent_id),
            }
        )

    if conversation_service:
        await conversation_service.persist_message(
            role="assistant",
            content="",
            agent_name=agent_name,
            node_id=agent_id,
            event_type="attachment_produced",
            args={
                "attachment_id": str(attachment_id),
                "name": name,
                "file_type": file_type,
                "source": source,
                "run_id": run_id_str,
            },
        )
