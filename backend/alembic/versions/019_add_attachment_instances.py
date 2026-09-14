"""add_attachment_instances

Revision ID: 019
Revises: 018
Create Date: 2026-09-14 00:00:00.000000

Introduces a unified ``attachment_instances`` table that generalizes the
plot-only ``conversation_plots`` table (#79/#83) to arbitrary attachment
content. Existing ``conversation_plots`` rows are backfilled in place,
preserving their ids, typed as ``image``/``agent_output``. Any persisted
message content referencing the removed ``/api/plots/{id}`` endpoint is
rewritten to point at the new ``/api/attachments/{id}`` endpoint — no
back-compat alias is kept.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "attachment_instances" not in existing_tables:
        op.create_table(
            "attachment_instances",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("conversation_id", sa.Uuid(), nullable=False),
            sa.Column("attachment_node_id", sa.Uuid(), nullable=True),
            sa.Column(
                "file_type", sa.String(length=20), nullable=False, server_default="image"
            ),
            sa.Column(
                "source", sa.String(length=20), nullable=False, server_default="agent_output"
            ),
            sa.Column("produced_by_run_id", sa.Uuid(), nullable=True),
            sa.Column("format", sa.String(length=10), nullable=False, server_default="png"),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["produced_by_run_id"], ["durable_runs.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_attachment_instances_conversation",
            "attachment_instances",
            ["conversation_id"],
        )

    if "conversation_plots" in existing_tables:
        # Backfill: every legacy plot row becomes an image/agent_output
        # attachment instance, preserving its original id. The NOT EXISTS
        # guard makes this safe to re-run if a prior attempt inserted rows
        # but failed before dropping conversation_plots.
        op.execute(
            sa.text(
                """
                INSERT INTO attachment_instances
                    (id, conversation_id, file_type, source, format, content, size_bytes, created_at)
                SELECT cp.id, cp.conversation_id, 'image', 'agent_output', cp.format, cp.content,
                       length(cp.content), cp.created_at
                FROM conversation_plots cp
                WHERE NOT EXISTS (
                    SELECT 1 FROM attachment_instances ai WHERE ai.id = cp.id
                )
                """
            )
        )

        # Rewrite persisted message content pointing at the removed
        # plot-specific endpoint to the new unified attachment endpoint.
        op.execute(
            sa.text(
                "UPDATE messages SET content = REPLACE(content, '/api/plots/', '/api/attachments/') "
                "WHERE content LIKE '%/api/plots/%'"
            )
        )

        op.drop_index("idx_conversation_plots_conversation", table_name="conversation_plots")
        op.drop_table("conversation_plots")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "conversation_plots" not in existing_tables:
        op.create_table(
            "conversation_plots",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("conversation_id", sa.Uuid(), nullable=False),
            sa.Column("format", sa.String(length=10), nullable=False, server_default="png"),
            sa.Column("content", sa.LargeBinary(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_conversation_plots_conversation", "conversation_plots", ["conversation_id"]
        )

    if "attachment_instances" in existing_tables:
        op.execute(
            sa.text(
                """
                INSERT INTO conversation_plots (id, conversation_id, format, content, created_at)
                SELECT ai.id, ai.conversation_id, ai.format, ai.content, ai.created_at
                FROM attachment_instances ai
                WHERE ai.source = 'agent_output' AND ai.file_type = 'image'
                AND NOT EXISTS (
                    SELECT 1 FROM conversation_plots cp WHERE cp.id = ai.id
                )
                """
            )
        )

        op.execute(
            sa.text(
                "UPDATE messages SET content = REPLACE(content, '/api/attachments/', '/api/plots/') "
                "WHERE content LIKE '%/api/attachments/%'"
            )
        )

        op.drop_index(
            "idx_attachment_instances_conversation", table_name="attachment_instances"
        )
        op.drop_table("attachment_instances")
