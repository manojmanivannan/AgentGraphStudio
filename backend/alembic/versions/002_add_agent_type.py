"""add agent_type to agent_nodes

Revision ID: 002
Revises: 001
Create Date: 2025-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    agent_type_enum = postgresql.ENUM("worker", "router", name="agent_type_enum", create_type=False)
    agent_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "agent_nodes",
        sa.Column("agent_type", agent_type_enum, nullable=False, server_default="worker"),
    )


def downgrade() -> None:
    op.drop_column("agent_nodes", "agent_type")
    op.execute("DROP TYPE IF EXISTS agent_type_enum")
