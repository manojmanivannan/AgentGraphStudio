"""HTTP layer shared helpers for the route modules."""

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.repos.mcp_repo import McpServerRepo


async def get_mcp_server_row_or_404(
    session: AsyncSession, server_id: uuid.UUID
):
    """Fetch the registered MCP server row, or raise 404 (both registry and
    tool-route modules resolve the same way — no per-module copies)."""
    row = await McpServerRepo(session).get(server_id)
    if row is None:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    return row
