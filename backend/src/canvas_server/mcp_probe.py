"""MCP server connection probe (ticket #131).

Full-parity analogue of :mod:`canvas_server.provider_probe` for MCP servers:
a short-lived Streamable HTTP connection opened from the **backend
environment** (never the sandbox) that performs the ``initialize`` handshake,
lists tools, measures latency, and closes.

Probes never raise — a failure is reported as an ``ok=False`` result so the
Settings Test button can render it. Failures are best-effort classified
(spec §3.1): when ``initialize`` fails because the server speaks an
unsupported protocol revision, the probe names the revision; unrecognized
failure shapes collapse to the generic connection-failure class.

The probe result never carries the credential (§5.4); callers pass the
credential in and the response only carries connection facts.

This module is the shared MCP client primitive: the live-catalog endpoint
(#134) and the ZIP export snapshot (#135) reuse :func:`probe_mcp_server` /
:class:`McpSessionContext` rather than re-deriving the transport plumbing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import LATEST_PROTOCOL_VERSION
from mcp.types import Tool as McpTool

from canvas_server.config import settings

logger = logging.getLogger("canvas_server.mcp_probe")

# First Streamable HTTP protocol revision (2024-11-05 spoke deprecated HTTP+SSE).
# The negotiated head comes from the SDK instead of being hardcoded.
SUPPORTED_REVISION_FLOOR = "2025-03-26"
SUPPORTED_REVISION_HEAD = LATEST_PROTOCOL_VERSION

# Failure-classification category names.
CLASSIFICATION_OK = None
CLASSIFICATION_UNSUPPORTED_REVISION = "unsupported_protocol_revision"
CLASSIFICATION_CONNECTION_FAILURE = "connection_failure"

_UNSUPPORTED_VERSION_RE = re.compile(
    r"Unsupported protocol version from the server: (\S+)"
)


@dataclass(frozen=True)
class McpFailureClassification:
    category: str
    detail: str
    protocol_revision: str | None = None


@dataclass
class McpProbeResult:
    ok: bool
    server_name: str | None = None
    server_version: str | None = None
    tools: list[str] = field(default_factory=list)
    tool_count: int = 0
    latency_ms: int = 0
    detail: str = ""
    classification: str | None = None
    protocol_revision: str | None = None


@dataclass(frozen=True)
class McpToolDescriptor:
    """One catalog entry: name + description + the server-provided input
    schema, exactly as the server serves it — no client-side reshaping (#134)."""

    name: str
    description: str | None = None
    input_schema: dict = field(default_factory=dict)


@dataclass
class McpCatalogResult:
    """Full-descriptor sibling of :class:`McpProbeResult` for the editor's
    live-catalog fetch (#134, spec §6.3): same short-lived probe connection,
    same never-raises contract, but carries descriptions + input schemas."""

    ok: bool
    tools: list[McpToolDescriptor] = field(default_factory=list)
    server_name: str | None = None
    server_version: str | None = None
    latency_ms: int = 0
    detail: str = ""
    classification: str | None = None
    protocol_revision: str | None = None


def _iter_exception_tree(exc: BaseException) -> Iterator[BaseException]:
    """Flatten ExceptionGroups (anyio task-group wrapping is the norm here)."""
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            yield from _iter_exception_tree(sub)
    else:
        yield exc


def _summarize(exc: BaseException) -> str:
    """Human failure summary in the provider_probe._summarize style.

    Summarizes the first leaf exception: str(ExceptionGroup) is just
    "unhandled errors in a TaskGroup (N sub-exceptions)", which hides the
    informative part.
    """
    for leaf in _iter_exception_tree(exc):
        exc = leaf
        break
    text = str(exc) or type(exc).__name__
    lowered = text.lower()
    if "<html" in lowered or "<!doctype" in lowered:
        return "The endpoint returned an HTML page — check the server URL."
    if isinstance(exc, TimeoutError):
        return f"Timed out after {settings.llm_validation_timeout_seconds}s."
    if "401" in text or "Unauthorized" in lowered:
        return "401 Unauthorized — the credential header/value is missing, invalid, or expired."
    if "404" in text:
        return "404 Not Found — no MCP server at this URL."
    if "403" in text or "Forbidden" in text:
        return "403 Forbidden — the credential was rejected for this endpoint."
    return text[:300] + ("..." if len(text) > 300 else "")


def classify_mcp_failure(exc: BaseException) -> McpFailureClassification:
    """Best-effort classification of a probe failure (spec §3.1).

    The dedicated revision class fires only when a revision can actually be
    extracted (the official SDK raises ``RuntimeError("Unsupported protocol
    version from the server: <revision>")`` when the handshake returns one it
    does not speak). Everything else — JSON-RPC error ``-32022`` bodies from
    modern servers, POST-only/no-session-echo shapes, plain connection
    failures — collapses to the generic connection-failure class.
    """
    for sub in _iter_exception_tree(exc):
        match = _UNSUPPORTED_VERSION_RE.search(str(sub))
        if match:
            revision = match.group(1)
            return McpFailureClassification(
                category=CLASSIFICATION_UNSUPPORTED_REVISION,
                detail=(
                    f"Server speaks protocol revision {revision}; this client "
                    f"supports Streamable HTTP legacy revisions "
                    f"({SUPPORTED_REVISION_FLOOR} → {SUPPORTED_REVISION_HEAD})."
                ),
                protocol_revision=revision,
            )
    return McpFailureClassification(
        category=CLASSIFICATION_CONNECTION_FAILURE, detail=_summarize(exc)
    )


async def probe_mcp_server(
    url: str,
    *,
    credential_header: str | None = None,
    credential_value: str | None = None,
    timeout: float | None = None,
) -> McpProbeResult:
    """Connect, handshake, list tools, and close. Never raises."""
    timeout = timeout if timeout is not None else settings.llm_validation_timeout_seconds
    headers = (
        {credential_header: credential_value}
        if credential_header and credential_value
        else None
    )

    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            _connect_and_list(url, headers=headers, timeout=timeout),
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — probes never raise (§3.1)
        logger.info("MCP probe %r failed: %r", url.split("?")[0], exc)
        classification = classify_mcp_failure(exc)
        return McpProbeResult(
            ok=False,
            detail=classification.detail,
            latency_ms=int((time.perf_counter() - start) * 1000),
            classification=classification.category,
            protocol_revision=classification.protocol_revision,
        )
    return McpProbeResult(
        ok=True,
        detail="OK",
        latency_ms=int((time.perf_counter() - start) * 1000),
        **result,
    )


def _open_session(
    url: str, *, headers: dict[str, str] | None, timeout: float
) -> AbstractAsyncContextManager:
    """The shared transport block: Streamable HTTP + ``ClientSession``.

    One client primitive, two consumers (#126 §4): the name-only probe
    (:func:`probe_mcp_server`) and the full-descriptor catalog fetch
    (:func:`fetch_mcp_catalog`) both open, handshake, and close through here.
    """
    return _session_cm(url, headers=headers, timeout=timeout)


@asynccontextmanager
async def _session_cm(
    url: str, *, headers: dict[str, str] | None, timeout: float
):
    async with streamablehttp_client(
        url, headers=headers, timeout=timeout, sse_read_timeout=timeout
    ) as (read_stream, write_stream, _get_session_id), ClientSession(
        read_stream, write_stream
    ) as session:
        yield session


async def _connect_and_list(
    url: str, *, headers: dict[str, str] | None, timeout: float
) -> dict:
    """Run the full handshake + tools/list; returns McpProbeResult fields."""
    async with _session_cm(url, headers=headers, timeout=timeout) as session:
        init = await session.initialize()
        listing = await session.list_tools()

    return {
        "server_name": init.serverInfo.name,
        "server_version": init.serverInfo.version,
        "tools": [tool.name for tool in listing.tools],
        "tool_count": len(listing.tools),
        "protocol_revision": init.protocolVersion,
    }


async def fetch_mcp_catalog(
    url: str,
    *,
    credential_header: str | None = None,
    credential_value: str | None = None,
    timeout: float | None = None,
) -> McpCatalogResult:
    """Connect, handshake, and list full tool descriptors, then close.

    The editor's live-catalog read (#134, spec §6.3): rides the same
    short-lived probe connection as :func:`probe_mcp_server` — no cache lives
    anywhere. Never raises; failures come back as ``ok=False`` with the
    classified detail so the picker can show an honest error.
    """
    timeout = timeout if timeout is not None else settings.llm_validation_timeout_seconds
    headers = (
        {credential_header: credential_value}
        if credential_header and credential_value
        else None
    )

    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            _connect_and_catalog(url, headers=headers, timeout=timeout),
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — probes never raise (§3.1)
        logger.info("MCP catalog fetch %r failed: %r", url.split("?")[0], exc)
        classification = classify_mcp_failure(exc)
        return McpCatalogResult(
            ok=False,
            detail=classification.detail,
            latency_ms=int((time.perf_counter() - start) * 1000),
            classification=classification.category,
            protocol_revision=classification.protocol_revision,
        )
    latency = int((time.perf_counter() - start) * 1000)
    return McpCatalogResult(
        ok=True,
        detail="OK",
        latency_ms=latency,
        **result,
    )


async def _connect_and_catalog(
    url: str, *, headers: dict[str, str] | None, timeout: float
) -> dict:
    async with _session_cm(url, headers=headers, timeout=timeout) as session:
        init = await session.initialize()
        listing = await session.list_tools()

    return {
        "tools": [
            McpToolDescriptor(
                name=tool.name,
                description=tool.description,
                input_schema=dict(tool.inputSchema) if tool.inputSchema else {},
            )
            for tool in listing.tools
        ],
        "server_name": init.serverInfo.name,
        "server_version": init.serverInfo.version,
        "protocol_revision": init.protocolVersion,
    }

async def capture_mcp_metadata_snapshot(
    url: str,
    *,
    credential_header: str | None = None,
    credential_value: str | None = None,
    timeout: float | None = None,
) -> dict:
    """Full metadata snapshot for the ZIP export (ticket #136, spec §2.3).

    Same probe path as :func:`probe_mcp_server` (short-lived backend-side
    Streamable HTTP connection), but returns each tool's description and raw
    JSON ``inputSchema`` alongside the name. Never raises — the result is the
    manifest's ``mcp_reference.snapshot`` block:

    ``{"captured": True, "server_name", "server_version", "protocol_revision",
    "tools": [{"name", "description", "input_schema"}]}`` on success, or
    ``{"captured": False, "detail": "...", "tools": []}`` when the live fetch
    fails (export records the snapshot as unavailable rather than failing).
    The credential never appears in the returned metadata.
    """
    timeout = timeout if timeout is not None else settings.llm_validation_timeout_seconds
    headers = (
        {credential_header: credential_value}
        if credential_header and credential_value
        else None
    )
    try:
        result = await asyncio.wait_for(
            _connect_and_snapshot(url, headers=headers, timeout=timeout),
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — snapshots never raise (§3.1 parity)
        logger.info("MCP snapshot %r failed: %r", url.split("?")[0], exc)
        return {
            "captured": False,
            "detail": classify_mcp_failure(exc).detail,
            "tools": [],
        }
    return result


async def _connect_and_snapshot(
    url: str, *, headers: dict[str, str] | None, timeout: float
) -> dict:
    """Handshake + tools/list, keeping descriptions and input schemas."""
    async with _session_cm(url, headers=headers, timeout=timeout) as session:
        init = await session.initialize()
        listing = await session.list_tools()

    return {
        "captured": True,
        "server_name": init.serverInfo.name,
        "server_version": init.serverInfo.version,
        "protocol_revision": init.protocolVersion,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": _get_tool_input_schema(tool),
            }
            for tool in listing.tools
        ],
    }


def _get_tool_input_schema(tool: McpTool) -> dict:
    """The raw JSON schema dict, tolerant of camelCase/snake_case SDK shapes."""
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
    if schema is None:
        return {}
    return schema if isinstance(schema, dict) else dict(schema)
