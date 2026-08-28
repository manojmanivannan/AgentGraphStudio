"""add_provider_settings

Revision ID: 017
Revises: 016
Create Date: 2026-08-28 00:00:00.000000

Adds the singleton ``provider_settings`` table backing the in-app LLM provider
configuration. The ``.env`` LLM_*/MEM0_* variables remain the seed/fallback used
until a row exists.

Idempotent: the table is only created if absent.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "provider_settings" in inspector.get_table_names():
        return

    op.create_table(
        "provider_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile", sa.String(64), nullable=False, server_default="custom"),
        sa.Column(
            "llm_provider_type", sa.String(64), nullable=False, server_default="ollama"
        ),
        sa.Column("llm_base_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("llm_api_key", sa.String(512), nullable=False, server_default=""),
        sa.Column("llm_model", sa.String(255), nullable=False, server_default=""),
        sa.Column("mem0_llm_model", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "mem0_embedder_model", sa.String(255), nullable=False, server_default=""
        ),
        sa.Column(
            "mem0_embedder_dimensions", sa.Integer(), nullable=False, server_default="768"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_settings")
