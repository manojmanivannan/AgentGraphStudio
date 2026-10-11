"""Round-trip tests for the 025 migration: tool_nodes gains ``mcp_seen_tools``.

The enablement-history baseline for the editor's NEW-badge diff (#134,
spec §6.2/decision #126 §2): the union of tool names this node's picker has
ever rendered from a live catalog fetch. Without it every un-enabled tool
would flash NEW on every reload, and tools the user explicitly dropped would
reappear as forever-new suggestions. Same alembic-Python-API pattern as
test_migration_024: upgrade to the pre-025 schema, seed a pre-existing tool
row, then 025 must add the column without altering the row.
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
    db_path = tmp_path / "migration_025_test.db"
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


def _seed_code_tool(engine, canvas_id):
    """A pre-025 mcp-era tool row, exactly as 024 left it."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tool_nodes (id, canvas_id, name, code, dependencies, args, "
                "position_x, position_y, requires_approval, mcp_tools) "
                "VALUES (:id, :canvas_id, 'Calc', :code, '[]', '[]', 0, 0, 0, '[]')"
            ),
            {"id": "11111111-1111-1111-1111-111111111111", "canvas_id": canvas_id,
             "code": "def add(a, b): return a + b"},
        )


def _tool_node_columns(engine):
    with engine.connect() as conn:
        return {
            row[1] for row in conn.execute(text("PRAGMA table_info(tool_nodes)"))
        }


def test_upgrade_adds_seen_tools_and_leaves_existing_rows_unchanged(migration_db):
    cfg, engine = migration_db

    command.upgrade(cfg, "024")
    canvas_id = "33333333-3333-3333-3333-333333333333"
    _seed_canvas(engine, canvas_id)
    _seed_code_tool(engine, canvas_id)

    command.upgrade(cfg, "025")

    assert "mcp_seen_tools" in _tool_node_columns(engine)

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT code, mcp_seen_tools FROM tool_nodes WHERE id = :id"),
            {"id": "11111111-1111-1111-1111-111111111111"},
        ).mappings().one()
    assert row["code"] == "def add(a, b): return a + b"
    seen = row["mcp_seen_tools"]
    if isinstance(seen, str):
        import json

        seen = json.loads(seen)
    assert seen == []


def test_downgrade_removes_seen_tools(migration_db):
    cfg, engine = migration_db

    command.upgrade(cfg, "025")
    command.downgrade(cfg, "024")

    assert "mcp_seen_tools" not in _tool_node_columns(engine)