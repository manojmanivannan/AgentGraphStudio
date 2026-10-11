"""Boundary redaction for configured MCP server secrets (ticket #140, spec §5.4).

One redaction pass strips every *configured* MCP credential value and server
endpoint URL from error/event text bound for execution events, the UI, and
MLflow. SDK/transport error strings (httpx ``ConnectError``, auth rejections,
server 500s) are the realistic leak vector.

The inputs are the *configured* servers from the ``mcp_config`` process-local
cache — the same read seam ``McpSessionRegistry`` resolves sessions through —
so redaction covers exactly the servers a run can actually talk to. There is
**no general redaction layer** here: provider keys, sandbox internals, and
non-MCP secrets are explicitly out of scope (spec §5.4, plaintext-credential
trust level per ADR 0008/0009).

Choke points wiring this pass in (ticket #140):

* ``BackgroundRunWorker._execute_run``'s ``send_event`` closure (before the
  durable append + broker publish) — covers execution events, DB replay, and
  the UI for every worker-run event;
* the worker's run-level ``error``/``run_aborted`` payloads (built directly,
  not routed through ``send_event``);
* ``StreamingReAct``'s tool-error observation string (feeds MLflow autolog
  trajectories as well as the ``tool_result`` event);
* ``ConversationRunCoordinator._persist_error`` (the final-answer message
  persisted to the conversation on a failed run).
"""

from __future__ import annotations

import logging
from typing import Any

from canvas_server.mcp_config import get_mcp_servers

logger = logging.getLogger("canvas_server.mcp_redaction")

REDACTED = "[REDACTED]"

# Below this length a credential would mangle innocent text (every 1-2 char
# substring replaced) for near-zero secrecy gain. Configured MCP credentials
# are real API keys, far above this floor.
_MIN_REDACT_LENGTH = 4


def _secret_literals() -> tuple[str, ...]:
    """The credential values + endpoint URLs currently configured, longest first.

    Longest-first so overlapping literals (a URL that contains the credential,
    or a credential that embeds the URL) are replaced once, cleanly.
    """
    literals: set[str] = set()
    try:
        servers = get_mcp_servers()
    except Exception:  # noqa: BLE001 — the cache is read on the hot event path
        logger.debug("MCP server cache unavailable; nothing to redact")
        return ()
    for server in servers:
        if server.credential_value and len(server.credential_value) >= _MIN_REDACT_LENGTH:
            literals.add(server.credential_value)
        if server.url:
            literals.add(server.url)
    return tuple(sorted(literals, key=len, reverse=True))


def redact_mcp_text(text: str) -> str:
    """Strip configured MCP credential values and endpoint URLs from *text*.

    Exact-literal replacement: SDK error strings quote the configured URL
    verbatim. No pattern matching beyond literals — configured values are
    known exactly.
    """
    if not text:
        return text
    for literal in _secret_literals():
        text = text.replace(literal, REDACTED)
    return text


def redact_mcp_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact every string value in an event payload.

    Returns a rebuilt structure (original nested containers are not mutated);
    non-string leaves (numbers, bools, None) pass through untouched.
    """

    def redact_value(value: Any) -> Any:
        if isinstance(value, str):
            return redact_mcp_text(value)
        if isinstance(value, dict):
            return {k: redact_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [redact_value(v) for v in value]
        return value

    rebuilt = redact_value(payload)
    return rebuilt if isinstance(rebuilt, dict) else {}
