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
from mcp.shared.exceptions import McpError
from mcp.types import LATEST_PROTOCOL_VERSION, TextContent

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
# The call stage (#135) adds one class: the handshake succeeded but the
# JSON-RPC ``tools/call`` request itself was rejected (unknown tool, invalid
# params reported as a JSON-RPC error, …). In-band ``isError`` results are NOT
# failures at this level — they executed and are surfaced via ``is_error``.
CLASSIFICATION_CALL_FAILURE = "call_failure"

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


# --- Live remote tool call (#135, spec §6.4) --------------------------------


@dataclass(frozen=True)
class McpToolOutputBlock:
    """One content block of a ``CallToolResult``, block-structured for the
    Test panel. Text carries its text; non-text blocks carry a mime type /
    resource URI plus a human ``placeholder`` note — the binary payload never
    enters the response (same posture as the runtime's observation joining)."""

    type: str
    text: str | None = None
    mime_type: str | None = None
    resource_uri: str | None = None
    placeholder: str | None = None


@dataclass
class McpToolCallResult:
    """:func:`call_mcp_tool`'s outcome. ``ok`` means the call **executed and
    was answered** (connection + JSON-RPC round trip); ``is_error`` is the
    server's in-band ``CallToolResult.isError`` — reported as such, never
    folded into a successful output. Never raises."""

    ok: bool
    is_error: bool = False
    blocks: list[McpToolOutputBlock] = field(default_factory=list)
    latency_ms: int = 0
    detail: str = ""
    classification: str | None = None
    protocol_revision: str | None = None


def _blocks_from_content(content: list) -> list[McpToolOutputBlock]:
    """Map SDK content blocks onto Test-panel blocks.

    In-band error results keep their text blocks so the panel can show the
    server's explanation; non-text content degrades to a placeholder note.
    """
    blocks: list[McpToolOutputBlock] = []
    for item in content:
        if isinstance(item, TextContent):
            blocks.append(McpToolOutputBlock(type="text", text=item.text))
            continue
        type_name = getattr(item, "type", None) or type(item).__name__
        mime = getattr(item, "mimeType", None)
        uri = getattr(item, "uri", None)
        if uri is None:
            resource = getattr(item, "resource", None)
            if resource is not None:
                mime = getattr(resource, "mimeType", None) or mime
                uri = getattr(resource, "uri", None)
        note = getattr(item, "data", None)
        size_hint = f"{len(item.data)} bytes" if isinstance(note, (str, bytes)) else None
        placeholder_parts = [f"[{type_name} output — not rendered in this panel"]
        if mime:
            placeholder_parts[0] += f", {mime}"
        if size_hint:
            placeholder_parts[0] += f", {size_hint}"
        placeholder_parts[0] += "]"
        blocks.append(
            McpToolOutputBlock(
                type=type_name,
                mime_type=mime,
                resource_uri=str(uri) if uri is not None else None,
                placeholder=placeholder_parts[0],
            )
        )
    return blocks


async def _connect_and_call(
    url: str,
    tool_name: str,
    arguments: dict,
    *,
    headers: dict[str, str] | None,
    timeout: float,
) -> dict:
    async with _session_cm(url, headers=headers, timeout=timeout) as session:
        init = await session.initialize()
        result = await session.call_tool(tool_name, arguments=arguments)

    return {
        "is_error": bool(result.isError),
        "blocks": _blocks_from_content(list(result.content)),
        "protocol_revision": init.protocolVersion,
    }


async def call_mcp_tool(
    url: str,
    tool_name: str,
    arguments: dict,
    *,
    credential_header: str | None = None,
    credential_value: str | None = None,
    timeout: float | None = None,
) -> McpToolCallResult:
    """Call ``tools/call`` from the backend environment over one short-lived
    Streamable HTTP connection, then close (#135 Test panel stage 2).

    Never raises — every failure shape comes back as a structured result:

    - transport/handshake failure → ``ok=False`` with the classification from
      :func:`classify_mcp_failure` (connection failure, timeout, revision …);
    - JSON-RPC-level rejection of the call itself (unknown tool, invalid params
      reported as an RPC error) → ``ok=False`` with
      ``classification="call_failure"``;
    - in-band ``isError`` results → ``ok=True, is_error=True`` with the
      server's explanation blocks preserved — the exact distinction the
      panel must render (output vs error result).

    The raw ``ClientSession.call_tool`` is used, deliberately NOT dspy's
    convert wrapper (which raises ``RuntimeError`` on isError results and
    would collapse the two cases). The credential never appears in the
    result (§5.4).
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
            _connect_and_call(
                url, tool_name, arguments, headers=headers, timeout=timeout
            ),
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — the call stage never raises (§6.4)
        logger.info(
            "MCP tool call %r/%r failed: %r", url.split("?")[0], tool_name, exc
        )
        classification = classify_mcp_failure(exc)
        category = classification.category
        detail = classification.detail
        if isinstance(exc, McpError):
            # The handshake may have succeeded; the tools/call request itself
            # was rejected at the JSON-RPC layer.
            category = CLASSIFICATION_CALL_FAILURE
            detail = str(exc)[:300] or f"{type(exc).__name__}"
        return McpToolCallResult(
            ok=False,
            detail=detail,
            classification=category,
            latency_ms=int((time.perf_counter() - start) * 1000),
            protocol_revision=classification.protocol_revision,
        )
    return McpToolCallResult(
        ok=True,
        detail="OK",
        latency_ms=int((time.perf_counter() - start) * 1000),
        **result,
    )
