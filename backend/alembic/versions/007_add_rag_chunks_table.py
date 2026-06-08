"""add_rag_chunks_table

Revision ID: 007
Revises: 006
Create Date: 2026-06-08 13:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create agent_document_chunks table
    # We define a temporary column type for embedding to be replaced or modified depending on dialect
    op.create_table(
        "agent_document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canvas_id", sa.Uuid(), nullable=False),
        sa.Column("agent_node_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["canvas_id"], ["canvases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_node_id"], ["agent_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["agent_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    if dialect_name == "postgresql":
        # Drop the temporary NullType column and create the pgvector vector column
        op.execute("ALTER TABLE agent_document_chunks DROP COLUMN embedding")
        op.execute("ALTER TABLE agent_document_chunks ADD COLUMN embedding vector")
        op.execute("ALTER TABLE agent_document_chunks ALTER COLUMN embedding SET NOT NULL")

    op.create_index("idx_agent_document_chunks_canvas", "agent_document_chunks", ["canvas_id"])
    op.create_index("idx_agent_document_chunks_agent", "agent_document_chunks", ["agent_node_id"])
    op.create_index("idx_agent_document_chunks_document", "agent_document_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_document_chunks_document", table_name="agent_document_chunks")
    op.drop_index("idx_agent_document_chunks_agent", table_name="agent_document_chunks")
    op.drop_index("idx_agent_document_chunks_canvas", table_name="agent_document_chunks")
    op.drop_table("agent_document_chunks")
