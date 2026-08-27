"""Add durable privacy-safe public abuse limits.

Revision ID: 20260827_0009
Revises: 20260826_0008
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_0009"
down_revision = "20260826_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abuse_rate_limits",
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempts >= 1", name="ck_abuse_rate_limits_attempts_positive"),
        sa.PrimaryKeyConstraint("action", "key_hash"),
    )
    op.create_index(
        "ix_abuse_rate_limits_window_started_at",
        "abuse_rate_limits",
        ["window_started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_abuse_rate_limits_window_started_at", table_name="abuse_rate_limits")
    op.drop_table("abuse_rate_limits")
