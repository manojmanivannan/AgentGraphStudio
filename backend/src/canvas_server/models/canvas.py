from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Double, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

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
    conversations: Mapped[list[Conversation]] = relationship(
        "Conversation", back_populates="canvas", cascade="all, delete-orphan",
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
    enable_memory: Mapped[bool] = mapped_column(sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False)
    enable_conversation_history: Mapped[bool] = mapped_column(sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False)
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
    args: Mapped[list] = mapped_column(JSON, default=[])
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


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("idx_conversations_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255), default="New Conversation")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("idx_messages_conversation", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"),
    )
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text, default="")
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, default=None)
    event_type: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")
