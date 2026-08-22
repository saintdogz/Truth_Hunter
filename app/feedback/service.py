"""Duplicate-safe, ownership-bound investigation feedback."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Feedback, Investigation

ALLOWED_FEEDBACK = {"HELPFUL", "NOT_HELPFUL"}


class FeedbackError(ValueError):
    """Feedback was invalid or not authorized for this actor."""


def submit_feedback(
    session: Session,
    investigation: Investigation,
    value: str,
    *,
    user_id: UUID | None,
    session_id: str | None,
) -> Feedback:
    if value not in ALLOWED_FEEDBACK:
        raise FeedbackError("Invalid feedback value")
    if investigation.status != "COMPLETED":
        raise FeedbackError("Feedback requires a completed investigation")

    owned_by_user = user_id is not None and investigation.user_id == user_id
    owned_by_session = session_id is not None and investigation.session_id == session_id
    if not (owned_by_user or owned_by_session):
        raise FeedbackError("Feedback is not available for this investigation")

    actor_filter = (
        Feedback.user_id == user_id if owned_by_user else Feedback.session_id == session_id
    )
    existing = session.scalar(
        select(Feedback).where(
            Feedback.investigation_id == investigation.id,
            actor_filter,
        )
    )
    if existing is None:
        existing = Feedback(
            investigation_id=investigation.id,
            user_id=user_id if owned_by_user else None,
            session_id=session_id if owned_by_session and not owned_by_user else None,
            value=value,
        )
        session.add(existing)
    else:
        existing.value = value
    session.commit()
    session.refresh(existing)
    return existing
