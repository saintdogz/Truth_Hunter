"""Private ownership, public sharing, and report safety tests."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Investigation, PublicReport
from app.sharing.service import (
    SharingError,
    owns_investigation,
    set_public,
    submit_public_report,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def test_investigation_ownership_is_bound_to_user_or_guest_session() -> None:
    user_id = uuid4()
    user_investigation = Investigation(
        original_claim="User claim", status="COMPLETED", user_id=user_id
    )
    guest_investigation = Investigation(
        original_claim="Guest claim", status="COMPLETED", session_id="owner-session"
    )

    assert owns_investigation(user_investigation, user_id=str(user_id), session_id=None)
    assert owns_investigation(guest_investigation, user_id=None, session_id="owner-session")
    assert not owns_investigation(guest_investigation, user_id=None, session_id="different-session")
    assert not owns_investigation(user_investigation, user_id=str(uuid4()), session_id=None)


def test_public_slug_is_stable_across_unpublish_and_republish(session: Session) -> None:
    investigation = Investigation(
        original_claim="Shareable claim", status="COMPLETED", session_id="owner-session"
    )
    session.add(investigation)
    session.commit()

    set_public(
        session,
        investigation,
        enabled=True,
        user_id=None,
        session_id="owner-session",
    )
    slug = investigation.public_slug
    assert investigation.is_public
    assert slug is not None and len(slug) >= 24

    set_public(
        session,
        investigation,
        enabled=False,
        user_id=None,
        session_id="owner-session",
    )
    set_public(
        session,
        investigation,
        enabled=True,
        user_id=None,
        session_id="owner-session",
    )

    assert investigation.is_public
    assert investigation.public_slug == slug
    with pytest.raises(SharingError):
        set_public(
            session,
            investigation,
            enabled=False,
            user_id=None,
            session_id="attacker-session",
        )


def test_public_report_is_duplicate_safe_and_rejects_invalid_reasons(session: Session) -> None:
    investigation = Investigation(
        original_claim="Public claim",
        status="COMPLETED",
        is_public=True,
        public_slug="stable-public-slug",
    )
    session.add(investigation)
    session.commit()

    first = submit_public_report(
        session, investigation, reason="SPAM", reporter_session_id="reporter-session"
    )
    second = submit_public_report(
        session, investigation, reason="COPYRIGHT", reporter_session_id="reporter-session"
    )

    assert first.id == second.id
    assert second.reason == "COPYRIGHT"
    assert session.scalar(select(func.count()).select_from(PublicReport)) == 1
    with pytest.raises(SharingError):
        submit_public_report(
            session, investigation, reason="NOT_A_REASON", reporter_session_id="other-session"
        )


def test_private_investigation_cannot_be_reported(session: Session) -> None:
    investigation = Investigation(original_claim="Private claim", status="COMPLETED")
    session.add(investigation)
    session.commit()

    with pytest.raises(SharingError):
        submit_public_report(
            session, investigation, reason="SPAM", reporter_session_id="reporter-session"
        )
