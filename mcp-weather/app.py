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
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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
async def get_current_weather(
    latitude: float, longitude: float
) -> dict[str, list[float | str]]:
    """Fetch hourly temperature data for a latitude/longitude pair."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m",
        "current_weather": True,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        forecast = data.get("hourly", {})
        timestamps = forecast.get("time", [])
        temperatures = forecast.get("temperature_2m", [])
        current_time = data.get("current_weather", {}).get("time")

        start_index = 0
        if current_time is not None:
            for i, timestamp in enumerate(timestamps):
                if timestamp >= current_time:
                    start_index = i
                    break

        next_10 = min(10, len(timestamps) - start_index)
        hours = [
            timestamp.split("T", 1)[1] if "T" in timestamp else timestamp
            for timestamp in timestamps[start_index : start_index + next_10]
        ]
        current_time_list = [current_time] if current_time is not None else []
        return {
            "current_time": current_time_list,
            "hours": hours,
            "temps": temperatures[start_index : start_index + next_10],
        }


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth_header = request.headers.get("Authorization")
        if auth_header == f"Bearer {AUTH_TOKEN}":
            return await call_next(request)
        return JSONResponse({"error": "Unauthorized"}, status_code=401)


app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)
