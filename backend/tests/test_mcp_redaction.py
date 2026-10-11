"""Boundary redaction for configured MCP server secrets (ticket #140, spec §5.4).

One redaction pass strips the configured credential value and the server
endpoint URL from text/payloads bound for execution events, the UI, and
MLflow. SDK/transport error strings are the realistic leak vector — the
inputs come from the ``mcp_config`` process-local cache (the same read seam
the session registry uses), so redaction covers exactly the servers the run
can actually talk to.
"""

from unittest.mock import patch

from canvas_server.mcp_config import McpServerConfig
from canvas_server.mcp_redaction import (
    REDACTED,
    redact_mcp_payload,
    redact_mcp_text,
)


def make_server(
    name="corp-tools",
    url="https://mcp.corp.internal/sse",
    credential_header="X-Api-Key",
    credential_value="sk-corp-secret-123",
):
    import uuid

    return McpServerConfig(
        id=uuid.uuid4(),
        name=name,
        url=url,
        credential_header=credential_header,
        credential_value=credential_value,
    )


class ServerCache:
    """Patch ``get_mcp_servers`` so the redaction pass sees the test servers."""

    def __init__(self, *servers):
        self.servers = servers

    def __call__(self):
        return self.servers


class TestRedactMcpText:
    def test_strips_the_configured_credential_value(self):
        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(make_server()),
        ):
            assert (
                redact_mcp_text("POST /sse failed: 401 for key sk-corp-secret-123")
                == f"POST /sse failed: 401 for key {REDACTED}"
            )

    def test_strips_the_configured_endpoint_url(self):
        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(make_server()),
        ):
            assert (
                redact_mcp_text(
                    "ConnectError: connect to https://mcp.corp.internal/sse"
                    " failed after 3 retries"
                )
                == f"ConnectError: connect to {REDACTED} failed after 3 retries"
            )

    def test_every_server_url_and_credential_is_stripped(self):
        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(
                make_server(url="https://a.example.com", credential_value="AAAA1111"),
                make_server(url="https://b.example.com", credential_value="BBBB2222"),
            ),
        ):
            text = "a: AAAA1111 @ https://a.example.com; b: BBBB2222 @ https://b.example.com"
            assert redact_mcp_text(text) == (
                f"a: {REDACTED} @ {REDACTED}; b: {REDACTED} @ {REDACTED}"
            )

    def test_text_without_credentials_is_untouched(self):
        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(make_server()),
        ):
            original = "Execution error in add: server returned 500"
            assert redact_mcp_text(original) == original

    def test_no_servers_configured_is_a_passthrough(self):
        with patch("canvas_server.mcp_redaction.get_mcp_servers", ServerCache()):
            original = "ConnectError: connect to https://anything.invalid failed"
            assert redact_mcp_text(original) == original

    def test_absurdly_short_credentials_are_not_globalized(self):
        # A 1-2 char credential would mangle innocent text (every "a"/"-"
        # replaced) for near-zero secrecy; skip below the floor.
        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(make_server(credential_value="x")),
        ):
            original = "failed: x is required"
            assert redact_mcp_text(original) == original


class TestRedactMcpPayload:
    def test_redacts_nested_strings_in_exec_event_payloads(self):
        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(make_server()),
        ):
            payload = {
                "type": "tool_result",
                "tool": "add",
                "output": "Execution error: 401 sk-corp-secret-123",
                "input": {"q": "https://mcp.corp.internal/sse/probe"},
                "raw_content": [
                    {"type": "text", "text": "leak: sk-corp-secret-123"},
                ],
                "sequence": 3,
            }
            redacted = redact_mcp_payload(payload)
            assert redacted["output"] == f"Execution error: 401 {REDACTED}"
            assert redacted["input"]["q"] == f"{REDACTED}/probe"
            assert redacted["raw_content"][0]["text"] == f"leak: {REDACTED}"
            assert redacted["sequence"] == 3  # non-string values untouched

    def test_redacts_string_values_inside_lists(self):
        with patch(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(make_server()),
        ):
            assert redact_mcp_payload(
                {"items": ["https://mcp.corp.internal/sse", 7]}
            ) == {"items": [REDACTED, 7]}
