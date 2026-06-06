"""Tests for /api/tools/inspect and /api/tools/test endpoints."""

import shutil

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from canvas_server.main import app
from canvas_server.database import get_session

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