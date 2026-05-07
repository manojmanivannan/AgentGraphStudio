import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Double, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from canvas_server.database import Base


class Canvas(Base):
    __tablename__ = "canvases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), default="Untitled Canvas")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent_nodes = relationship("AgentNode", back_populates="canvas", cascade="all, delete-orphan")
    tool_nodes = relationship("ToolNode", back_populates="canvas", cascade="all, delete-orphan")
    edges = relationship("Edge", back_populates="canvas", cascade="all, delete-orphan")


class AgentNode(Base):
    __tablename__ = "agent_nodes"
    __table_args__ = (Index("idx_agent_nodes_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canvases.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), default="Agent")
    role: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(255), default="ollama:llama3.1")
    position_x: Mapped[float] = mapped_column(Double, default=0)
    position_y: Mapped[float] = mapped_column(Double, default=0)

    canvas = relationship("Canvas", back_populates="agent_nodes")


class ToolNode(Base):
    __tablename__ = "tool_nodes"
    __table_args__ = (Index("idx_tool_nodes_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canvases.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), default="Tool")
    code: Mapped[str] = mapped_column(Text, default="")
    position_x: Mapped[float] = mapped_column(Double, default=0)
    position_y: Mapped[float] = mapped_column(Double, default=0)

    canvas = relationship("Canvas", back_populates="tool_nodes")


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (Index("idx_edges_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canvases.id", ondelete="CASCADE")
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    edge_type: Mapped[str] = mapped_column(
        Enum("tool_access", "handoff", name="edge_type_enum"),
    )

    canvas = relationship("Canvas", back_populates="edges")
