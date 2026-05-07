import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from canvas_server.exceptions import CanvasNotFoundError
from canvas_server.models.api import AgentNodeInput, EdgeInput, ToolNodeInput
from canvas_server.models.canvas import AgentNode, Canvas, Edge, ToolNode

logger = logging.getLogger("canvas_server.repo")


class CanvasRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _eager_query(self):
        return (
            select(Canvas)
            .options(
                selectinload(Canvas.agent_nodes),
                selectinload(Canvas.tool_nodes),
                selectinload(Canvas.edges),
            )
        )

    async def create(self, name: str = "Untitled Canvas") -> Canvas:
        canvas = Canvas(name=name)
        self.session.add(canvas)
        await self.session.commit()
        result = await self.session.execute(
            self._eager_query().where(Canvas.id == canvas.id)
        )
        return result.scalar_one()

    async def get(self, canvas_id: uuid.UUID) -> Canvas | None:
        result = await self.session.execute(
            self._eager_query().where(Canvas.id == canvas_id)
        )
        return result.scalar_one_or_none()

    async def get_or_404(self, canvas_id: uuid.UUID) -> Canvas:
        canvas = await self.get(canvas_id)
        if not canvas:
            raise CanvasNotFoundError(f"Canvas {canvas_id} not found")
        return canvas

    async def list_all(self) -> list[Canvas]:
        result = await self.session.execute(
            select(Canvas).order_by(Canvas.updated_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, canvas_id: uuid.UUID) -> bool:
        canvas = await self.get(canvas_id)
        if not canvas:
            return False
        await self.session.delete(canvas)
        await self.session.commit()
        return True

    async def save_nodes_and_edges(
        self,
        canvas_id: uuid.UUID,
        name: str,
        agents: list[AgentNodeInput],
        tools: list[ToolNodeInput],
        edges: list[EdgeInput],
    ) -> Canvas:
        canvas = await self.get_or_404(canvas_id)
        canvas.name = name
        canvas.updated_at = datetime.now(timezone.utc)

        await self.session.execute(
            delete(Edge).where(Edge.canvas_id == canvas_id)
        )
        await self.session.execute(
            delete(AgentNode).where(AgentNode.canvas_id == canvas_id)
        )
        await self.session.execute(
            delete(ToolNode).where(ToolNode.canvas_id == canvas_id)
        )

        for a in agents:
            node = AgentNode(
                id=a.id,
                canvas_id=canvas_id,
                name=a.name,
                role=a.role,
                instructions=a.instructions,
                model_name=a.model_name,
                agent_type=a.agent_type,
                position_x=a.position_x,
                position_y=a.position_y,
            )
            self.session.add(node)

        for t in tools:
            node = ToolNode(
                id=t.id,
                canvas_id=canvas_id,
                name=t.name,
                code=t.code,
                position_x=t.position_x,
                position_y=t.position_y,
            )
            self.session.add(node)

        for e in edges:
            edge = Edge(
                id=e.id,
                canvas_id=canvas_id,
                source_node_id=e.source_node_id,
                target_node_id=e.target_node_id,
                edge_type=e.edge_type,
            )
            self.session.add(edge)

        await self.session.commit()

        return await self.get_or_404(canvas_id)
