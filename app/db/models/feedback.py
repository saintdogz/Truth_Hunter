"""Privacy-conscious one-click investigation feedback."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("value IN ('HELPFUL', 'NOT_HELPFUL')", name="ck_feedback_value"),
        UniqueConstraint("investigation_id", "user_id", name="uq_feedback_investigation_user"),
        UniqueConstraint(
            "investigation_id", "session_id", name="uq_feedback_investigation_session"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    value: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    investigation: Mapped["Investigation"] = relationship(back_populates="feedback")


from app.db.models.investigation import Investigation  # noqa: E402
