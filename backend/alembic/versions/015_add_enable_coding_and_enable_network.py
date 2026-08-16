"""add_enable_coding_and_enable_network

Revision ID: 015
Revises: 014
Create Date: 2026-08-16 00:00:00.000000

Adds two NOT NULL BOOLEAN columns to ``agent_nodes``, same shape as
``enable_plotting`` (nullable=False, server_default false):

* ``enable_coding`` — wired up end-to-end in this ticket (worker-only
  ``run_code`` tool).
* ``enable_network`` — schema-only placeholder; its behavior is wired up in a
  later ticket. Adding both in one migration avoids a second table rewrite.

Idempotent: each column is only added if absent, so re-running is safe.

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("agent_nodes")}

    if "enable_coding" not in existing_columns:
        op.add_column(
            "agent_nodes",
            sa.Column(
                "enable_coding",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    if "enable_network" not in existing_columns:
        op.add_column(
            "agent_nodes",
            sa.Column(
                "enable_network",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("agent_nodes")}

    if "enable_network" in existing_columns:
        op.drop_column("agent_nodes", "enable_network")

    if "enable_coding" in existing_columns:
        op.drop_column("agent_nodes", "enable_coding")