"""One-click feedback ownership and duplicate-safety tests."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Feedback, Investigation, User
from app.feedback.service import FeedbackError, submit_feedback


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def test_guest_feedback_is_created_once_and_can_be_changed(session: Session) -> None:
    guest_id = "guest-session"
    investigation = Investigation(
        original_claim="A test claim",
        status="COMPLETED",
        session_id=guest_id,
    )
    session.add(investigation)
    session.commit()

    first = submit_feedback(session, investigation, "HELPFUL", user_id=None, session_id=guest_id)
    second = submit_feedback(
        session, investigation, "NOT_HELPFUL", user_id=None, session_id=guest_id
    )

    assert first.id == second.id
    assert second.value == "NOT_HELPFUL"
    assert session.scalar(select(func.count()).select_from(Feedback)) == 1


def test_user_feedback_requires_investigation_ownership(session: Session) -> None:
    owner = User(email="owner@example.com", email_verified=True)
    investigation = Investigation(original_claim="A test claim", status="COMPLETED", user=owner)
    session.add(investigation)
    session.commit()

    with pytest.raises(FeedbackError, match="not available"):
        submit_feedback(
            session,
            investigation,
            "HELPFUL",
            user_id=uuid4(),
            session_id=None,
        )


def test_feedback_rejects_invalid_value_and_incomplete_investigation(
    session: Session,
) -> None:
    investigation = Investigation(
        original_claim="A test claim",
        status="SEARCHING",
        session_id="guest-session",
    )
    session.add(investigation)
    session.commit()

    with pytest.raises(FeedbackError, match="Invalid"):
        submit_feedback(session, investigation, "MAYBE", user_id=None, session_id="guest-session")
    with pytest.raises(FeedbackError, match="completed"):
        submit_feedback(session, investigation, "HELPFUL", user_id=None, session_id="guest-session")
