"""add mcp_seen_tools (enablement history) to tool_nodes

Revision ID: 025
Revises: 024
Create Date: 2026-10-11 00:00:00.000000

The NEW-badge diff baseline for the editor's live-catalog checklist (#134,
spec §6.2, decision #126 §2): the union of tool names this node's picker has
ever rendered from a live catalog fetch. The catalog itself is never
persisted (#126 §1) — only the names-that-were-seen history, so a tool the
server newly exposes (or the user explicitly dropped) no longer flashes NEW
forever. Existing rows land as an empty history; nothing else changes.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode per the 024 precedent (SQLite cannot ALTER a table in place;
    # the copy-and-move rebuild works on postgres too).
    with op.batch_alter_table("tool_nodes", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "mcp_seen_tools",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("tool_nodes", schema=None) as batch:
        batch.drop_column("mcp_seen_tools")