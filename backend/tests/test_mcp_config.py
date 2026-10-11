"""Process-local MCP registry cache (provider-config conventions, #129).

Reads are synchronous (the runner/probe sit deep insideDSPy-shaped call
stacks), so the resolved server list lives in a process-local cache that the
write routes refresh explicitly — mirroring refresh_provider_config.
"""

import pytest

from canvas_server.mcp_config import (
    get_mcp_servers,
    refresh_mcp_servers,
    reset_mcp_servers_cache,
)
from canvas_server.models.mcp import McpServer


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_mcp_servers_cache()
    yield
    reset_mcp_servers_cache()


async def test_cache_is_empty_before_first_refresh(test_session):
    assert get_mcp_servers() == ()


async def test_refresh_loads_all_rows(test_session):
    repo_session = test_session
    repo_session.add_all(
        [
            McpServer(name="alpha", url="https://a.example/mcp"),
            McpServer(
                name="beta",
                url="http://localhost:8000/mcp",
                credential_header="X-Api-Key",
                credential_value="secret-value",
            ),
        ]
    )
    await repo_session.flush()

    servers = await refresh_mcp_servers(repo_session)
    assert [s.name for s in get_mcp_servers()] == ["alpha", "beta"]

    beta = servers[1]
    assert beta.url == "http://localhost:8000/mcp"
    assert beta.credential_header == "X-Api-Key"
    assert beta.credential_value == "secret-value"


async def test_reset_clears_the_cache(test_session):
    test_session.add(McpServer(name="alpha", url="https://a.example/mcp"))
    await test_session.flush()
    await refresh_mcp_servers(test_session)
    assert get_mcp_servers() != ()
    reset_mcp_servers_cache()
    assert get_mcp_servers() == ()


async def test_refresh_picks_up_writes_but_not_unrefreshed_ones(test_session):
    await refresh_mcp_servers(test_session)
    assert get_mcp_servers() == ()

    test_session.add(McpServer(name="late", url="https://late.example/mcp"))
    await test_session.flush()
    # Unrefreshed: cache still stale — writes refresh it explicitly.
    assert get_mcp_servers() == ()
    await refresh_mcp_servers(test_session)
    assert [s.name for s in get_mcp_servers()] == ["late"]
