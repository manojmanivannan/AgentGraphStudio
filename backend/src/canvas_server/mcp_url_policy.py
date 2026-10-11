"""URL policy for MCP server registrations (spec §5.1, ticket #129).

Only ``http(s)://`` endpoints are accepted; every other scheme is hard-rejected
on every write path. Plain ``http://`` is allowed with a warning (localhost dev
servers need it), and there is deliberately **no** IP/SSRF guard: server URLs
are workspace-operator-configured — the same self-configured posture as
``llm_base_url``. Open egress is documented in ``docs/ARCHITECTURE.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = ("https", "http")


@dataclass(frozen=True)
class McpUrlValidation:
    ok: bool
    error: str | None = None
    warning: str | None = None


def validate_mcp_server_url(url: str) -> McpUrlValidation:
    """Validate an MCP endpoint URL, returning an error and/or warning."""
    if not url or not url.strip():
        return McpUrlValidation(
            ok=False, error="URL is required: provide an http(s):// endpoint."
        )

    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in _ALLOWED_SCHEMES or not parts.netloc:
        if not parts.scheme.lower():
            return McpUrlValidation(
                ok=False,
                error=(
                    f"URL must be a valid http(s):// endpoint; got no scheme in "
                    f'"{url.strip()}".'
                ),
            )
        return McpUrlValidation(
            ok=False,
            error=(
                f"Unsupported URL scheme \"{parts.scheme}\" for an MCP server: "
                "only http:// and https:// endpoints are allowed."
            ),
        )

    if parts.scheme.lower() == "http":
        return McpUrlValidation(
            ok=True,
            warning=(
                'URL uses plain "http://". This is permitted (e.g. for localhost '
                "dev servers), but the credential header would be sent unencrypted."
            ),
        )

    return McpUrlValidation(ok=True)
