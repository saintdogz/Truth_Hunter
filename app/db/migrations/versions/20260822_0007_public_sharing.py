"""Add private-by-default public sharing and reporting.

Revision ID: 20260822_0007
Revises: 20260822_0006
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op

revision = "20260822_0007"
down_revision = "20260822_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("investigations", sa.Column("public_slug", sa.String(length=64), nullable=True))
    op.create_index("ix_investigations_is_public", "investigations", ["is_public"])
    op.create_index(
        "uq_investigations_public_slug",
        "investigations",
        ["public_slug"],
        unique=True,
    )
    op.create_table(
        "public_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("reporter_session_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('SPAM', 'ABUSE', 'PERSONAL_INFORMATION', 'HARMFUL', 'COPYRIGHT', 'OTHER')",
            name="ck_public_reports_reason",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'REVIEWED', 'ACTIONED')", name="ck_public_reports_status"
        ),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "investigation_id", "reporter_session_id", name="uq_public_report_session"
        ),
    )
    op.create_index("ix_public_reports_investigation_id", "public_reports", ["investigation_id"])
    op.create_index(
        "ix_public_reports_reporter_session_id", "public_reports", ["reporter_session_id"]
    )
    op.create_index("ix_public_reports_status", "public_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_public_reports_status", table_name="public_reports")
    op.drop_index("ix_public_reports_reporter_session_id", table_name="public_reports")
    op.drop_index("ix_public_reports_investigation_id", table_name="public_reports")
    op.drop_table("public_reports")
    op.drop_index("uq_investigations_public_slug", table_name="investigations")
    op.drop_index("ix_investigations_is_public", table_name="investigations")
    op.drop_column("investigations", "public_slug")
    op.drop_column("investigations", "is_public")
