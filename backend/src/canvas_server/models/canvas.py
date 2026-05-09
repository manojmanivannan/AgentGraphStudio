import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Double, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from canvas_server.database import Base


def _utcnow():
    return datetime.now(UTC)


class Canvas(Base):
    __tablename__ = "canvases"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), default="Untitled Canvas")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    agent_nodes: Mapped[list[AgentNode]] = relationship(
        "AgentNode", back_populates="canvas", cascade="all, delete-orphan",
    )
    tool_nodes: Mapped[list[ToolNode]] = relationship(
        "ToolNode", back_populates="canvas", cascade="all, delete-orphan",
    )
    edges: Mapped[list[Edge]] = relationship(
        "Edge", back_populates="canvas", cascade="all, delete-orphan",
    )


class AgentNode(Base):
    __tablename__ = "agent_nodes"
    __table_args__ = (Index("idx_agent_nodes_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255), default="Agent")
    role: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(255), default="ollama:llama3.1")
    agent_type: Mapped[str] = mapped_column(String(20), default="worker")
    position_x: Mapped[float] = mapped_column(Double, default=0)
    position_y: Mapped[float] = mapped_column(Double, default=0)

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="agent_nodes")


class ToolNode(Base):
    __tablename__ = "tool_nodes"
    __table_args__ = (Index("idx_tool_nodes_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255), default="Tool")
    code: Mapped[str] = mapped_column(Text, default="")
    position_x: Mapped[float] = mapped_column(Double, default=0)
    position_y: Mapped[float] = mapped_column(Double, default=0)

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="tool_nodes")


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (Index("idx_edges_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    target_node_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    edge_type: Mapped[str] = mapped_column(String(20))

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="edges")
