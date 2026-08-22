"""Ownership-bound public sharing and abuse reporting."""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Investigation, PublicReport

REPORT_REASONS = {"SPAM", "ABUSE", "PERSONAL_INFORMATION", "HARMFUL", "COPYRIGHT", "OTHER"}


class SharingError(ValueError):
    pass


def owns_investigation(
    investigation: Investigation, *, user_id: str | None, session_id: str | None
) -> bool:
    return (user_id is not None and str(investigation.user_id) == user_id) or (
        session_id is not None and investigation.session_id == session_id
    )


def set_public(
    session: Session,
    investigation: Investigation,
    *,
    enabled: bool,
    user_id: str | None,
    session_id: str | None,
) -> Investigation:
    if investigation.status != "COMPLETED" or not owns_investigation(
        investigation, user_id=user_id, session_id=session_id
    ):
        raise SharingError("Investigation is not shareable")
    if investigation.public_slug is None:
        investigation.public_slug = secrets.token_urlsafe(24)
    investigation.is_public = enabled
    session.add(investigation)
    session.commit()
    session.refresh(investigation)
    return investigation


def submit_public_report(
    session: Session,
    investigation: Investigation,
    *,
    reason: str,
    reporter_session_id: str,
) -> PublicReport:
    normalized = reason.strip().upper()
    if not investigation.is_public or normalized not in REPORT_REASONS:
        raise SharingError("Invalid public report")
    existing = session.scalar(
        select(PublicReport).where(
            PublicReport.investigation_id == investigation.id,
            PublicReport.reporter_session_id == reporter_session_id,
        )
    )
    if existing is None:
        existing = PublicReport(
            investigation_id=investigation.id,
            reporter_session_id=reporter_session_id,
            reason=normalized,
            status="OPEN",
        )
    else:
        existing.reason = normalized
        existing.status = "OPEN"
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing
