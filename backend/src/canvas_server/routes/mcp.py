"""MCP server registry routes (Settings → MCP Servers, ticket #129).

CRUD over the workspace-global ``mcp_servers`` table. The credential value is
never returned (§3.1); URL writes follow the http(s)-only policy (§5.1). The
process-local registry cache is refreshed after every write so the runner/probe
read fresh state without re-querying the database (provider-settings
convention). The connection probe (``POST /api/mcp/servers/test``) is ticket
#131, not this file.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.auth import get_current_user, verify_origin
from canvas_server.database import get_session
from canvas_server.mcp_config import refresh_mcp_servers
from canvas_server.mcp_url_policy import validate_mcp_server_url
from canvas_server.models.api import (
    McpServerCreate,
    McpServerListResponse,
    McpServerResponse,
    McpServerUpdate,
)
from canvas_server.models.auth import User
from canvas_server.repos.mcp_repo import McpServerRepo

mcp_router = APIRouter(prefix="/api/mcp/servers", tags=["mcp"])

# Masked-credential preview: fixed-width bullets plus a short, useless tail
# — only when the value is long enough that the tail reveals a small fraction.
_PREVIEW_TAIL_CHARS = 4
_MIN_LEN_FOR_TAIL = 12
_FIXED_MASK = "•" * 8


def _mask_credential(value: str | None) -> str | None:
    """A masked preview: bullets plus at most the last 4 characters.

    The mask is fixed-width so the response does not leak the exact length,
    and short credentials (< 12 chars) are fully bullet-masked.
    """
    if not value:
        return None
    if len(value) < _MIN_LEN_FOR_TAIL:
        return _FIXED_MASK
    return _FIXED_MASK + value[-_PREVIEW_TAIL_CHARS:]


def _to_response(row) -> McpServerResponse:
    return McpServerResponse(
        id=row.id,
        name=row.name,
        url=row.url,
        credential_header=row.credential_header,
        credential_set=bool(row.credential_value),
        credential_preview=_mask_credential(row.credential_value),
        url_warning=validate_mcp_server_url(row.url).warning,
    )


def _validated_url_or_400(url: str) -> str:
    check = validate_mcp_server_url(url)
    if not check.ok:
        raise HTTPException(status_code=400, detail=check.error)
    return url


async def _get_row_or_404(session: AsyncSession, server_id: uuid.UUID):
    row = await McpServerRepo(session).get(server_id)
    if row is None:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    return row


@mcp_router.get("", response_model=McpServerListResponse)
async def list_mcp_servers(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> McpServerListResponse:
    rows = await McpServerRepo(session).list()
    return McpServerListResponse(servers=[_to_response(row) for row in rows])


@mcp_router.post("", response_model=McpServerResponse, status_code=201)
async def create_mcp_server(
    body: McpServerCreate,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
    _origin: None = Depends(verify_origin),
) -> McpServerResponse:
    _validated_url_or_400(body.url)
    row = await McpServerRepo(session).create(
        name=body.name,
        url=body.url,
        credential_header=body.credential_header if body.credential_header else None,
        credential_value=body.credential_value,
    )
    await session.commit()
    await refresh_mcp_servers(session)
    return _to_response(row)


@mcp_router.put("/{server_id}", response_model=McpServerResponse)
async def update_mcp_server(
    server_id: uuid.UUID,
    body: McpServerUpdate,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
    _origin: None = Depends(verify_origin),
) -> McpServerResponse:
    row = await _get_row_or_404(session, server_id)
    _validated_url_or_400(body.url)
    await McpServerRepo(session).update(
        row,
        name=body.name,
        url=body.url,
        credential_header=body.credential_header,
        # None keeps the stored credential; "" clears it (§3.1).
        credential_value=body.credential_value,
    )
    await session.commit()
    await refresh_mcp_servers(session)
    return _to_response(row)


@mcp_router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
    _origin: None = Depends(verify_origin),
) -> None:
    row = await _get_row_or_404(session, server_id)
    await McpServerRepo(session).delete(row)
    await session.commit()
    await refresh_mcp_servers(session)
