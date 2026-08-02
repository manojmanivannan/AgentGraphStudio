"""Authentication domain models: users and server-side sessions."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from canvas_server.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def new_session_id() -> str:
    """Opaque, url-safe session token used as the session primary key."""
    return secrets.token_urlsafe(32)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    # Normalized (lowercased, stripped) email used as the login handle.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    sessions: Mapped[list[Session]] = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Session(Base):
    __tablename__ = "sessions"

    # Opaque url-safe token (secrets.token_urlsafe(32)); string PK, not a UUID.
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_session_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Sliding idle timeout — extended on every protected-route hit.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Fixed-from-login absolute cap.
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )

    user: Mapped[User] = relationship("User", back_populates="sessions")
