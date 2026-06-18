"""add_is_entry_point

Revision ID: 010
Revises: 009
Create Date: 2026-06-18 21:35:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_nodes",
        sa.Column("is_entry_point", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("agent_nodes", "is_entry_point")
