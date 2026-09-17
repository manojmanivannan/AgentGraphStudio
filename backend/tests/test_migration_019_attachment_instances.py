"""Round-trip tests for the 019 migration: conversation_plots -> attachment_instances.

These tests drive alembic's Python API directly against a throwaway sqlite
file so the backfill/rewrite/downgrade SQL is exercised the same way it would
run in a real deployment, rather than relying on manual smoke-testing alone.

Alembic's `env.py` manages its own event loop internally (`asyncio.run(...)`),
so `command.upgrade`/`command.downgrade` must be called from plain sync test
functions, not from within an already-running async test's event loop. Setup
and verification queries use a sync sqlite engine for the same reason.
"""

import os
import uuid
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
    db_path = tmp_path / "migration_019_test.db"
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


def _seed_conversation(engine, conversation_id, canvas_id):
    user_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, created_at, updated_at) "
                "VALUES (:id, :email, 'x', datetime('now'), datetime('now'))"
            ),
            {"id": user_id, "email": f"{user_id}@example.com"},
        )
        conn.execute(
            text(
                "INSERT INTO canvases (id, owner_id, name, created_at, updated_at) "
                "VALUES (:id, :owner_id, 'c', datetime('now'), datetime('now'))"
            ),
            {"id": canvas_id, "owner_id": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO conversations (id, canvas_id, name, status, created_at, updated_at) "
                "VALUES (:id, :canvas_id, 'conv', 'active', datetime('now'), datetime('now'))"
            ),
            {"id": conversation_id, "canvas_id": canvas_id},
        )


def test_upgrade_backfills_plots_and_rewrites_message_content(migration_db):
    cfg, engine = migration_db

    # Land on the pre-019 schema.
    command.upgrade(cfg, "018")

    conversation_id = str(uuid.uuid4())
    plot_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    canvas_id = str(uuid.uuid4())

    _seed_conversation(engine, conversation_id, canvas_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversation_plots (id, conversation_id, format, content, created_at) "
                "VALUES (:id, :conversation_id, 'png', X'89504e47', datetime('now'))"
            ),
            {"id": plot_id, "conversation_id": conversation_id},
        )
        conn.execute(
            text(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (:id, :conversation_id, 'assistant', :content, datetime('now'))"
            ),
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "content": f"![Plot](/api/plots/{plot_id})",
            },
        )

    command.upgrade(cfg, "019")

    with engine.begin() as conn:
        table_names = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "attachment_instances" in table_names
        assert "conversation_plots" not in table_names

        rows = conn.execute(
            text(
                "SELECT conversation_id, file_type, source, format, size_bytes "
                "FROM attachment_instances WHERE id = :id"
            ),
            {"id": plot_id},
        ).mappings().all()
        assert len(rows) == 1
        row = rows[0]
        assert row["conversation_id"] == conversation_id
        assert row["file_type"] == "image"
        assert row["source"] == "agent_output"
        assert row["format"] == "png"
        assert row["size_bytes"] == 4

        message_content = conn.execute(
            text("SELECT content FROM messages WHERE id = :id"), {"id": message_id}
        ).scalar_one()
        assert message_content == f"![Plot](/api/attachments/{plot_id})"


def test_upgrade_is_safe_to_rerun(migration_db):
    """Re-running upgrade() after it already completed must not error or duplicate rows."""
    cfg, engine = migration_db

    command.upgrade(cfg, "018")

    conversation_id = str(uuid.uuid4())
    plot_id = str(uuid.uuid4())
    canvas_id = str(uuid.uuid4())

    _seed_conversation(engine, conversation_id, canvas_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversation_plots (id, conversation_id, format, content, created_at) "
                "VALUES (:id, :conversation_id, 'png', X'89504e47', datetime('now'))"
            ),
            {"id": plot_id, "conversation_id": conversation_id},
        )

    command.upgrade(cfg, "019")
    # Running the same upgrade step again should be a no-op, not an error.
    command.upgrade(cfg, "019")

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id FROM attachment_instances WHERE id = :id"), {"id": plot_id}
        ).fetchall()
        assert len(rows) == 1


def test_downgrade_restores_conversation_plots(migration_db):
    cfg, engine = migration_db

    command.upgrade(cfg, "019")

    conversation_id = str(uuid.uuid4())
    canvas_id = str(uuid.uuid4())
    attachment_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    _seed_conversation(engine, conversation_id, canvas_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO attachment_instances "
                "(id, conversation_id, file_type, source, format, content, size_bytes, created_at) "
                "VALUES (:id, :conversation_id, 'image', 'agent_output', 'png', X'89504e47', 4, datetime('now'))"
            ),
            {"id": attachment_id, "conversation_id": conversation_id},
        )
        conn.execute(
            text(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (:id, :conversation_id, 'assistant', :content, datetime('now'))"
            ),
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "content": f"![Plot](/api/attachments/{attachment_id})",
            },
        )

    command.downgrade(cfg, "018")

    with engine.begin() as conn:
        table_names = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "conversation_plots" in table_names
        assert "attachment_instances" not in table_names

        rows = conn.execute(
            text("SELECT id FROM conversation_plots WHERE id = :id"),
            {"id": attachment_id},
        ).fetchall()
        assert len(rows) == 1

        message_content = conn.execute(
            text("SELECT content FROM messages WHERE id = :id"), {"id": message_id}
        ).scalar_one()
        assert message_content == f"![Plot](/api/plots/{attachment_id})"

    # And back up again, to confirm the round trip is fully reversible.
    command.upgrade(cfg, "019")
    with engine.begin() as conn:
        table_names_after = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "attachment_instances" in table_names_after
