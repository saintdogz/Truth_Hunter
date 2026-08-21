"""Add Phase 4 users and investigation ownership.

Revision ID: 20260821_0005
Revises: 20260821_0004
Create Date: 2026-08-21
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0005"
down_revision = "20260821_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("google_subject", sa.String(length=255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_subject"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.add_column("investigations", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column("investigations", sa.Column("session_id", sa.String(128), nullable=True))
    op.create_index("ix_investigations_user_id", "investigations", ["user_id"])
    op.create_index("ix_investigations_session_id", "investigations", ["session_id"])
    op.create_foreign_key(
        "fk_investigations_user_id_users",
        "investigations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_investigations_user_id_users", "investigations", type_="foreignkey")
    op.drop_index("ix_investigations_session_id", table_name="investigations")
    op.drop_index("ix_investigations_user_id", table_name="investigations")
    op.drop_column("investigations", "session_id")
    op.drop_column("investigations", "user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
