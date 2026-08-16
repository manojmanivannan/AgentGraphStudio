from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import (
    DateTime,
    Double,
    ForeignKey,
    Index,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from canvas_server.config import settings
from canvas_server.database import Base
from canvas_server.models.auth import User


def _utcnow():
    return datetime.now(UTC)


class Canvas(Base):
    __tablename__ = "canvases"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), default="Untitled Canvas")
    # Every canvas belongs to exactly one user; users see/touch only their own.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    owner: Mapped[User] = relationship(User)
    agent_nodes: Mapped[list[AgentNode]] = relationship(
        "AgentNode",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )
    tool_nodes: Mapped[list[ToolNode]] = relationship(
        "ToolNode",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list[Edge]] = relationship(
        "Edge",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )
    conversations: Mapped[list[Conversation]] = relationship(
        "Conversation",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )


class AgentNode(Base):
    __tablename__ = "agent_nodes"
    __table_args__ = (Index("idx_agent_nodes_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255), default="Agent")
    role: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(255), default="ollama:llama3.1")
    agent_type: Mapped[str] = mapped_column(String(20), default="worker")
    enable_plotting: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    enable_coding: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    # Reserved for a later ticket: enables network access inside the sandbox.
    # The column is added now (one migration with enable_coding) so future work
    # only flips behavior; it is not yet wired through the Pydantic model, repo,
    # routes, or frontend.
    enable_network: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    enable_hitl: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    enable_memory: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    enable_conversation_history: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    enable_rag: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    rag_chunk_size: Mapped[int] = mapped_column(
        sa.Integer(), default=1000, server_default=sa.text("1000"), nullable=False
    )
    is_entry_point: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )
    position_x: Mapped[float] = mapped_column(Double, default=0)
    position_y: Mapped[float] = mapped_column(Double, default=0)

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="agent_nodes")
    documents: Mapped[list[AgentDocument]] = relationship(
        "AgentDocument",
        back_populates="agent_node",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chunks: Mapped[list[AgentDocumentChunk]] = relationship(
        "AgentDocumentChunk",
        back_populates="agent_node",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AgentDocument(Base):
    __tablename__ = "agent_documents"
    __table_args__ = (
        Index("idx_agent_documents_canvas", "canvas_id"),
        Index("idx_agent_documents_agent", "agent_node_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    agent_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_nodes.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )

    agent_node: Mapped[AgentNode] = relationship(
        "AgentNode", back_populates="documents"
    )
    chunks: Mapped[list[AgentDocumentChunk]] = relationship(
        "AgentDocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]

    HAS_PGVECTOR = True
except ImportError:
    Vector = None  # type: ignore
    HAS_PGVECTOR = False


class SafeVector(TypeDecorator):
    impl = JSON
    cache_ok = True

    def __init__(self, dimensions=None):
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            if HAS_PGVECTOR and Vector is not None:
                return dialect.type_descriptor(Vector(self.dimensions))
            else:
                from sqlalchemy import Float
                from sqlalchemy.dialects.postgresql import ARRAY

                return dialect.type_descriptor(ARRAY(Float))
        return dialect.type_descriptor(sa.JSON())


class AgentDocumentChunk(Base):
    __tablename__ = "agent_document_chunks"
    __table_args__ = (
        Index("idx_agent_document_chunks_canvas", "canvas_id"),
        Index("idx_agent_document_chunks_agent", "agent_node_id"),
        Index("idx_agent_document_chunks_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    agent_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_nodes.id", ondelete="CASCADE"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_documents.id", ondelete="CASCADE"),
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(
        SafeVector(dimensions=settings.mem0_embedder_dimensions)
    )

    agent_node: Mapped[AgentNode] = relationship("AgentNode", back_populates="chunks")
    document: Mapped[AgentDocument] = relationship(
        "AgentDocument", back_populates="chunks"
    )


class ToolNode(Base):
    __tablename__ = "tool_nodes"
    __table_args__ = (Index("idx_tool_nodes_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255), default="Tool")
    code: Mapped[str] = mapped_column(Text, default="")
    dependencies: Mapped[list] = mapped_column(JSON, default=[])
    args: Mapped[list] = mapped_column(JSON, default=[])
    position_x: Mapped[float] = mapped_column(Double, default=0)
    position_y: Mapped[float] = mapped_column(Double, default=0)
    requires_approval: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, server_default=sa.text("false"), nullable=False
    )

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="tool_nodes")


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (Index("idx_edges_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    target_node_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    edge_type: Mapped[str] = mapped_column(String(20))

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="edges")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("idx_conversations_canvas", "canvas_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("canvases.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(255), default="New Conversation")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    canvas: Mapped[Canvas] = relationship("Canvas", back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    plots: Mapped[list[ConversationPlot]] = relationship(
        "ConversationPlot",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list[DurableRun]] = relationship(
        "DurableRun",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("idx_messages_conversation", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
    )
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text, default="")
    agent_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, default=None)
    event_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )

    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="messages"
    )


class ConversationPlot(Base):
    __tablename__ = "conversation_plots"
    __table_args__ = (Index("idx_conversation_plots_conversation", "conversation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
    )
    format: Mapped[str] = mapped_column(String(10), default="png")
    content: Mapped[bytes] = mapped_column(sa.LargeBinary)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )

    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="plots"
    )


class DurableRun(Base):
    __tablename__ = "durable_runs"
    __table_args__ = (
        Index("idx_durable_runs_conversation", "conversation_id"),
        Index("idx_durable_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
    )
    prompt: Mapped[str] = mapped_column(Text)
    target_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer(), default=0, server_default=sa.text("0"), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    replay_cursor: Mapped[int] = mapped_column(
        sa.Integer(), default=0, server_default=sa.text("0"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    final_result: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    final_error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="runs"
    )
    events: Mapped[list[DurableRunEvent]] = relationship(
        "DurableRunEvent",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DurableRunEvent.sequence",
    )


class DurableRunEvent(Base):
    __tablename__ = "durable_run_events"
    __table_args__ = (
        Index("idx_durable_run_events_run", "run_id"),
        UniqueConstraint("run_id", "sequence", name="uq_durable_run_events_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("durable_runs.id", ondelete="CASCADE"),
    )
    sequence: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    run: Mapped[DurableRun] = relationship("DurableRun", back_populates="events")

