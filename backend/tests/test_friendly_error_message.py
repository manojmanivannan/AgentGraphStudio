"""Tests for the friendly LLM error translation in runner.execution.

The chat UI displays whatever ``_friendly_error_message`` returns, so every
common LLM/gateway failure must translate into a short actionable message
rather than a raw traceback/JSON blob.
"""

import pytest

from canvas_server.runner.execution import _friendly_error_message


class APIError(Exception):
    """Stand-in shaped like litellm.exceptions.APIError."""


class InternalServerError(Exception):
    """Stand-in shaped like litellm.exceptions.InternalServerError."""


class APIConnectionError(Exception):
    """Stand-in shaped like litellm.exceptions.APIConnectionError."""


OPENROUTER_502 = (
    'APIError: OpenrouterException - {"error":{"message":"Provider returned error",'
    '"code":502,"metadata":{"raw":"{\\n  \\"error\\": {\\n    \\"code\\": 500,'
    '\\n    \\"message\\": \\"Internal error encountered.\\",'
    '\\n    \\"status\\": \\"INTERNAL\\"\\n  }\\n}\\n",'
    '"provider_name":"Google AI Studio","is_byok":true,"provider_error_code":"500"}}},'
    '"user_id":"user_3AJiBlHrheRLNvGTOzUSkuGTiAX"} LiteLLM Retried: 3 times'
)


class TestGatewayErrors:
    """5xx gateway/provider failures must be translated, not echoed."""

    def test_502_provider_error_becomes_friendly_message(self):
        msg = _friendly_error_message(APIError(OPENROUTER_502))
        assert "502" in msg
        assert "provider" in msg.lower()
        # Actionable: tell the user it's transient
        assert "try again" in msg.lower()

    def test_502_does_not_leak_raw_json(self):
        msg = _friendly_error_message(APIError(OPENROUTER_502))
        assert '{"error"' not in msg
        assert "OpenrouterException" not in msg
        assert "user_id" not in msg

    def test_500_internal_error_becomes_friendly_message(self):
        msg = _friendly_error_message(InternalServerError("500 Internal error encountered."))
        assert "500" in msg
        assert "try again" in msg.lower()
        assert "Internal error encountered." not in msg

    def test_504_gateway_timeout_becomes_friendly_message(self):
        msg = _friendly_error_message(APIError("504 Gateway Timeout"))
        assert "504" in msg
        assert "try again" in msg.lower()

    def test_internal_server_error_type_is_translated(self):
        msg = _friendly_error_message(InternalServerError("upstream blew up"))
        assert "InternalServerError" not in msg
        assert "try again" in msg.lower()


class TestConnectionErrors:
    def test_api_connection_error_is_translated(self):
        msg = _friendly_error_message(
            APIConnectionError("Connection error: connection refused by endpoint")
        )
        assert "connect" in msg.lower()
        assert "connection refused" not in msg

    def test_connection_reset_is_translated(self):
        msg = _friendly_error_message(APIError("Connection reset by peer"))
        assert "connect" in msg.lower()


class TestExistingBehaviorPreserved:
    def test_401_still_translated(self):
        msg = _friendly_error_message(APIError("401 Unauthorized: bad key"))
        assert "401" in msg
        assert "API key" in msg

    def test_429_still_translated(self):
        msg = _friendly_error_message(APIError("429 Too Many Requests"))
        assert "429" in msg

    def test_503_still_translated(self):
        msg = _friendly_error_message(APIError("503 ServiceUnavailable"))
        assert "503" in msg

    def test_403_still_translated(self):
        msg = _friendly_error_message(APIError("403 Forbidden"))
        assert "403" in msg

    def test_long_unrelated_message_is_truncated(self):
        msg = _friendly_error_message(ValueError("x" * 1000))
        assert len(msg) <= 404
        assert msg.startswith("xxx")

    def test_short_unrelated_message_passes_through(self):
        msg = _friendly_error_message(ValueError("something unrelated but short"))
        assert msg == "something unrelated but short"


@pytest.mark.parametrize(
    "exc_str",
    [
        OPENROUTER_502,
        "500 Internal error encountered.",
        "504 Gateway Timeout",
        "Connection reset by peer",
    ],
)
def test_translated_messages_stay_short(exc_str):
    """Every translated message must stay compact enough for the chat UI."""
    msg = _friendly_error_message(APIError(exc_str))
    assert len(msg) <= 300
