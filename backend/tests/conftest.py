import os
import uuid
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://canvas:canvas@localhost:5432/canvas_test",
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


@pytest_asyncio.fixture
async def fresh_db():
    from canvas_server.database import Base, get_engine

    _reset_engine_and_factory()
    engine = get_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TYPE IF EXISTS agent_type_enum CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS edge_type_enum CASCADE"))
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TYPE IF EXISTS agent_type_enum CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS edge_type_enum CASCADE"))
    _reset_engine_and_factory()


@pytest_asyncio.fixture
async def test_session(fresh_db):
    from canvas_server.database import get_session_factory
    factory = get_session_factory(TEST_DB_URL)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_client(fresh_db):
    from canvas_server.main import app
    from canvas_server.database import get_session, get_session_factory

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
async def blank_canvas(test_session):
    from canvas_server.repos.canvas_repo import CanvasRepo
    repo = CanvasRepo(test_session)
    canvas = await repo.create(name="Test Canvas")
    return canvas


@pytest_asyncio.fixture
async def canvas_with_nodes(test_session):
    from canvas_server.repos.canvas_repo import CanvasRepo
    from canvas_server.models.api import AgentNodeInput, ToolNodeInput, EdgeInput

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
    )
    return canvas
