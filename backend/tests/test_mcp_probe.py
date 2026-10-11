"""MCP server connection-probe tests (ticket #131).

The reference servers are real Streamable HTTP MCP servers built from the
official ``mcp`` 1.x SDK primitives — defined once in ``tests/conftest.py``
(``ref_mcp_server``, ``modern_revision_mcp_server``, ``auth_ref_mcp_server``)
so the catalog (#134) and ZIP-snapshot (#136) tickets can reuse them. served
in-process from a background thread via uvicorn, so probe tests stay
Docker-free and exercise the probe module's public seam:
``probe_mcp_server`` / ``classify_mcp_failure``.
"""

import json

from mcp import types as mcp_types
from mcp.shared.exceptions import McpError

from canvas_server.mcp_probe import classify_mcp_failure, probe_mcp_server

# The modern (2026-07-28) revision the bundled 1.x client deliberately does
# not speak — Streamable HTTP legacy revisions end at 2025-11-25.
MODERN_REVISION = "2026-07-28"


async def test_probe_ok_against_reference_server(ref_mcp_server):
    result = await probe_mcp_server(ref_mcp_server)

    assert result.ok is True
    assert result.server_name == "ags-probe-ref"
    assert result.server_version  # version string from the handshake
    assert result.tools == ["add"]
    assert result.tool_count == 1
    assert result.latency_ms >= 0
    assert result.detail == "OK"
    assert result.classification is None


async def test_probe_latency_reflects_a_real_round_trip(ref_mcp_server):
    result = await probe_mcp_server(ref_mcp_server)

    # Handshake + tools/list over loopback: fast, but strictly > 0 ms.
    assert 0 < result.latency_ms < 10_000


async def test_probe_does_not_raise_on_connection_failure():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]

    result = await probe_mcp_server(f"http://127.0.0.1:{dead_port}/mcp")

    assert result.ok is False
    assert result.server_name is None
    assert result.tools == []
    assert result.tool_count == 0
    assert result.detail
    assert result.latency_ms >= 0
    assert result.classification == "connection_failure"


# --- Modern-revision server shape (spec §3.1 classification) ---


async def test_probe_names_revision_of_unsupported_server(modern_revision_mcp_server):
    result = await probe_mcp_server(modern_revision_mcp_server)

    assert result.ok is False
    assert result.classification == "unsupported_protocol_revision"
    assert result.protocol_revision == MODERN_REVISION
    assert result.detail == (
        "Server speaks protocol revision 2026-07-28; this client supports "
        "Streamable HTTP legacy revisions (2025-03-26 → 2025-11-25)."
    )


# --- Credential handling ---


async def test_probe_without_credential_fails_with_401(auth_ref_mcp_server):
    result = await probe_mcp_server(auth_ref_mcp_server)

    assert result.ok is False
    assert "401" in result.detail


async def test_probe_with_credential_succeeds(auth_ref_mcp_server):
    result = await probe_mcp_server(
        auth_ref_mcp_server,
        credential_header="Authorization",
        credential_value="Bearer good-token",
    )

    assert result.ok is True
    assert result.server_name == "ags-probe-auth-ref"
    assert result.tools == ["echo"]


async def test_probe_result_never_carries_the_credential(auth_ref_mcp_server):
    secret = "Bearer super-secret-token-value"

    def contains_secret(value: object) -> bool:
        return secret in repr(value)

    assert not contains_secret(
        await probe_mcp_server(
            auth_ref_mcp_server,
            credential_header="Authorization",
            credential_value=secret,
        )
    )
    assert not contains_secret(await probe_mcp_server(auth_ref_mcp_server))


# --- Classification of mock failure shapes (pure, wire-free) ---


def test_classify_sdk_unsupported_version_runtime_error():
    exc = RuntimeError(f"Unsupported protocol version from the server: {MODERN_REVISION}")
    classified = classify_mcp_failure(exc)

    assert classified.category == "unsupported_protocol_revision"
    assert classified.protocol_revision == MODERN_REVISION
    assert MODERN_REVISION in classified.detail
    assert "2025-03-26" in classified.detail and "2025-11-25" in classified.detail


def test_classify_jsonrpc_32022_error_collapses_to_generic():
    exc = McpError(
        error=mcp_types.ErrorData(code=-32022, message="Unsupported protocol version")
    )
    classified = classify_mcp_failure(exc)

    assert classified.category == "connection_failure"
    assert classified.protocol_revision is None
    assert classified.detail


def test_classify_group_wrapped_revision_error_is_still_found():
    exc = ExceptionGroup(
        "wrapped",
        [
            ValueError("noise"),
            RuntimeError(
                f"Unsupported protocol version from the server: {MODERN_REVISION}"
            ),
        ],
    )
    classified = classify_mcp_failure(exc)

    assert classified.category == "unsupported_protocol_revision"
    assert classified.protocol_revision == MODERN_REVISION


