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
