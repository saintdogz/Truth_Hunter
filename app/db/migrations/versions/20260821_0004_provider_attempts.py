"""Add provider attempt audit trail.

Revision ID: 20260821_0004
Revises: 20260821_0003
Create Date: 2026-08-21
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0004"
down_revision = "20260821_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column(
            "ai_provider_attempts",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.alter_column("investigations", "ai_provider_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("investigations", "ai_provider_attempts")
