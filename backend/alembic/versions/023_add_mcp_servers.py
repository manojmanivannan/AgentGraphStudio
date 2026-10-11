"""add_mcp_servers

Revision ID: 023
Revises: 022
Create Date: 2026-10-11 00:00:00.000000

Workspace-global registry of external MCP servers (#129, spec §2.1): one row
per registered endpoint, with a credential header/value pair stored in
plaintext at the same trust level as provider_settings. The credential value
is DB-only — the API never returns it.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2083), nullable=False),
        sa.Column("credential_header", sa.String(64), nullable=True),
        sa.Column("credential_value", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("mcp_servers")
