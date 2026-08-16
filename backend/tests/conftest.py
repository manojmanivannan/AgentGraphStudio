import asyncio
import contextlib
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///test.db",
)


def _reset_engine_and_factory():
    from canvas_server.database import reset_session_factory
    reset_session_factory()
    os.environ["DATABASE_URL"] = TEST_DB_URL


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def _test_db_url():
    _reset_engine_and_factory()


@pytest.fixture(autouse=True)
def mock_embedder(monkeypatch):
    class MockEmbedder:
        def __call__(self, texts):
            from canvas_server.config import settings
            dims = settings.mem0_embedder_dimensions
            return [[0.1] * dims for _ in texts]

    monkeypatch.setattr(
        "canvas_server.runner.rag_helper.get_embedder",
        lambda: MockEmbedder(),
    )



@pytest_asyncio.fixture
async def fresh_db():
    from canvas_server.database import Base, async_reset_session_factory, get_engine

    _reset_engine_and_factory()
    engine = get_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_reset_session_factory()


@pytest_asyncio.fixture
async def test_session(fresh_db):
    from canvas_server.database import get_session_factory
    factory = get_session_factory(TEST_DB_URL)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_client(fresh_db):
    from canvas_server.database import get_session, get_session_factory
    from canvas_server.main import app

    factory = get_session_factory(TEST_DB_URL)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(test_session):
    """A persisted User row used as the owner for repo-level canvas fixtures.

    Repo/unit tests that don't go through the HTTP layer still need a real
    owner because ``canvases.owner_id`` is NOT NULL with a FK->users.
    """
    from canvas_server.models.auth import User

    user = User(
        email=f"blank_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
    )
    test_session.add(user)
    await test_session.flush()
    return user


@pytest_asyncio.fixture
async def blank_canvas(test_session, test_user):
    from canvas_server.repos.canvas_repo import CanvasRepo
    repo = CanvasRepo(test_session)
    canvas = await repo.create(name="Test Canvas", owner_id=test_user.id)
    return canvas


@pytest_asyncio.fixture
async def authed_client(fresh_db):
    """An httpx AsyncClient that has registered + logged in via the REAL cookie
    flow (cookie jar), so protected routes authenticate normally.

    No auth is bypassed: get_current_user reads the session cookie and resolves
    it against the real sessions table. Only get_session is overridden to point
    at the test sqlite DB (same pattern as test_client). No auth-disable flag.
    """
    from canvas_server.database import get_session, get_session_factory
    from canvas_server.main import app

    factory = get_session_factory(TEST_DB_URL)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        creds = {
            "email": f"user_{uuid.uuid4().hex[:12]}@example.com",
            "password": "super-secret-123",
        }
        # Same-origin Origin header satisfies the CSRF check on state-changing routes.
        r = await client.post(
            "/api/auth/register", json=creds, headers={"Origin": "http://test"}
        )
        assert r.status_code == 201, r.text
        r = await client.post(
            "/api/auth/login", json=creds, headers={"Origin": "http://test"}
        )
        assert r.status_code == 200, r.text
        # Sanity: the cookie jar now holds the session cookie.
        client.auth_email = creds["email"]  # type: ignore[attr-defined]
        client.auth_password = creds["password"]  # type: ignore[attr-defined]
        me = await client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        client.auth_user_id = uuid.UUID(me.json()["id"])  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_authed_client(fresh_db):
    """Factory yielding fresh authenticated AsyncClients (one per call).

    For cross-user isolation tests: call ``alice = await make_authed_client()``
    and ``bob = await make_authed_client()`` to get two independent cookie jars
    backed by two different registered users. Each client exposes
    ``auth_user_id`` / ``auth_email``. All clients share the test ``get_session``
    override; cleanup closes them at teardown.
    """
    from httpx import ASGITransport, AsyncClient

    from canvas_server.database import get_session, get_session_factory
    from canvas_server.main import app

    factory = get_session_factory(TEST_DB_URL)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    created: list[AsyncClient] = []

    async def _make() -> AsyncClient:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        creds = {
            "email": f"user_{uuid.uuid4().hex[:12]}@example.com",
            "password": "super-secret-123",
        }
        r = await client.post(
            "/api/auth/register", json=creds, headers={"Origin": "http://test"}
        )
        assert r.status_code == 201, r.text
        r = await client.post(
            "/api/auth/login", json=creds, headers={"Origin": "http://test"}
        )
        assert r.status_code == 200, r.text
        me = await client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        client.auth_user_id = uuid.UUID(me.json()["id"])  # type: ignore[attr-defined]
        client.auth_email = creds["email"]  # type: ignore[attr-defined]
        created.append(client)
        return client

    yield _make

    for client in created:
        await client.aclose()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def owned_canvas(authed_client, test_session):
    """A canvas owned by ``authed_client``'s user, created via the repo.

    HTTP tests that act on a canvas through the API need the canvas to belong
    to the authenticated user; otherwise every protected route 404s.
    """
    from canvas_server.repos.canvas_repo import CanvasRepo

    repo = CanvasRepo(test_session)
    return await repo.create(
        name="Test Canvas", owner_id=authed_client.auth_user_id
    )


