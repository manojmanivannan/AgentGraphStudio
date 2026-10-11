"""Per-run MCP session registry (ticket #137, spec §3.2/§4.3).

Worker-facing tests against real Streamable HTTP reference servers: sessions
open concurrently at registry ``open`` time, are reused across tool calls
(one handshake observed server-side), and terminate on ``close``.
"""

import asyncio
import time
import uuid

from canvas_server.mcp_config import McpServerConfig
from canvas_server.runner.mcp_sessions import McpSessionRegistry


def _config(obs, name="ref"):
    return McpServerConfig(
        id=uuid.uuid4(),
        name=name,
        url=obs.url,
        credential_header=None,
        credential_value=None,
    )


async def _call_add(session, a=1, b=2):
    return await session.call_tool("add", arguments={"a": a, "b": b})


class TestSessionLifecycle:
    async def test_open_connects_to_each_referenced_server(self, make_ref_mcp_server):
        servers = [_config(make_ref_mcp_server()) for _ in range(2)]
        reg = McpSessionRegistry(servers=tuple(servers))

        await reg.open([s.id for s in servers])

        for server in servers:
            session = reg.get_session(server.id)
            assert session is not None
            tools = await reg.list_tools(server.id)
            assert "add" in [t.name for t in tools]

        await reg.close()

    async def test_one_handshake_for_many_tool_calls(self, make_ref_mcp_server):
        obs = make_ref_mcp_server()
        server = _config(obs)
        reg = McpSessionRegistry(servers=(server,))

        await reg.open([server.id])

        session = reg.get_session(server.id)
        assert session is not None
        first = reg.get_session(server.id)
        assert first is session  # same ClientSession object every fetch
        for _ in range(3):
            result = await _call_add(session, a=20, b=22)
            assert result.content[0].text == "42"

        assert obs.initialize_count == 1  # one handshake, not per-call

        await reg.close()

    async def test_close_terminates_sessions(self, make_ref_mcp_server):
        obs = make_ref_mcp_server()
        server = _config(obs)
        reg = McpSessionRegistry(servers=(server,))

        await reg.open([server.id])
        assert reg.get_session(server.id) is not None
        assert obs.delete_count == 0

        await reg.close()

        assert reg.get_session(server.id) is None
        # Server side observed the session-terminating DELETE on close.
        assert obs.delete_count == 1

    async def test_open_with_no_server_ids_connects_to_nothing(self, make_ref_mcp_server):
        obs = make_ref_mcp_server()
        reg = McpSessionRegistry(servers=(_config(obs),))

        await reg.open([])

        assert obs.post_count == 0
        assert reg.get_session(uuid.uuid4()) is None

        await reg.close()

    async def test_unknown_server_id_is_skipped(self, make_ref_mcp_server):
        obs = make_ref_mcp_server()
        known = _config(obs)
        reg = McpSessionRegistry(servers=(known,))

        # Nothing raises for an id the registry has no server config for.
        await reg.open([known.id, uuid.uuid4()])

        assert reg.get_session(known.id) is not None
        assert obs.initialize_count == 1
        assert len(reg.server_ids) == 1

        await reg.close()


class TestConcurrentOpens:
    async def test_multiple_servers_open_concurrently(self, make_ref_mcp_server):
        obs_a = make_ref_mcp_server(delay=0.5)
        obs_b = make_ref_mcp_server(delay=0.5)
        servers = [_config(obs_a, "slow-a"), _config(obs_b, "slow-b")]
        reg = McpSessionRegistry(servers=tuple(servers))

        start = time.monotonic()
        await reg.open([s.id for s in servers])
        elapsed = time.monotonic() - start

        # Serial opens would take >= 1s (two 0.5s handshakes back to back);
        # concurrent opens overlap the handshakes server-side.
        (a_start, a_end), (b_start, b_end) = obs_a.initialize_spans[0], obs_b.initialize_spans[0]
        overlap = min(a_end, b_end) - max(a_start, b_start)
        assert overlap > 0, "initializes did not overlap — opens ran serially"
        assert elapsed < 1.0

        assert reg.get_session(servers[0].id) is not None
        assert reg.get_session(servers[1].id) is not None

        await reg.close()


class TestOpenFailurePosture:
    async def test_unreachable_server_records_error_others_still_open(
        self, make_ref_mcp_server
    ):
        obs = make_ref_mcp_server()
        good = _config(obs, "good")
        bad = McpServerConfig(
            id=uuid.uuid4(),
            name="bad",
            url="http://127.0.0.1:1/mcp",  # nothing listens on port 1
            credential_header=None,
            credential_value=None,
        )
        reg = McpSessionRegistry(servers=(good, bad))

        await reg.open([good.id, bad.id])  # never raises

        assert reg.get_session(good.id) is not None
        assert reg.get_session(bad.id) is None
        assert reg.error_for(bad.id) is not None
        assert reg.error_for(good.id) is None

        await reg.close()
        await asyncio.sleep(0)  # let the failed task finish unwinding

    async def test_close_is_idempotent(self, make_ref_mcp_server):
        obs = make_ref_mcp_server()
        server = _config(obs)
        reg = McpSessionRegistry(servers=(server,))

        await reg.open([server.id])
        await reg.close()
        await reg.close()  # no raise

        assert reg.get_session(server.id) is None
