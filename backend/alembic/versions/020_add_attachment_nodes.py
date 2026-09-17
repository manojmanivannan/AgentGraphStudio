"""add_attachment_nodes

Revision ID: 020
Revises: 019
Create Date: 2026-09-15 00:00:00.000000

Introduces the ``attachment_nodes`` table for the new Attachment canvas node
type (#76/#80): a typed data artifact node with no direction field of its
own — whether it acts as an input or output is derived purely from the
``produces``/``consumes`` edges connecting it to agent nodes. The existing
``edges.edge_type`` column is a plain string with no DB-level enum
constraint, so no migration is needed there to support the new values.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachment_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canvas_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default="Attachment"),
        sa.Column("file_type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("position_x", sa.Double(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Double(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["canvas_id"], ["canvases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_attachment_nodes_canvas", "attachment_nodes", ["canvas_id"])


def downgrade() -> None:
    op.drop_index("idx_attachment_nodes_canvas", table_name="attachment_nodes")
    op.drop_table("attachment_nodes")
