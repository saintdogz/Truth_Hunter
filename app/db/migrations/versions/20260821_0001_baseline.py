"""Establish the Phase 1 migration baseline.

Revision ID: 20260821_0001
Revises:
Create Date: 2026-08-21
"""

revision = "20260821_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No domain tables are introduced during Phase 1."""


def downgrade() -> None:
    """The empty baseline requires no database changes."""
