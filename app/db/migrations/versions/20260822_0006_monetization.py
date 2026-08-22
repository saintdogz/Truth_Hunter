"""Add Phase 5 payment and credit ledger.

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
    op.add_column(
        "users",
        sa.Column(
            "free_investigation_used", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "investigations",
        sa.Column("is_unlocked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "investigations", sa.Column("entitlement_kind", sa.String(length=24), nullable=True)
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("anonymized_owner", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_order_id", sa.String(length=128), nullable=False),
        sa.Column("provider_capture_id", sa.String(length=128), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("provider_capture_id"),
    )
    for column in (
        "user_id",
        "anonymized_owner",
        "provider_order_id",
        "provider_capture_id",
        "status",
    ):
        op.create_index(f"ix_payments_{column}", "payments", [column])

    op.create_table(
        "credit_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("remaining", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "payment_id", "status"):
        op.create_index(f"ix_credit_grants_{column}", "credit_grants", [column])

    op.create_table(
        "credit_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("grant_id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["grant_id"], ["credit_grants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investigation_id"),
    )
    for column in ("user_id", "grant_id", "investigation_id", "status"):
        op.create_index(f"ix_credit_reservations_{column}", "credit_reservations", [column])

    op.create_table(
        "free_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_hash"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("investigation_id"),
    )
    for column in ("session_hash", "user_id", "investigation_id"):
        op.create_index(f"ix_free_entitlements_{column}", "free_entitlements", [column])

    op.create_table(
        "monetization_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("provider_event_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    for column in ("user_id", "payment_id", "provider_event_id", "event_type"):
        op.create_index(f"ix_monetization_events_{column}", "monetization_events", [column])


def downgrade() -> None:
    op.drop_table("monetization_events")
    op.drop_table("free_entitlements")
    op.drop_table("credit_reservations")
    op.drop_table("credit_grants")
    op.drop_table("payments")
    op.drop_column("investigations", "entitlement_kind")
    op.drop_column("investigations", "is_unlocked")
    op.drop_column("users", "free_investigation_used")
