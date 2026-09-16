"""add_attachment_delivery_method_and_consumed_at

Revision ID: 021
Revises: 020
Create Date: 2026-09-16 00:00:00.000000

Runtime consumption of chat-uploaded input attachments (#88):

- ``attachment_nodes.delivery_method`` — per-node preference (``inline`` |
  ``file_path``) for how a declared input attachment is handed to the
  consuming agent. The framework falls back automatically per-consumer when
  the preference isn't feasible (see ``attachment_delivery.py``).
- ``attachment_instances.consumed_at`` — set once a chat-uploaded input
  attachment has been delivered to its consuming agent, so a later turn in
  the same conversation never re-delivers it.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachment_nodes",
        sa.Column(
            "delivery_method", sa.String(20), nullable=False, server_default="inline"
        ),
    )
    op.add_column(
        "attachment_instances",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attachment_instances", "consumed_at")
    op.drop_column("attachment_nodes", "delivery_method")
