"""add MCP grant columns to tool_nodes

Revision ID: 024
Revises: 023
Create Date: 2026-10-11 00:00:00.000000

MCP-backed Tool Node domain model (#132, spec §2.1): a Tool Node grants a
subset of one registered server's tools. ``mcp_server_id`` is a nullable FK
to ``mcp_servers.id`` (non-null ⇒ MCP-backed node; ``code``/``args`` stay
empty — no schema snapshot is persisted on the node). ``mcp_tools`` is the
enabled-tools selection, ``[{name, requires_approval}]`` (per-tool approval
granularity, #119 Q9). Existing author (code) tool rows are untouched: they
keep a NULL server reference and an empty grant list.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a table to add an FK-bearing column
    # in place; the copy-and-move rebuild works on postgres too. Constraint
    # names are explicit per the 014 precedent.
    with op.batch_alter_table("tool_nodes", schema=None) as batch:
        batch.add_column(sa.Column("mcp_server_id", sa.Uuid(), nullable=True))
        # NOT NULL with a server_default so existing rows migrate to an empty
        # selection rather than failing the ALTER.
        batch.add_column(
            sa.Column(
                "mcp_tools", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            )
        )
        batch.create_foreign_key(
            "fk_tool_nodes_mcp_server_id_mcp_servers",
            referent_table="mcp_servers",
            local_cols=["mcp_server_id"],
            remote_cols=["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("tool_nodes", schema=None) as batch:
        batch.drop_constraint(
            "fk_tool_nodes_mcp_server_id_mcp_servers", type_="foreignkey"
        )
        batch.drop_column("mcp_tools")
        batch.drop_column("mcp_server_id")
