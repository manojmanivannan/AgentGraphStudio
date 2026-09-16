import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from canvas_server.config import settings
from canvas_server.events import EventPayload
from canvas_server.exceptions import AttachmentTooLargeError, ConversationNotFoundError
from canvas_server.models.canvas import AttachmentInstance, Conversation, Message


class ConversationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    def _eager_query(self):
        return select(Conversation).options(
            selectinload(Conversation.messages),
            selectinload(Conversation.canvas),
        )

    async def create(
        self,
        canvas_id: uuid.UUID,
        name: str = "New Conversation",
    ) -> Conversation:
        conv = Conversation(
            canvas_id=canvas_id,
            name=name,
            status="active",
        )
        self.session.add(conv)
        await self.session.commit()
        result = await self.session.execute(
            self._eager_query().where(Conversation.id == conv.id)
        )
        return result.scalar_one()

    async def list_for_canvas(self, canvas_id: uuid.UUID) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.canvas_id == canvas_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        result = await self.session.execute(
            self._eager_query().where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def get_or_404(self, conversation_id: uuid.UUID) -> Conversation:
        conv = await self.get(conversation_id)
        if not conv:
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")
        return conv

    async def delete(self, conversation_id: uuid.UUID) -> bool:
        conv = await self.get(conversation_id)
        if not conv:
            return False
        await self.session.delete(conv)
        await self.session.commit()
        return True

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        agent_name: str | None = None,
        node_id: uuid.UUID | None = None,
        event_type: str | None = None,
        tool: str | None = None,
        args: EventPayload | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            agent_name=agent_name,
            node_id=node_id,
            event_type=event_type,
            tool=tool,
            args=args,
        )
        self.session.add(msg)
        await self.session.flush()

        conv_result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.now(UTC)

        return msg

    async def complete_conversation(self, conversation_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.status = "completed"
            conv.updated_at = datetime.now(UTC)
            await self.session.flush()

    async def update_name(self, conversation_id: uuid.UUID, name: str) -> Conversation:
        conv = await self.get_or_404(conversation_id)
        conv.name = name
        conv.updated_at = datetime.now(UTC)
        await self.session.flush()
        return conv

    async def save_attachment(
        self,
        conversation_id: uuid.UUID,
        content: bytes,
        format: str = "png",
        file_type: str = "image",
        source: str = "agent_output",
        attachment_node_id: uuid.UUID | None = None,
        produced_by_run_id: uuid.UUID | None = None,
    ) -> AttachmentInstance:
        size_bytes = len(content)
        if size_bytes > settings.max_attachment_size_bytes:
            raise AttachmentTooLargeError(
                f"Attachment content is {size_bytes} bytes, which exceeds the "
                f"{settings.max_attachment_size_bytes} byte limit."
            )

        attachment = AttachmentInstance(
            conversation_id=conversation_id,
            content=content,
            size_bytes=size_bytes,
            format=format,
            file_type=file_type,
            source=source,
            attachment_node_id=attachment_node_id,
            produced_by_run_id=produced_by_run_id,
        )
        self.session.add(attachment)
        await self.session.flush()

        conv_result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.now(UTC)

        await self.session.commit()
        return attachment

    async def get_attachment(self, attachment_id: uuid.UUID) -> AttachmentInstance | None:
        result = await self.session.execute(
            select(AttachmentInstance)
            .options(
                selectinload(AttachmentInstance.conversation).selectinload(
                    Conversation.canvas
                )
            )
            .where(AttachmentInstance.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def get_unconsumed_input_attachments(
        self, conversation_id: uuid.UUID, node_ids: list[uuid.UUID]
    ) -> list[AttachmentInstance]:
        """Chat-uploaded input attachments not yet delivered to their agent (#88).

        Scoped to ``source="chat_upload"`` (never an ``agent_output`` row) and
        to the given declared input Attachment node ids, so a call site only
        ever sees attachments actually wired as inputs to the agent it is
        about to run. Ordered by ``created_at`` so a run delivers uploads in
        upload order.
        """
        if not node_ids:
            return []
        result = await self.session.execute(
            select(AttachmentInstance)
            .where(
                AttachmentInstance.conversation_id == conversation_id,
                AttachmentInstance.source == "chat_upload",
                AttachmentInstance.attachment_node_id.in_(node_ids),
                AttachmentInstance.consumed_at.is_(None),
            )
            .order_by(AttachmentInstance.created_at)
        )
        return list(result.scalars().all())

    async def mark_attachment_consumed(self, attachment_id: uuid.UUID) -> None:
        """Marks an input ``AttachmentInstance`` as delivered (#88).

        Idempotent and best-effort: a missing row is simply a no-op (the
        caller never needs to branch on whether the mark "took").
        """
        result = await self.session.execute(
            select(AttachmentInstance).where(AttachmentInstance.id == attachment_id)
        )
        attachment = result.scalar_one_or_none()
        if attachment is None:
            return
        attachment.consumed_at = datetime.now(UTC)
        await self.session.commit()