def test_classify_group_summary_uses_the_leaf_exception():
    exc = ExceptionGroup("wrapped", [ConnectionRefusedError("connection refused")])
    classified = classify_mcp_failure(exc)

    assert classified.category == "connection_failure"
    assert classified.detail == "connection refused"


def test_classify_plain_exception_collapses_to_generic():
    exc = ConnectionRefusedError("connection refused")
    classified = classify_mcp_failure(exc)

    assert classified.category == "connection_failure"
    assert classified.protocol_revision is None
    assert classified.detail == "connection refused"


# --- Live-tool-catalog fetch (#134, spec §6.3) ---
#
# The catalog is the probe's full-descriptor sibling: instead of tool *names*
# it returns each tool's description and the server-provided input schema, so
# the editor's checklist can render inspection data from the same short-lived
# probe connection. Same seam, same never-raises contract.


async def test_catalog_ok_against_reference_server(ref_mcp_server):
    from canvas_server.mcp_probe import fetch_mcp_catalog

    result = await fetch_mcp_catalog(ref_mcp_server)

    assert result.ok is True
    assert result.server_name == "ags-probe-ref"
    assert result.latency_ms >= 0
    assert result.detail == "OK"
    assert result.classification is None
    assert len(result.tools) == 1

    tool = result.tools[0]
    assert tool.name == "add"
    assert "two integers" in (tool.description or "")
    # The server-provided schema reaches the editor untouched — the ``a``
    # property comes straight from the SDK's annotation-derived schema.
    assert tool.input_schema.get("properties", {}).get("a", {}).get("type") == "integer"


async def test_catalog_failure_is_ok_false_with_detail():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]

    from canvas_server.mcp_probe import fetch_mcp_catalog

    result = await fetch_mcp_catalog(f"http://127.0.0.1:{dead_port}/mcp")

    assert result.ok is False
    assert result.tools == []
    assert result.detail
    assert result.classification == "connection_failure"


async def test_catalog_without_credential_fails_and_never_carries_it(
    auth_ref_mcp_server,
):
    from canvas_server.mcp_probe import fetch_mcp_catalog

    failed = await fetch_mcp_catalog(auth_ref_mcp_server)
    assert failed.ok is False
    assert "401" in failed.detail or "Unauthorized" in failed.detail.lower()

    ok = await fetch_mcp_catalog(
        auth_ref_mcp_server,
        credential_header="Authorization",
        credential_value="Bearer good-token",
    )
    assert ok.ok is True
    assert ok.tools[0].name == "echo"

    import dataclasses

    dumped = str(dataclasses.asdict(ok))
    assert "good-token" not in dumped


# --- Live remote tool call (#135, spec §6.4) ---
#
# The Test panel's second stage calls ``tools/call`` on the raw ClientSession
# (NOT the dspy wrapper — that one raises RuntimeError on in-band error
# results, which would collapse the two cases the panel must distinguish).
# Same short-lived connection, same never-raises contract.


async def test_call_tool_returns_text_blocks(ref_mcp_server):
    from canvas_server.mcp_probe import call_mcp_tool

    result = await call_mcp_tool(ref_mcp_server, "add", {"a": 2, "b": 3})

    assert result.ok is True
    assert result.is_error is False
    assert result.detail == "OK"
    assert result.latency_ms >= 0
    assert result.classification is None
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block.type == "text"
    assert block.text == "5"
    assert block.placeholder is None


async def test_call_tool_in_band_is_error_is_reported_as_an_error(
    error_ref_mcp_server,
):
    from canvas_server.mcp_probe import call_mcp_tool

    result = await call_mcp_tool(error_ref_mcp_server, "explode", {})

    # The call itself completed (ok) — but the server answered with an in-band
    # isError result, which must be reported as an error, not output.
    assert result.ok is True
    assert result.is_error is True
    assert result.blocks, "the server's error explanation blocks are preserved"
    joined = " ".join(b.text or "" for b in result.blocks)
    assert "boom" in joined


async def test_call_tool_bad_args_come_back_structured(error_ref_mcp_server):
    from canvas_server.mcp_probe import call_mcp_tool

    result = await call_mcp_tool(
        error_ref_mcp_server, "add", {"a": "not-an-int", "b": 3}
    )

    # Never raises: FastMCP's input validation lands as an in-band isError
    # result whose text explains the problem.
    assert result.ok is True
    assert result.is_error is True
    assert result.blocks
    assert (result.blocks[0].text or "").strip()


