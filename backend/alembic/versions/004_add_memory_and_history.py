"""add_memory_and_history

Revision ID: 004
Revises: 003
Create Date: 2026-05-28 10:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_nodes",
        sa.Column(
            "enable_memory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "agent_nodes",
        sa.Column(
            "enable_conversation_history",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_nodes", "enable_conversation_history")
    op.drop_column("agent_nodes", "enable_memory")
