"""add_args_to_tool_nodes

Revision ID: 003
Revises: 002
Create Date: 2026-05-27 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tool_nodes', sa.Column('args', JSON, nullable=True))


def downgrade() -> None:
    op.drop_column('tool_nodes', 'args')
