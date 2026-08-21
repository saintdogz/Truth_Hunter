"""Add Phase 3 confirmation state.

Revision ID: 20260821_0003
Revises: 20260821_0002
Create Date: 2026-08-21
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0003"
down_revision = "20260821_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("correction_used", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("investigations", "correction_used", server_default=None)


def downgrade() -> None:
    op.drop_column("investigations", "correction_used")
