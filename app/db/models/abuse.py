"""Durable privacy-safe abuse-control buckets."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AbuseRateLimit(Base):
    __tablename__ = "abuse_rate_limits"
    __table_args__ = (
        CheckConstraint("attempts >= 1", name="ck_abuse_rate_limits_attempts_positive"),
    )

    action: Mapped[str] = mapped_column(String(40), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer)
