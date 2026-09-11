"""add_rag_top_k

Revision ID: 018
Revises: 017
Create Date: 2026-09-11 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_nodes",
        sa.Column(
            "rag_top_k",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_nodes", "rag_top_k")
