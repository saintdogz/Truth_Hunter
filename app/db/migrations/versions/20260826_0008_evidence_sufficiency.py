"""Persist the deterministic evidence-sufficiency decision.

Revision ID: 20260826_0008
Revises: 20260822_0007
Create Date: 2026-08-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_0008"
down_revision = "20260822_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("evidence_sufficient", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        """
        UPDATE investigations AS investigation
        SET evidence_sufficient = (
            investigation.status = 'COMPLETED'
            AND investigation.supporting_score IS NOT NULL
            AND (
                SELECT count(*) FROM evidence
                WHERE evidence.investigation_id = investigation.id
                  AND evidence.position <> 'NEUTRAL'
                  AND evidence.relevance >= 0.5
                  AND evidence.quality >= 0.45
            ) >= 2
            AND (
                SELECT count(*) FROM evidence
                WHERE evidence.investigation_id = investigation.id
                  AND evidence.position <> 'NEUTRAL'
                  AND evidence.relevance >= 0.5
                  AND evidence.quality >= 0.45
                  AND evidence.independence >= 0.55
            ) >= 2
        )
        """
    )
    op.alter_column("investigations", "evidence_sufficient", server_default=None)


def downgrade() -> None:
    op.drop_column("investigations", "evidence_sufficient")
