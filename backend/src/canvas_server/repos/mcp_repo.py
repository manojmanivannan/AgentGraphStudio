"""CRUD access to the workspace-global ``mcp_servers`` registry (#129)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.models.mcp import McpServer


class McpServerRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[McpServer]:
        rows = await self._session.execute(
            select(McpServer).order_by(McpServer.name)
        )
        return list(rows.scalars().all())

    async def get(self, server_id: uuid.UUID) -> McpServer | None:
        return await self._session.get(McpServer, server_id)

    async def create(
        self,
        name: str,
        url: str,
        credential_header: str | None = "Authorization",
        credential_value: str | None = None,
    ) -> McpServer:
        row = McpServer(
            name=name,
            url=url,
            credential_header=credential_header,
            # An empty credential on create means "no credential stored".
            credential_value=credential_value or None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        row: McpServer,
        name: str | None = None,
        url: str | None = None,
        credential_header: str | None = None,
        credential_value: str | None = None,
    ) -> McpServer:
        """Partially update a server; ``None`` keeps the stored value.

        The credential follows the provider-settings convention (§3.1):
        ``None`` keeps the stored credential, ``""`` clears it.
        """
        if name is not None:
            row.name = name
        if url is not None:
            row.url = url
        if credential_header is not None:
            row.credential_header = credential_header or None
        if credential_value is not None:
            row.credential_value = credential_value or None
        await self._session.flush()
        return row

    async def delete(self, row: McpServer) -> None:
        await self._session.delete(row)
        await self._session.flush()
