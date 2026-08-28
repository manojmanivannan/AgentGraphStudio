"""App-managed LLM provider configuration (single global row)."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from canvas_server.database import Base

# The table holds at most one row; this is its fixed primary key.
SINGLETON_ID = 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProviderSettings(Base):
    __tablename__ = "provider_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    profile: Mapped[str] = mapped_column(String(64), default="custom")
    llm_provider_type: Mapped[str] = mapped_column(String(64), default="ollama")
    llm_base_url: Mapped[str] = mapped_column(String(512), default="")
    # Stored in plaintext at the same trust level as the .env it replaces.
    llm_api_key: Mapped[str] = mapped_column(String(512), default="")
    llm_model: Mapped[str] = mapped_column(String(255), default="")
    mem0_llm_model: Mapped[str] = mapped_column(String(255), default="")
    mem0_embedder_model: Mapped[str] = mapped_column(String(255), default="")
    mem0_embedder_dimensions: Mapped[int] = mapped_column(sa.Integer, default=768)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )
