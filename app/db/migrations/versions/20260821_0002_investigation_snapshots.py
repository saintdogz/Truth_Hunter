"""Add Phase 2 investigation snapshot tables.

Revision ID: 20260821_0002
Revises: 20260821_0001
Create Date: 2026-08-21
"""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0002"
down_revision = "20260821_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_claim", sa.Text(), nullable=False),
        sa.Column("interpreted_claim", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("claim_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=True),
        sa.Column("supporting_score", sa.Float(), nullable=True),
        sa.Column("contradicting_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("pro_arguments", sa.JSON(), nullable=False),
        sa.Column("contra_arguments", sa.JSON(), nullable=False),
        sa.Column("conflict_detected", sa.Boolean(), nullable=False),
        sa.Column("conflict_summary", sa.Text(), nullable=True),
        sa.Column("conflicting_source_ids", sa.JSON(), nullable=False),
        sa.Column("ai_model", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("search_provider", sa.String(length=100), nullable=True),
        sa.Column("search_languages", sa.JSON(), nullable=False),
        sa.Column("scoring_version", sa.String(length=100), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_investigations_status", "investigations", ["status"])
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sources_domain", "sources", ["domain"])
    op.create_index("ix_sources_investigation_id", "sources", ["investigation_id"])
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.String(length=20), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("quality", sa.Float(), nullable=False),
        sa.Column("independence", sa.Float(), nullable=False),
        sa.Column("recency", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_investigation_id", "evidence", ["investigation_id"])
    op.create_index("ix_evidence_source_id", "evidence", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_source_id", table_name="evidence")
    op.drop_index("ix_evidence_investigation_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_sources_investigation_id", table_name="sources")
    op.drop_index("ix_sources_domain", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_investigations_status", table_name="investigations")
    op.drop_table("investigations")
