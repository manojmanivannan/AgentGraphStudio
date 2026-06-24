"""add_enable_hitl

Revision ID: 011
Revises: 010
Create Date: 2026-06-24 12:15:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_nodes",
        sa.Column("enable_hitl", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "tool_nodes",
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("agent_nodes", "enable_hitl")
    op.drop_column("tool_nodes", "requires_approval")
