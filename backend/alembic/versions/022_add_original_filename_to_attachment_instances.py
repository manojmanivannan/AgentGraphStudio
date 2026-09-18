"""add_original_filename_to_attachment_instances

Revision ID: 022
Revises: 021
Create Date: 2026-09-18 00:00:00.000000

Preserves the filename a user uploaded an attachment under (e.g.
"city_name.json"), distinct from the declared Attachment node's own `name`
(a stable canvas label, e.g. "CityName") — #90. Materializing a `file_path`
delivery into the sandbox now uses this when present, falling back to the
node's name (+ a file_type-derived extension) for agent-produced attachments
that were never uploaded.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachment_instances",
        sa.Column("original_filename", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attachment_instances", "original_filename")
