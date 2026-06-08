"""add_rag_support

Revision ID: 006
Revises: 005
Create Date: 2026-06-08 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add enable_rag column to agent_nodes
    op.add_column(
        "agent_nodes",
        sa.Column(
            "enable_rag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "agent_nodes",
        sa.Column(
            "rag_chunk_size",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1000"),
        ),
    )

    # Create agent_documents table
    op.create_table(
        "agent_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canvas_id", sa.Uuid(), nullable=False),
        sa.Column("agent_node_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["canvas_id"], ["canvases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_node_id"], ["agent_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_agent_documents_canvas", "agent_documents", ["canvas_id"])
    op.create_index("idx_agent_documents_agent", "agent_documents", ["agent_node_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_documents_agent", table_name="agent_documents")
    op.drop_index("idx_agent_documents_canvas", table_name="agent_documents")
    op.drop_table("agent_documents")
    op.drop_column("agent_nodes", "rag_chunk_size")
    op.drop_column("agent_nodes", "enable_rag")