@pytest_asyncio.fixture
async def authed_sync_client(fresh_db):
    """Sync TestClient analogue of ``authed_client`` for the execute-route tests.

    Registers + logs in a user via the real cookie flow, overrides ``get_session``
    to the test sqlite DB, and exposes ``auth_user_id`` so fakes can stub the
    ownership chain (``canvas.owner_id == auth_user_id``). The execute routes
    resolve the current user via ``Depends(get_current_user)`` (which uses the
    overridden ``get_session``) while their repo work still goes through the
    per-test monkeypatched ``get_session_factory`` — the two sessions are
    independent, so auth and faked repos coexist.
    """
    from fastapi.testclient import TestClient

    from canvas_server.database import get_session, get_session_factory
    from canvas_server.main import app

    factory = get_session_factory(TEST_DB_URL)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # Use the TestClient default host ("testserver") and a matching Origin so the
    # session cookie scopes to "testserver" — required because
    # TestClient.websocket_connect() hardcodes "ws://testserver" and only sends
    # cookies scoped to that host. ("http://test" would scope the cookie to
    # "test" and the WS upgrade would arrive without it.) The matching Origin
    # also satisfies verify_origin's same-origin CSRF check.
    client = TestClient(app)
    creds = {
        "email": f"user_{uuid.uuid4().hex[:12]}@example.com",
        "password": "super-secret-123",
    }
    r = client.post(
        "/api/auth/register", json=creds, headers={"Origin": "http://testserver"}
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/auth/login", json=creds, headers={"Origin": "http://testserver"}
    )
    assert r.status_code == 200, r.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    client.auth_user_id = uuid.UUID(me.json()["id"])  # type: ignore[attr-defined]
    client.auth_email = creds["email"]  # type: ignore[attr-defined]
    yield client
    client.close()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_authed_sync_client(fresh_db):
    """Sync TestClient analogue of ``make_authed_client`` (issue #37).

    Factory yielding fresh authenticated sync ``TestClient``s (one per call), each
    with its own cookie jar backed by a different registered user. Required for
    cross-user WebSocket tests: the sync TestClient is the only WS-capable client
    available (httpx AsyncClient has no websocket_connect). Each client exposes
    ``auth_user_id`` / ``auth_email`` and uses ``base_url="http://test"`` so the
    same-origin Origin header passes the CSRF check. All clients share the test
    ``get_session`` override; cleanup closes them at teardown.
    """
    from fastapi.testclient import TestClient

    from canvas_server.database import get_session, get_session_factory
    from canvas_server.main import app

    factory = get_session_factory(TEST_DB_URL)

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    created: list[TestClient] = []

    def _make() -> TestClient:
        # Default host "testserver" + matching Origin so the session cookie
        # scopes to "testserver" and is sent on websocket_connect (see
        # authed_sync_client for why).
        client = TestClient(app)
        creds = {
            "email": f"user_{uuid.uuid4().hex[:12]}@example.com",
            "password": "super-secret-123",
        }
        r = client.post(
            "/api/auth/register", json=creds, headers={"Origin": "http://testserver"}
        )
        assert r.status_code == 201, r.text
        r = client.post(
            "/api/auth/login", json=creds, headers={"Origin": "http://testserver"}
        )
        assert r.status_code == 200, r.text
        me = client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        client.auth_user_id = uuid.UUID(me.json()["id"])  # type: ignore[attr-defined]
        client.auth_email = creds["email"]  # type: ignore[attr-defined]
        created.append(client)
        return client

    yield _make

    for client in created:
        client.close()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def canvas_with_nodes(test_session, test_user):
    from canvas_server.models.api import AgentNodeInput, EdgeInput, ToolNodeInput
    from canvas_server.repos.canvas_repo import CanvasRepo

    master_id = uuid.uuid4()
    math_id = uuid.uuid4()
    weather_id = uuid.uuid4()
    calc_tool_id = uuid.uuid4()

    agents = [
        AgentNodeInput(id=master_id, name="Master", role="Router", agent_type="router", model_name="ollama:llama3.1"),
        AgentNodeInput(id=math_id, name="MathAgent", role="Math expert", agent_type="worker", model_name="ollama:llama3.1"),
        AgentNodeInput(id=weather_id, name="WeatherAgent", role="Weather expert", agent_type="worker", model_name="ollama:llama3.1"),
    ]
    tools = [
        ToolNodeInput(id=calc_tool_id, name="Calculator", code="def add(a: int, b: int) -> int:\n    return a + b"),
    ]
    edges = [
        EdgeInput(id=uuid.uuid4(), source_node_id=master_id, target_node_id=math_id, edge_type="handoff"),
        EdgeInput(id=uuid.uuid4(), source_node_id=master_id, target_node_id=weather_id, edge_type="handoff"),
        EdgeInput(id=uuid.uuid4(), source_node_id=math_id, target_node_id=calc_tool_id, edge_type="tool_access"),
    ]

    repo = CanvasRepo(test_session)
    canvas = await repo.create_full(
        name="Test Workflow",
        agents=agents,
        tools=tools,
        edges=edges,
        owner_id=test_user.id,
    )
    return canvas


