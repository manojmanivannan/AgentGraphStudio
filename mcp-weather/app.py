# Local MCP test server for the docker compose stack (ticket: mcp-client-support
# dev tooling). Runs as the optional `mcp-weather` compose service (profile
# "mcp") on agent_network, so the containerized backend probes it at
# http://mcp-weather:8000/mcp with no host.docker.internal / firewall plumbing.
#
# Keep in sync with the standalone host variant (/tmp/app.py during dev): the
# only difference is the transport-security allowlist — service-name Host
# headers ("mcp-weather:8000") replace the host.docker.internal case.

import os

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

AUTH_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "my-secret-token")

# `stateless_http=True` makes every request self-contained — no per-session
# state to go stale between the app's short-lived probe/run connections.
mcp = FastMCP(
    "Weather Server",
    stateless_http=True,
    # The SDK's default anti-rebind allowlist only accepts localhost-family
    # Host headers; in-stack requests arrive with "Host: mcp-weather:8000"
    # (the compose service name).
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "localhost:*",
            "127.0.0.1:*",
            "[::1]:*",
            "host.docker.internal:*",
            "mcp-weather:*",
        ],
    ),
)

@mcp.tool()
async def get_current_weather(latitude: float, longitude: float) -> str:
    """Fetch current weather for given latitude and longitude coordinates."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": True,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current_weather", {})
        return (
            f"Temperature: {current.get('temperature')}°C, "
            f"Windspeed: {current.get('windspeed')} km/h, "
            f"Weather Code: {current.get('weathercode')}"
        )

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth_header = request.headers.get("Authorization")
        if auth_header == f"Bearer {AUTH_TOKEN}":
            return await call_next(request)
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)