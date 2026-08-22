"""Add one-click investigation feedback.

Revision ID: 20260822_0006
Revises: 20260821_0005
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op

revision = "20260822_0006"
down_revision = "20260821_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("value", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("value IN ('HELPFUL', 'NOT_HELPFUL')", name="ck_feedback_value"),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "investigation_id", "session_id", name="uq_feedback_investigation_session"
        ),
        sa.UniqueConstraint("investigation_id", "user_id", name="uq_feedback_investigation_user"),
    )
    op.create_index("ix_feedback_investigation_id", "feedback", ["investigation_id"])
    op.create_index("ix_feedback_session_id", "feedback", ["session_id"])
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_user_id", table_name="feedback")
    op.drop_index("ix_feedback_session_id", table_name="feedback")
    op.drop_index("ix_feedback_investigation_id", table_name="feedback")
    op.drop_table("feedback")
