"""Workspace-global registry of external MCP servers (multi-row) — #129.

Borrows ``provider_settings`` conventions for secrets (plaintext at the same
trust level as the .env it replaces, ``*_set`` redaction at the API layer —
never the raw value), without the singleton-row shape: this table holds one
row per registered server.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from canvas_server.database import Base


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Display name; unique enough for pickers, not DB-constrained.
    name: Mapped[str] = mapped_column(String(255))
    # Endpoint URL; validated http(s):// on every write path (spec §5.1).
    url: Mapped[str] = mapped_column(String(2083))
    # Header carrying the credential (e.g. "Authorization"); default per #120.
    credential_header: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="Authorization"
    )
    # Header value (e.g. "Bearer sk-…"); DB-only, never returned by the API.
    credential_value: Mapped[str | None] = mapped_column(Text, nullable=True)
