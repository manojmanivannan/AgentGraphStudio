"""MCP server URL policy (spec §5.1): http(s) accepted, others rejected.

Plain ``http://`` is warned about — not blocked — so localhost dev servers
remain usable. There is deliberately no IP/SSRF guard: server URLs are
workspace-operator-configured, the same self-configured posture as
``llm_base_url``.
"""

import pytest

from canvas_server.mcp_url_policy import validate_mcp_server_url


class TestHttpsUrlsAccepted:
    @pytest.mark.parametrize(
        "url",
        [
            "https://mcp.context7.com/mcp",
            "https://10.0.0.5/mcp",
        ],
    )
    def test_https_is_valid_without_warning(self, url):
        result = validate_mcp_server_url(url)
        assert result.ok is True
        assert result.error is None
        assert result.warning is None

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:8000/mcp",
            "http://127.0.0.1:3001/sse",
        ],
    )
    def test_http_is_valid_without_error(self, url):
        result = validate_mcp_server_url(url)
        assert result.ok is True
        assert result.error is None


class TestPlainHttpWarns:
    def test_http_gets_a_warning_but_still_ok(self):
        result = validate_mcp_server_url("http://localhost:8123/mcp")
        assert result.ok is True
        assert result.warning is not None

    def test_warning_does_not_appear_for_https(self):
        assert validate_mcp_server_url("https://example.com/mcp").warning is None


class TestOtherSchemesRejected:
    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/mcp",
            "file:///etc/passwd",
            "ws://example.com/mcp",
            "wss://example.com/mcp",
            "ssh://example.com",
            "example.com/mcp",
            "/relative/path",
            "localhost:8000/mcp",
        ],
    )
    def test_non_http_schemes_fail_withClear_error(self, url):
        result = validate_mcp_server_url(url)
        assert result.ok is False
        assert result.error is not None
        assert "http" in result.error.lower()

    def test_empty_url_is_rejected(self):
        assert validate_mcp_server_url("").ok is False

    def test_scheme_is_reported_in_the_error(self):
        result = validate_mcp_server_url("ftp://example.com/mcp")
        assert "ftp" in result.error

    def test_urlparse_ish_scheme_confusion_is_rejected(self):
        # A scheme like "https" mangled into the netloc must not validate.
        result = validate_mcp_server_url("https:/not-a-real-url")
        assert result.ok is False
