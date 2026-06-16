"""add_enable_plotting

Revision ID: 008
Revises: 007
Create Date: 2026-06-16 16:50:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("agent_nodes")}

    if "enable_plotting" not in existing_columns:
        op.add_column(
            "agent_nodes",
            sa.Column(
                "enable_plotting",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("agent_nodes")}

    if "enable_plotting" in existing_columns:
        op.drop_column("agent_nodes", "enable_plotting")
