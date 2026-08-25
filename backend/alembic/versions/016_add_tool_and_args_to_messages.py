"""add_tool_and_args_to_messages

Revision ID: 016
Revises: 015
Create Date: 2026-08-25 00:00:00.000000

Adds ``tool`` (String) and ``args`` (JSON) columns to ``messages`` table
so that tool executions and generated code / arguments can be persisted and
re-rendered in the UI across sessions.

Idempotent: each column is only added if absent, so re-running is safe.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("messages")}

    if "tool" not in existing_columns:
        op.add_column(
            "messages",
            sa.Column("tool", sa.String(255), nullable=True),
        )

    if "args" not in existing_columns:
        op.add_column(
            "messages",
            sa.Column("args", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("messages")}

    if "args" in existing_columns:
        op.drop_column("messages", "args")

    if "tool" in existing_columns:
        op.drop_column("messages", "tool")