async def test_call_tool_non_text_blocks_carry_placeholders(error_ref_mcp_server):
    from canvas_server.mcp_probe import call_mcp_tool

    result = await call_mcp_tool(error_ref_mcp_server, "produce_image", {})

    assert result.ok is True
    assert result.is_error is False
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block.type == "image"
    # The binary payload never enters the response; a human note does.
    assert block.text is None
    assert block.placeholder
    assert block.mime_type == "image/png"
    assert "not-really-a-png" not in block.placeholder


async def test_call_tool_connection_failure_is_structured():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]

    from canvas_server.mcp_probe import call_mcp_tool

    result = await call_mcp_tool(f"http://127.0.0.1:{dead_port}/mcp", "add", {})

    assert result.ok is False
    assert result.is_error is False
    assert result.blocks == []
    assert result.classification == "connection_failure"
    assert result.detail


async def test_call_tool_unknown_tool_comes_back_in_band(ref_mcp_server):
    from canvas_server.mcp_probe import call_mcp_tool

    result = await call_mcp_tool(ref_mcp_server, "does_not_exist", {})

    # mcp 1.30 servers report unknown tools as an in-band isError result with
    # the explanation as text — structured, honest, never an exception.
    assert result.ok is True
    assert result.is_error is True
    assert "does_not_exist" in (result.blocks[0].text or "")


def test_call_tool_classifies_json_rpc_rejection_as_call_failure(monkeypatch):
    """A server that rejects ``tools/call`` at the JSON-RPC layer (client-side
    ``McpError`` rather than an in-band result) is a distinct failure class —
    pinned here with the exception shape, since the reference servers report
    everything in-band."""
    import asyncio

    from mcp.shared.exceptions import McpError
    from mcp.types import INTERNAL_ERROR, ErrorData

    from canvas_server import mcp_probe

    error = McpError(ErrorData(code=INTERNAL_ERROR, message="Internal error", data=None))

    async def _fake_connect(url, tool_name, arguments, *, headers, timeout):
        raise error

    monkeypatch.setattr(mcp_probe, "_connect_and_call", _fake_connect)

    result = asyncio.run(
        mcp_probe.call_mcp_tool("http://example.test/mcp", "add", {})
    )

    assert result.ok is False
    assert result.is_error is False
    assert result.classification == "call_failure"
    assert "Internal error" in result.detail


async def test_call_tool_never_carries_the_credential(auth_ref_mcp_server):
    from canvas_server.mcp_probe import call_mcp_tool

    result = await call_mcp_tool(
        auth_ref_mcp_server,
        "echo",
        {"a": "x"},
        credential_header="Authorization",
        credential_value="Bearer good-token",
    )

    assert result.ok is True  # credential was honored
    import dataclasses

    dumped = str(dataclasses.asdict(result))
    assert "good-token" not in dumped


# --- Metadata snapshot capture (ticket #136, ZIP export §2.3) ---


async def test_snapshot_captures_full_metadata_against_reference_server(ref_mcp_server):
    """The ZIP-export snapshot carries tool names, descriptions, and input
    schemas — not just the name list the live probe returns."""
    from canvas_server.mcp_probe import capture_mcp_metadata_snapshot

    snap = await capture_mcp_metadata_snapshot(ref_mcp_server)

    assert snap["captured"] is True
    assert snap["server_name"] == "ags-probe-ref"
    assert snap["server_version"]
    assert snap["protocol_revision"]
    assert [t["name"] for t in snap["tools"]] == ["add"]
    add_tool = snap["tools"][0]
    assert add_tool["description"] == "Add two integers."
    schema = add_tool["input_schema"]
    assert "a" in schema["properties"] and "b" in schema["properties"]
    assert schema["properties"]["a"]["type"] == "integer"


async def test_snapshot_never_raises_on_connection_failure():
    import socket

    from canvas_server.mcp_probe import capture_mcp_metadata_snapshot

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]

    snap = await capture_mcp_metadata_snapshot(f"http://127.0.0.1:{dead_port}/mcp")

    assert snap["captured"] is False
    assert snap["detail"]  # human-readable failure summary
    assert snap["tools"] == []


async def test_snapshot_passes_credential_to_the_server(auth_ref_mcp_server):
    """The snapshot uses the stored credential header/value to connect —
    without ever embedding it in the returned metadata."""
    from canvas_server.mcp_probe import capture_mcp_metadata_snapshot

    snap = await capture_mcp_metadata_snapshot(
        auth_ref_mcp_server,
        credential_header="Authorization",
        credential_value="Bearer good-token",
    )
    assert snap["captured"] is True
    # No credential material leaks into the snapshot payload.
    serialized = json.dumps(snap)
    assert "good-token" not in serialized