@pytest_asyncio.fixture(scope="session", autouse=True)
async def autouse_sandbox():
    import logging
    import shutil
    import subprocess
    from pathlib import Path

    from canvas_server.sandbox import SANDBOX_FLOOR_IMAGE, SandboxManager

    if not shutil.which("docker"):
        yield None
        return

    # The locked default pool runs on the baked-floor image (matplotlib + plotly
    # + numpy pre-installed, network_mode="none"). Ensure it exists before
    # initializing the pool so @requires_docker tests can acquire containers.
    # Idempotent: a quick `docker image inspect` skips the build when present.
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile_ctx = repo_root / "sandbox"
    try:
        subprocess.run(
            ["docker", "image", "inspect", SANDBOX_FLOOR_IMAGE],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            subprocess.run(
                ["docker", "build", "-t", SANDBOX_FLOOR_IMAGE, str(dockerfile_ctx)],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            stderr = getattr(e, "stderr", b"") or b""
            logging.getLogger("canvas_server.tests").warning(
                "Failed to build sandbox floor image %s: %s\n%s",
                SANDBOX_FLOOR_IMAGE,
                e,
                stderr.decode("utf-8", errors="replace"),
            )

    manager = SandboxManager.get()
    try:
        await manager.initialize_pool()
    except Exception as e:
        logging.getLogger("canvas_server.tests").warning(
            f"Failed to initialize sandbox pool in tests: {e}"
        )
    yield manager
    with contextlib.suppress(Exception):
        await manager.shutdown()

