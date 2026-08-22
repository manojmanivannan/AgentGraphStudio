import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from canvas_server.exceptions import CanvasNotFoundError
from canvas_server.models.api import (
    AgentDocumentInput,
    AgentNodeInput,
    EdgeInput,
    ToolNodeInput,
)
from canvas_server.models.canvas import AgentDocument, AgentNode, Canvas, Edge, ToolNode

logger = logging.getLogger("canvas_server.repo")


class CanvasRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _eager_query(self):
        return select(Canvas).options(
            selectinload(Canvas.agent_nodes).selectinload(AgentNode.documents),
            selectinload(Canvas.tool_nodes),
            selectinload(Canvas.edges),
        )

    async def create(self, name: str = "Untitled Canvas", *, owner_id: uuid.UUID) -> Canvas:
        canvas = Canvas(name=name, owner_id=owner_id)
        self.session.add(canvas)
        await self.session.commit()
        result = await self.session.execute(
            self._eager_query().where(Canvas.id == canvas.id)
        )
        return result.scalar_one()

    async def create_full(
        self,
        name: str,
        agents: list[AgentNodeInput],
        tools: list[ToolNodeInput],
        edges: list[EdgeInput],
        documents: list[AgentDocumentInput] | None = None,
        *,
        owner_id: uuid.UUID,
    ) -> Canvas:
        canvas = Canvas(name=name, owner_id=owner_id)
        self.session.add(canvas)
        await self.session.flush()

        canvas_id = canvas.id
        id_map = {}

        for a in agents:
            new_id = uuid.uuid4()
            id_map[a.id] = new_id
            node = AgentNode(
                id=new_id,
                canvas_id=canvas_id,
                name=a.name,
                role=a.role,
                instructions=a.instructions,
                model_name=a.model_name,
                agent_type=a.agent_type,
                enable_plotting=a.enable_plotting,
                enable_coding=a.enable_coding,
                enable_network=a.enable_network,
                enable_hitl=a.enable_hitl,
                enable_memory=a.enable_memory,
                enable_conversation_history=a.enable_conversation_history,
                enable_rag=a.enable_rag,
                rag_chunk_size=a.rag_chunk_size,
                is_entry_point=a.is_entry_point,
                position_x=a.position_x,
                position_y=a.position_y,
            )
            self.session.add(node)

        for t in tools:
            new_id = uuid.uuid4()
            id_map[t.id] = new_id
            node = ToolNode(
                id=new_id,
                canvas_id=canvas_id,
                name=t.name,
                code=t.code,
                dependencies=(
                    t.dependencies
                    if t.dependencies
                    else (t.packages.split(",") if t.packages else [])
                ),
                args=t.args,
                requires_approval=t.requires_approval,
                position_x=t.position_x,
                position_y=t.position_y,
            )
            self.session.add(node)

        for e in edges:
            # Map source and target IDs to their new versions
            source_id = id_map.get(e.source_node_id, e.source_node_id)
            target_id = id_map.get(e.target_node_id, e.target_node_id)

            edge = Edge(
                id=uuid.uuid4(),
                canvas_id=canvas_id,
                source_node_id=source_id,
                target_node_id=target_id,
                edge_type=e.edge_type,
            )
            self.session.add(edge)

        for d in documents or []:
            target_agent_id = id_map.get(d.agent_node_id)
            if target_agent_id is None:
                continue
            if d.content is None:
                logger.warning(
                    f"Document '{d.name}' (id={d.id}) has no content. Skipping document import."
                )
                continue
            doc = AgentDocument(
                id=uuid.uuid4(),
                canvas_id=canvas_id,
                agent_node_id=target_agent_id,
                name=d.name,
                content=d.content,
            )
            if d.created_at is not None:
                doc.created_at = d.created_at
            self.session.add(doc)

        await self.session.commit()

        result = await self.session.execute(
            self._eager_query().where(Canvas.id == canvas_id)
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

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Canvas]:
        """Return only the canvases owned by ``owner_id``, newest-updated first."""
        result = await self.session.execute(
            select(Canvas)
            .where(Canvas.owner_id == owner_id)
            .order_by(Canvas.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_owner(
        self, canvas_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Canvas | None:
        """Return the canvas iff it exists AND is owned by ``owner_id``.

        Used by every protected canvas route to enforce per-user isolation:
        a missing canvas and a foreign canvas are indistinguishable (404).
        """
        result = await self.session.execute(
            self._eager_query().where(
                Canvas.id == canvas_id, Canvas.owner_id == owner_id
            )
        )
        return result.scalar_one_or_none()

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
        canvas.updated_at = datetime.now(UTC)

        await self.session.execute(delete(Edge).where(Edge.canvas_id == canvas_id))
        await self.session.execute(
            delete(ToolNode).where(ToolNode.canvas_id == canvas_id)
        )

        existing_agents = {n.id: n for n in canvas.agent_nodes}
        new_agent_ids = {a.id for a in agents}

        # Delete agent nodes that are no longer present on the canvas
        for eid, node in list(existing_agents.items()):
            if eid not in new_agent_ids:
                await self.session.delete(node)

        # Delta sync (upsert) the rest of the agent nodes
        agents_to_reindex = []
        for a in agents:
            if a.id in existing_agents:
                node = existing_agents[a.id]
                size_changed = node.rag_chunk_size != a.rag_chunk_size
                rag_toggled_on = (not node.enable_rag) and a.enable_rag
                if size_changed or rag_toggled_on:
                    agents_to_reindex.append(a.id)

                node.name = a.name
                node.role = a.role
                node.instructions = a.instructions
                node.model_name = a.model_name
                node.agent_type = a.agent_type
                node.enable_plotting = a.enable_plotting
                node.enable_coding = a.enable_coding
                node.enable_network = a.enable_network
                node.enable_hitl = a.enable_hitl
                node.enable_memory = a.enable_memory
                node.enable_conversation_history = a.enable_conversation_history
                node.enable_rag = a.enable_rag
                node.rag_chunk_size = a.rag_chunk_size
                node.is_entry_point = a.is_entry_point
                node.position_x = a.position_x
                node.position_y = a.position_y
            else:
                if a.enable_rag:
                    agents_to_reindex.append(a.id)
                node = AgentNode(
                    id=a.id,
                    canvas_id=canvas_id,
                    name=a.name,
                    role=a.role,
                    instructions=a.instructions,
                    model_name=a.model_name,
                    agent_type=a.agent_type,
                    enable_plotting=a.enable_plotting,
                    enable_coding=a.enable_coding,
                    enable_network=a.enable_network,
                    enable_hitl=a.enable_hitl,
                    enable_memory=a.enable_memory,
                    enable_conversation_history=a.enable_conversation_history,
                    enable_rag=a.enable_rag,
                    rag_chunk_size=a.rag_chunk_size,
                    is_entry_point=a.is_entry_point,
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
                dependencies=(
                    t.dependencies
                    if t.dependencies
                    else (t.packages.split(",") if t.packages else [])
                ),
                requires_approval=t.requires_approval,
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

        if agents_to_reindex:
            from canvas_server.runner.rag_helper import RAGIndexManager

            for aid in agents_to_reindex:
                await RAGIndexManager.trigger_reindex(aid)

        self.session.expunge_all()

        result = await self.session.execute(
            self._eager_query().where(Canvas.id == canvas_id)
        )
        return result.scalar_one()
