"""MCP server registry routes (Settings → MCP Servers, tickets #129/#131).

CRUD over the workspace-global ``mcp_servers`` table. The credential value is
never returned (#129 responses, §3.1); URL writes follow the http(s)-only
policy (§5.1). The process-local registry cache is refreshed after every write
so the runner/probe read fresh state without re-querying the database
(provider-settings convention). The connection probe
(``POST /api/mcp/servers/test``, #131) reads stored registrations from the
same cache and never echoes the credential (§5.4).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.auth import get_current_user, verify_origin
from canvas_server.database import get_session
from canvas_server.mcp_config import get_mcp_servers, refresh_mcp_servers
from canvas_server.mcp_probe import fetch_mcp_catalog, probe_mcp_server
from canvas_server.mcp_url_policy import validate_mcp_server_url
from canvas_server.models.api import (
    McpCatalogTool,
    McpServerCatalogResponse,
    McpServerCreate,
    McpServerListResponse,
    McpServerResponse,
    McpServerTestRequest,
    McpServerTestResponse,
    McpServerUpdate,
)
from canvas_server.models.auth import User
from canvas_server.repos.mcp_repo import McpServerRepo
from canvas_server.routes import get_mcp_server_row_or_404

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
    row = await get_mcp_server_row_or_404(session, server_id)
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
    row = await get_mcp_server_row_or_404(session, server_id)
    # Deletion guard (#132): a server still granted by any Tool Node stays.
    referencing = await McpServerRepo(session).list_referencing_canvases(server_id)
    if referencing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "This MCP server is still referenced by tool nodes in "
                    f"{len(referencing)} canvas(es). Remove those tool nodes' "
                    "server grants before deleting the server."
                ),
                "referencing_canvases": [
                    {"id": str(canvas.id), "name": canvas.name}
                    for canvas in referencing
                ],
            },
        )
    await McpServerRepo(session).delete(row)
    await session.commit()
    await refresh_mcp_servers(session)


@mcp_router.post("/test", response_model=McpServerTestResponse)
async def test_mcp_server(
    body: McpServerTestRequest,
    _user: User = Depends(get_current_user),
    _origin: None = Depends(verify_origin),
) -> McpServerTestResponse:
    """Connection probe for the Settings Test button (#131).

    Mirrors the provider Test-button convention: the request body carries the
    unsaved-form values; omitted fields fall back to the stored registration
    (read from the process-local cache, no DB session). The response never
    contains the credential — only connection facts (§5.4).
    """
    stored = None
    if body.server_id is not None:
        stored = next(
            (s for s in get_mcp_servers() if s.id == body.server_id), None
        )
        if stored is None:
            raise HTTPException(status_code=404, detail="MCP server not found.")

    url = body.url or (stored.url if stored else None)
    if not url:
        raise HTTPException(status_code=400, detail="url or server_id is required.")
    if body.url:
        _validated_url_or_400(body.url)

    # None → stored value; "" → explicitly test without a credential
    # (mirrors the PUT null-keeps / ""-clears rule, §3.1).
    header = stored.credential_header if stored else None
    value = stored.credential_value if stored else None
    if body.credential_header is not None:
        header = body.credential_header or None
    if body.credential_value is not None:
        value = body.credential_value or None

    probe = await probe_mcp_server(url, credential_header=header, credential_value=value)
    return McpServerTestResponse(**vars(probe))


@mcp_router.post("/{server_id}/tools", response_model=McpServerCatalogResponse)
async def list_mcp_server_tools(
    server_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
    _origin: None = Depends(verify_origin),
) -> McpServerCatalogResponse:
    """Live catalog read for the Tool Node editor's checklist (#134, §6.3).

    One shared endpoint riding the short-lived probe connection
    (:func:`fetch_mcp_catalog`): open, handshake, ``tools/list``, close —
    every request hits the server live; **no catalog cache exists anywhere**
    (no DB snapshot, no in-process memo). An unreachable server comes back as
    a structured ``ok=False`` response (honest error, never stale data); the
    response never contains the credential (§5.4).
    """
    row = await get_mcp_server_row_or_404(session, server_id)
    catalog = await fetch_mcp_catalog(
        row.url,
        credential_header=row.credential_header,
        credential_value=row.credential_value,
    )
    return McpServerCatalogResponse(
        ok=catalog.ok,
        server_id=server_id,
        tools=[
            McpCatalogTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in catalog.tools
        ],
        server_name=catalog.server_name,
        server_version=catalog.server_version,
        latency_ms=catalog.latency_ms,
        detail=catalog.detail,
        classification=catalog.classification,
        protocol_revision=catalog.protocol_revision,
    )
