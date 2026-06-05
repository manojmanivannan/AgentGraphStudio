"""add_dependencies_to_tool_nodes

Revision ID: 005
Revises: 004
Create Date: 2026-06-05 12:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.types import JSON

from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_nodes", sa.Column("dependencies", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("tool_nodes", "dependencies")