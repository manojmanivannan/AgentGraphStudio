import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from canvas_server.exceptions import ConversationNotFoundError
from canvas_server.models.canvas import Conversation, Message, ConversationPlot



class ConversationRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _eager_query(self):
        return select(Conversation).options(selectinload(Conversation.messages))

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
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            agent_name=agent_name,
            node_id=node_id,
            event_type=event_type,
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

    async def save_plot(
        self,
        conversation_id: uuid.UUID,
        content: bytes,
        format: str = "png",
    ) -> ConversationPlot:
        plot = ConversationPlot(
            conversation_id=conversation_id,
            content=content,
            format=format,
        )
        self.session.add(plot)
        await self.session.flush()

        conv_result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.now(UTC)

        return plot

    async def get_plot(self, plot_id: uuid.UUID) -> ConversationPlot | None:
        result = await self.session.execute(
            select(ConversationPlot).where(ConversationPlot.id == plot_id)
        )
        return result.scalar_one_or_none()

