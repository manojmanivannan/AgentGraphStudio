"""initial — single migration matching current model state

Revision ID: 001
Revises:
Create Date: 2026-05-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canvases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canvas_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("agent_type", sa.String(20), nullable=False),
        sa.Column("position_x", sa.Double(), nullable=False),
        sa.Column("position_y", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(["canvas_id"], ["canvases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_nodes_canvas", "agent_nodes", ["canvas_id"])

    op.create_table(
        "tool_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canvas_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("position_x", sa.Double(), nullable=False),
        sa.Column("position_y", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(["canvas_id"], ["canvases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tool_nodes_canvas", "tool_nodes", ["canvas_id"])

    op.create_table(
        "edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canvas_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("edge_type", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["canvas_id"], ["canvases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_edges_canvas", "edges", ["canvas_id"])


def downgrade() -> None:
    op.drop_table("edges")
    op.drop_table("tool_nodes")
    op.drop_table("agent_nodes")
    op.drop_table("canvases")
