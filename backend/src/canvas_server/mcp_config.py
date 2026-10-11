"""Process-local cache of the ``mcp_servers`` registry (ticket #129).

Follows the ``provider_settings`` conventions: reads are synchronous (the
runner and the MCP probe sit deep inside execution call stacks), so the
resolved server list lives in a process-local cache that write routes refresh
explicitly via :func:`refresh_mcp_servers`. The cache exposes the *raw*
credential value — consumers are behind the authenticated API; redaction
happens only at the response layer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("canvas_server.mcp_config")


@dataclass(frozen=True)
class McpServerConfig:
    id: uuid.UUID
    name: str
    url: str
    credential_header: str | None
    credential_value: str | None


_cached: tuple[McpServerConfig, ...] = ()


def get_mcp_servers() -> tuple[McpServerConfig, ...]:
    return _cached


async def refresh_mcp_servers(session: AsyncSession) -> tuple[McpServerConfig, ...]:
    """Reload the process-local cache from the database."""
    global _cached
    from canvas_server.repos.mcp_repo import McpServerRepo

    rows = await McpServerRepo(session).list()
    _cached = tuple(
        McpServerConfig(
            id=row.id,
            name=row.name,
            url=row.url,
            credential_header=row.credential_header,
            credential_value=row.credential_value,
        )
        for row in rows
    )
    return _cached


def reset_mcp_servers_cache() -> None:
    global _cached
    _cached = ()
