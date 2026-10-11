"""Tests for /api/tools/inspect and /api/tools/test endpoints."""

import shutil

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from canvas_server.database import get_session
from canvas_server.main import app

requires_docker = pytest.mark.skipif(
    not shutil.which("docker"), reason="Docker not installed"
)


@pytest_asyncio.fixture
async def tools_client(fresh_db):
    """HTTP client for the tools API — no DB required but we use fresh_db
    to ensure a clean app state."""
    from canvas_server.database import get_session_factory

    factory = get_session_factory(
        "sqlite+aiosqlite:///test.db"
    )

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestInspectEndpoint:
    """Tests for POST /api/tools/inspect."""

    @requires_docker
    async def test_inspect_simple_function(self, tools_client):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        response = await tools_client.post(
            "/api/tools/inspect",
            json={"code": code},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["function_name"] == "greet"
        assert len(data["arguments"]) == 1
        assert data["arguments"][0]["name"] == "name"
        assert data["arguments"][0]["type_hint"] == "str"

    @requires_docker
    async def test_inspect_multiple_args(self, tools_client):
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        response = await tools_client.post(
            "/api/tools/inspect",
            json={"code": code},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["function_name"] == "add"
        assert len(data["arguments"]) == 2

    async def test_inspect_syntax_error(self, tools_client):
        response = await tools_client.post(
            "/api/tools/inspect",
            json={"code": "def broken(:"},
        )
        assert response.status_code == 400

    async def test_inspect_empty_code(self, tools_client):
        response = await tools_client.post(
            "/api/tools/inspect",
            json={"code": ""},
        )
        # Should return 400 since no function is found
        assert response.status_code == 400


class TestTestEndpoint:
    """Tests for POST /api/tools/test."""

    @requires_docker
    async def test_test_simple_function(self, tools_client):
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": code, "args": {"a": "3", "b": "4"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["output"] == "7"
        assert data["execution_time_ms"] > 0

    @requires_docker
    async def test_test_string_args(self, tools_client):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": code, "args": {"name": "world"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["output"] == "Hello world"

    async def test_test_compilation_error(self, tools_client):
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": "def broken(:", "args": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "syntax" in data["output"].lower() or "SyntaxError" in data["output"]

    @requires_docker
    async def test_test_runtime_error(self, tools_client):
        code = "def boom():\n    raise ValueError('kaboom')"
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": code, "args": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "kaboom" in data["output"]

    @requires_docker
    async def test_test_missing_required_arg(self, tools_client):
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": code, "args": {"a": "1"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "missing" in data["output"].lower() or "b" in data["output"]

    @requires_docker
    async def test_test_default_args(self, tools_client):
        code = 'def greet(name: str = "world") -> str:\n    return f"Hello {name}"'
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": code, "args": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["output"] == "Hello world"

    @requires_docker
    async def test_test_no_args_needed(self, tools_client):
        code = "def answer() -> int:\n    return 42"
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": code, "args": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["output"] == "42"

    @requires_docker
    async def test_test_with_imports_and_globals(self, tools_client):
        code = (
            "from datetime import datetime, timedelta\n"
            "import random\n"
            "def run() -> str:\n"
            "    t = datetime.now()\n"
            "    r = random.uniform(1, 2)\n"
            "    return 'ok'"
        )
        response = await tools_client.post(
            "/api/tools/test",
            json={"code": code, "args": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["output"] == "ok"


# --- MCP branches (#135, spec §6.4) ------------------------------------------
#
# The kind-discriminated request/response: ``kind: "mcp"`` routes to the
# MCP branches (inspect = live server schema; test = two stages, probe then
# live remote call from the backend environment). ``kind: "code"`` (the
# default) keeps the sandbox path byte-for-byte.


async def _create_server_row(session_factory, **overrides):
    """Insert an ``mcp_servers`` row directly (no auth on this endpoint's
    siblings) and return it."""
    from canvas_server.repos.mcp_repo import McpServerRepo

    body = {"name": "Ref Server", "url": "http://invalid.test/mcp"} | overrides
    async with session_factory() as session:
        row = await McpServerRepo(session).create(
            name=body["name"],
            url=body["url"],
            credential_header=body.get("credential_header"),
            credential_value=body.get("credential_value"),
        )
        await session.commit()
        return row


@pytest.fixture
def session_factory(fresh_db):
    from canvas_server.database import get_session_factory

    return get_session_factory("sqlite+aiosqlite:///test.db")


class TestMcpInspectBranch:
    async def test_inspect_code_branch_keeps_kind_code(self, tools_client):
        code = "def answer() -> int:\n    return 42"
        response = await tools_client.post(
            "/api/tools/inspect", json={"code": code}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["kind"] == "code"
        assert data["ok"] is True
        assert data["function_name"] == "answer"

    async def test_inspect_mcp_named_tool_returns_live_server_schema(
        self, tools_client, session_factory, ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/inspect",
            json={
                "kind": "mcp",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "add",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["kind"] == "mcp"
        assert data["ok"] is True
        assert data["server_id"] == str(row.id)
        assert data["latency_ms"] >= 0
        tool = data["tool"]
        assert tool["name"] == "add"
        assert tool["input_schema"]["properties"]["a"]["type"] == "integer"
        assert tool["input_schema"]["properties"]["b"]["type"] == "integer"
        assert data["tools"] == []  # named-tool branch

    async def test_inspect_mcp_without_tool_name_returns_full_catalog(
        self, tools_client, session_factory, ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/inspect",
            json={"kind": "mcp", "mcp_server_id": str(row.id)},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ok"] is True
        assert [t["name"] for t in data["tools"]] == ["add"]
        assert data["tool"] is None

    async def test_inspect_mcp_unknown_server_id_is_404(self, tools_client):
        response = await tools_client.post(
            "/api/tools/inspect",
            json={
                "kind": "mcp",
                "mcp_server_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert response.status_code == 404

    async def test_inspect_mcp_unreachable_server_is_structured_ok_false(
        self, tools_client, session_factory
    ):
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            dead_port = sock.getsockname()[1]

        row = await _create_server_row(
            session_factory, url=f"http://127.0.0.1:{dead_port}/mcp"
        )
        response = await tools_client.post(
            "/api/tools/inspect",
            json={
                "kind": "mcp",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "add",
            },
        )
        # An unreachable server is an honest structured error, not 500.
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "mcp"
        assert data["ok"] is False
        assert data["classification"] == "connection_failure"
        assert data["tool"] is None
        assert data["tools"] == []

    async def test_inspect_mcp_named_tool_not_found_is_structured(
        self, tools_client, session_factory, ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/inspect",
            json={
                "kind": "mcp",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "does_not_exist",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["classification"] == "tool_not_found"
        assert "does_not_exist" in data["detail"]

    async def test_inspect_uses_the_stored_credential_and_never_echoes_it(
        self, tools_client, session_factory, auth_ref_mcp_server
    ):
        row = await _create_server_row(
            session_factory,
            url=auth_ref_mcp_server,
            credential_header="Authorization",
            credential_value="Bearer good-token",
        )
        response = await tools_client.post(
            "/api/tools/inspect",
            json={
                "kind": "mcp",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "echo",
            },
        )
        # The stored credential was used (the auth server would reject
        # otherwise) and never appears anywhere in the response (§5.4).
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ok"] is True
        assert data["tool"]["name"] == "echo"
        assert "good-token" not in response.text


class TestMcpTestBranch:
    async def test_test_code_branch_keeps_kind_code(self, tools_client):
        code = "def answer() -> int:\n    return 42"
        response = await tools_client.post(
            "/api/tools/test", json={"code": code, "args": {}}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["kind"] == "code"

    async def test_probe_stage_returns_probe_result(
        self, tools_client, session_factory, ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/test",
            json={"kind": "mcp", "stage": "probe", "mcp_server_id": str(row.id)},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["kind"] == "mcp"
        assert data["stage"] == "probe"
        assert data["ok"] is True
        assert data["success"] is True
        assert data["server_name"] == "ags-probe-ref"
        assert data["tools"] == ["add"]
        assert data["tool_count"] == 1
        assert data["latency_ms"] >= 0
        assert data["detail"] == "OK"

    async def test_probe_stage_unreachable_is_structured(
        self, tools_client, session_factory
    ):
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            dead_port = sock.getsockname()[1]
        row = await _create_server_row(
            session_factory, url=f"http://127.0.0.1:{dead_port}/mcp"
        )
        response = await tools_client.post(
            "/api/tools/test",
            json={"kind": "mcp", "stage": "probe", "mcp_server_id": str(row.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["success"] is False
        assert data["classification"] == "connection_failure"

    async def test_call_stage_returns_structured_output_blocks(
        self, tools_client, session_factory, ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/test",
            json={
                "kind": "mcp",
                "stage": "call",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "add",
                "mcp_args": {"a": 2, "b": 3},
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["kind"] == "mcp"
        assert data["stage"] == "call"
        assert data["ok"] is True
        assert data["is_error"] is False
        assert data["success"] is True
        assert data["blocks"] == [{"type": "text", "text": "5", "mime_type": None, "resource_uri": None, "placeholder": None}]

    async def test_call_stage_in_band_is_error_reported_as_error(
        self, tools_client, session_factory, error_ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=error_ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/test",
            json={
                "kind": "mcp",
                "stage": "call",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "explode",
                "mcp_args": {},
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        # Executed (ok) — but the in-band isError result is an error, not a
        # success output; "success" must not be True here.
        assert data["ok"] is True
        assert data["is_error"] is True
        assert data["success"] is False
        assert any("boom" in (b["text"] or "") for b in data["blocks"])

    async def test_call_stage_bad_args_never_raise(
        self, tools_client, session_factory, error_ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=error_ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/test",
            json={
                "kind": "mcp",
                "stage": "call",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "add",
                "mcp_args": {"a": "not-an-int", "b": 3},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_error"] is True
        assert data["success"] is False

    async def test_call_stage_unreachable_is_structured(
        self, tools_client, session_factory
    ):
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            dead_port = sock.getsockname()[1]
        row = await _create_server_row(
            session_factory, url=f"http://127.0.0.1:{dead_port}/mcp"
        )
        response = await tools_client.post(
            "/api/tools/test",
            json={
                "kind": "mcp",
                "stage": "call",
                "mcp_server_id": str(row.id),
                "mcp_tool_name": "add",
                "mcp_args": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["is_error"] is False
        assert data["classification"] == "connection_failure"
        assert data["blocks"] == []

    async def test_call_stage_unknown_server_id_is_404(self, tools_client):
        response = await tools_client.post(
            "/api/tools/test",
            json={
                "kind": "mcp",
                "stage": "call",
                "mcp_server_id": "00000000-0000-0000-0000-000000000000",
                "mcp_tool_name": "add",
                "mcp_args": {},
            },
        )
        assert response.status_code == 404

    async def test_call_stage_without_tool_name_is_400(
        self, tools_client, session_factory, ref_mcp_server
    ):
        row = await _create_server_row(session_factory, url=ref_mcp_server)
        response = await tools_client.post(
            "/api/tools/test",
            json={"kind": "mcp", "stage": "call", "mcp_server_id": str(row.id)},
        )
        assert response.status_code == 400

    async def test_credential_override_honored_and_never_echoed(
        self, tools_client, session_factory, auth_ref_mcp_server
    ):
        row = await _create_server_row(
            session_factory,
            url=auth_ref_mcp_server,
            credential_header="Authorization",
            credential_value="Bearer wrong-token",
        )
        body = {
            "kind": "mcp",
            "mcp_server_id": str(row.id),
        }
        # Stored credential is wrong → handshake fails, structured ok=False.
        failed = await tools_client.post(
            "/api/tools/test", json={**body, "stage": "probe"}
        )
        assert failed.status_code == 200
        assert failed.json()["ok"] is False

        # Test-time override (provider convention) succeeds.
        ok = await tools_client.post(
            "/api/tools/test",
            json={
                **body,
                "stage": "probe",
                "credential_value": "Bearer good-token",
            },
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["ok"] is True
        assert "good-token" not in ok.text
