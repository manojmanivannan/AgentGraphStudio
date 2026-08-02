"""add_canvas_owner

Revision ID: 014
Revises: 013
Create Date: 2026-08-02 00:00:00.000000

Adds the NOT NULL `owner_id` FK->users (ON DELETE CASCADE) to `canvases`.
Greenfield: the app is unreleased and dev data is dropped/recreated, so there
is no backfill and no bootstrap user (per the out-of-scope decision on the
roadmap). Every canvas belongs to exactly one user; users see only their own.

Uses batch mode so the migration applies on both postgres (native ALTER) and
sqlite (copy-and-move; sqlite cannot add a FK constraint via plain ALTER TABLE).

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("canvases", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("owner_id", sa.Uuid(), nullable=False),
        )
        batch_op.create_foreign_key(
            "fk_canvases_owner_id_users",
            referent_table="users",
            local_cols=["owner_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )
    op.create_index("idx_canvases_owner", "canvases", ["owner_id"])


def downgrade() -> None:
    op.drop_index("idx_canvases_owner", table_name="canvases")
    with op.batch_alter_table("canvases", schema=None) as batch_op:
        batch_op.drop_constraint("fk_canvases_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")