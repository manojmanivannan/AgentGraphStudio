"""Round-trip tests for the 024 migration: tool_nodes gains MCP grant columns.

These tests drive alembic's Python API directly against a throwaway sqlite
file so the column-addition SQL is exercised the same way it would run in a
real deployment: the database is upgraded to the pre-024 schema (023), a
pre-existing author (code) tool row is seeded, then 024 must add the columns
without altering the existing row (null server ref, empty grant list) — the
same pattern as test_migration_019.

Alembic's `env.py` manages its own event loop internally (`asyncio.run(...)`),
so `command.upgrade`/`command.downgrade` must be called from plain sync test
functions, not from within an already-running async test's event loop. Setup
and verification queries use a sync sqlite engine for the same reason.
"""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(async_db_url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    os.environ["DATABASE_URL"] = async_db_url
    return cfg


@pytest.fixture
def migration_db(tmp_path):
    db_path = tmp_path / "migration_024_test.db"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    sync_url = f"sqlite:///{db_path}"
    original_url = os.environ.get("DATABASE_URL")

    cfg = _alembic_config(async_url)
    engine = create_engine(sync_url)

    yield cfg, engine

    engine.dispose()
    if original_url is not None:
        os.environ["DATABASE_URL"] = original_url
    else:
        os.environ.pop("DATABASE_URL", None)


def _seed_code_tool(engine, canvas_id):
    """A pre-024 author (code) tool row, exactly as 023 left it."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tool_nodes (id, canvas_id, name, code, dependencies, args, "
                "position_x, position_y, requires_approval) "
                "VALUES (:id, :canvas_id, 'Calc', :code, '[]', '[]', 0, 0, 0)"
            ),
            {"id": "11111111-1111-1111-1111-111111111111", "canvas_id": canvas_id,
             "code": "def add(a, b): return a + b"},
        )


def _seed_canvas(engine, canvas_id):
    user_id = "22222222-2222-2222-2222-222222222222"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, created_at, updated_at) "
                "VALUES (:id, :email, 'x', datetime('now'), datetime('now'))"
            ),
            {"id": user_id, "email": "seed@example.com"},
        )
        conn.execute(
            text(
                "INSERT INTO canvases (id, owner_id, name, created_at, updated_at) "
                "VALUES (:id, :owner_id, 'c', datetime('now'), datetime('now'))"
            ),
            {"id": canvas_id, "owner_id": user_id},
        )


def _tool_node_columns(engine):
    with engine.connect() as conn:
        return {
            row[1] for row in conn.execute(text("PRAGMA table_info(tool_nodes)"))
        }


def test_upgrade_adds_grant_columns_and_leaves_code_rows_unchanged(migration_db):
    cfg, engine = migration_db

    command.upgrade(cfg, "023")
    canvas_id = "33333333-3333-3333-3333-333333333333"
    _seed_canvas(engine, canvas_id)
    _seed_code_tool(engine, canvas_id)

    command.upgrade(cfg, "024")

    columns = _tool_node_columns(engine)
    assert "mcp_server_id" in columns
    assert "mcp_tools" in columns

    # The pre-existing author-tool row is untouched: no server reference,
    # empty grant list, code payload intact.
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT code, mcp_server_id, mcp_tools FROM tool_nodes "
                "WHERE id = :id"
            ),
            {"id": "11111111-1111-1111-1111-111111111111"},
        ).mappings().one()
    assert row["code"] == "def add(a, b): return a + b"
    assert row["mcp_server_id"] is None
    # Raw sync select: SQLite returns the JSON column as text; postgres as jsonb.
    mcp_tools = row["mcp_tools"]
    if isinstance(mcp_tools, str):
        import json

        mcp_tools = json.loads(mcp_tools)
    assert mcp_tools == []


def test_downgrade_removes_the_grant_columns(migration_db):
    cfg, engine = migration_db

    command.upgrade(cfg, "024")
    command.downgrade(cfg, "023")

    columns = _tool_node_columns(engine)
    assert "mcp_server_id" not in columns
    assert "mcp_tools" not in columns
