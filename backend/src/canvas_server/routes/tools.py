"""Routes for the tool inspection and testing API.

Kind-discriminated (#135, spec §6.4):
``kind: "code"`` (the default) is the original stateless sandbox path —
no database session needed. ``kind: "mcp"`` rides the shared probe path:
inspect pulls the server-provided input schema live; test runs two stages
(connection probe, then a live remote ``tools/call`` executed from the
backend environment, never the sandbox). The MCP branches read the stored
registration from the database and never echo the credential (§5.4).
"""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.database import get_session
from canvas_server.exceptions import ToolCompilationError
from canvas_server.mcp_probe import call_mcp_tool, fetch_mcp_catalog, probe_mcp_server
from canvas_server.models.api import (
    McpInspectTool,
    McpToolCallBlock,
    ToolInspectRequest,
    ToolInspectResponse,
    ToolTestRequest,
    ToolTestResponse,
)
from canvas_server.routes import get_mcp_server_row_or_404
from canvas_server.tool_factory import execute_tool_code, inspect_tool_code

logger = logging.getLogger("canvas_server.routes.tools")

tools_router = APIRouter(prefix="/api/tools", tags=["tools"])


@tools_router.post("/inspect", response_model=ToolInspectResponse)
async def inspect_tool(
    body: ToolInspectRequest,
    session: AsyncSession = Depends(get_session),
) -> ToolInspectResponse:
    """Inspect a tool.

    ``kind: "code"``: inspect a Python tool function — accepts a code string
    containing a Python function definition and returns the function name and
    a list of arguments with type hints and default values.

    ``kind: "mcp"``: pull the **server-provided** input schema live over the
    short-lived probe connection — a named tool (``mcp_tool_name``) or the
    full catalog. Unreachable servers come back as structured ``ok=false``
    responses, never HTTP errors.
    """
    if body.kind == "mcp":
        return await _inspect_mcp_tool(body, session)

    logger.info("Inspecting tool code: %s chars, deps=%s", len(body.code), body.dependencies)
    try:
        result = await inspect_tool_code("test_tool", body.code, dependencies=body.dependencies)
    except ToolCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ToolInspectResponse(
        kind="code",
        function_name=result.function_name,
        arguments=result.arguments,
    )


async def _inspect_mcp_tool(
    body: ToolInspectRequest, session: AsyncSession
) -> ToolInspectResponse:
    if body.mcp_server_id is None:
        raise HTTPException(
            status_code=400, detail="mcp_server_id is required for kind=mcp."
        )
    row = await get_mcp_server_row_or_404(session, body.mcp_server_id)
    catalog = await fetch_mcp_catalog(
        row.url,
        credential_header=row.credential_header,
        credential_value=row.credential_value,
    )
    base = {
        "kind": "mcp",
        "server_id": row.id,
        "latency_ms": catalog.latency_ms,
        "server_name": catalog.server_name,
        "server_version": catalog.server_version,
        "protocol_revision": catalog.protocol_revision,
    }
    if not catalog.ok:
        return ToolInspectResponse(
            ok=False,
            detail=catalog.detail,
            classification=catalog.classification,
            **base,
        )
    if body.mcp_tool_name is None:
        return ToolInspectResponse(
            ok=True,
            tools=[
                McpInspectTool(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
                for tool in catalog.tools
            ],
            **base,
        )
    matched = next(
        (t for t in catalog.tools if t.name == body.mcp_tool_name), None
    )
    if matched is None:
        return ToolInspectResponse(
            ok=False,
            classification="tool_not_found",
            detail=(
                f"Tool {body.mcp_tool_name!r} was not found on server "
                f"{row.name!r}. Enable it in the tool list first."
            ),
            **base,
        )
    return ToolInspectResponse(
        ok=True,
        tool=McpInspectTool(
            name=matched.name,
            description=matched.description,
            input_schema=matched.input_schema,
        ),
        **base,
    )


@tools_router.post("/test", response_model=ToolTestResponse)
async def test_tool(
    body: ToolTestRequest,
    session: AsyncSession = Depends(get_session),
) -> ToolTestResponse:
    """Test a tool.

    ``kind: "code"``: execute a Python tool function with the provided
    arguments in the sandbox — string arg values are coerced to the function's
    type hints.

    ``kind: "mcp"``: two stages (#135, §6.4) — ``stage: "probe"`` is the
    connection probe (initialize + ``tools/list`` + latency via the shared
    #131 path); ``stage: "call"`` performs the live remote ``tools/call``
    from the backend environment (never the sandbox). The response never
    throws: connection failures are structured ``ok=false`` bodies, and
    in-band ``isError`` results are reported via ``is_error`` + ``blocks``,
    distinct from success output.
    """
    if body.kind == "mcp":
        return await _test_mcp_tool(body, session)

    logger.info("Testing tool code: %s chars, %d args, deps=%s", len(body.code), len(body.args), body.dependencies)
    return await execute_tool_code("test_tool", body.code, body.args, dependencies=body.dependencies)


async def _test_mcp_tool(
    body: ToolTestRequest, session: AsyncSession
) -> ToolTestResponse:
    if body.mcp_server_id is None:
        raise HTTPException(
            status_code=400, detail="mcp_server_id is required for kind=mcp."
        )
    row = await get_mcp_server_row_or_404(session, body.mcp_server_id)

    # Test-time credential overrides follow the provider convention (#131):
    # omitted (None) → stored value; "" → test without a credential even if
    # one is stored.
    header = row.credential_header
    value = row.credential_value
    if body.credential_header is not None:
        header = body.credential_header or None
    if body.credential_value is not None:
        value = body.credential_value or None

    if body.stage == "probe":
        probe = await probe_mcp_server(url=row.url, credential_header=header, credential_value=value)
        return ToolTestResponse(
            kind="mcp",
            stage="probe",
            ok=probe.ok,
            success=probe.ok,
            server_name=probe.server_name,
            server_version=probe.server_version,
            tools=probe.tools,
            tool_count=probe.tool_count,
            latency_ms=probe.latency_ms,
            detail=probe.detail,
            classification=probe.classification,
            protocol_revision=probe.protocol_revision,
        )

    if not body.mcp_tool_name:
        raise HTTPException(
            status_code=400,
            detail="mcp_tool_name is required for the MCP call stage.",
        )
    result = await call_mcp_tool(
        row.url,
        body.mcp_tool_name,
        body.mcp_args,
        credential_header=header,
        credential_value=value,
    )
    return ToolTestResponse(
        kind="mcp",
        stage="call",
        ok=result.ok,
        # An in-band isError result executed but is an error, not a success
        # output (§6.4).
        success=result.ok and not result.is_error,
        is_error=result.is_error,
        blocks=[McpToolCallBlock(**asdict(block)) for block in result.blocks],
        latency_ms=result.latency_ms,
        detail=result.detail,
        classification=result.classification,
        protocol_revision=result.protocol_revision,
    )
