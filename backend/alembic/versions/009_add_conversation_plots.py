"""add_conversation_plots

Revision ID: 009
Revises: 008
Create Date: 2026-06-18 19:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create conversation_plots table
    op.create_table(
        "conversation_plots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False, server_default="png"),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_conversation_plots_conversation", "conversation_plots", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("idx_conversation_plots_conversation", table_name="conversation_plots")
    op.drop_table("conversation_plots")
