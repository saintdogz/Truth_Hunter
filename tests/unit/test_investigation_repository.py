"""Atomic investigation workflow transition tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Investigation
from app.investigation.repository import InvestigationRepository


def test_only_one_confirmation_can_claim_investigation_start() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        investigation = Investigation(
            original_claim="A claim",
            interpreted_claim="A claim",
            language="en",
            claim_type="factual",
            status="AWAITING_CONFIRMATION",
        )
        session.add(investigation)
        session.commit()
        investigation_id = investigation.id

    with Session(engine) as first_session:
        assert InvestigationRepository(first_session).claim_start(investigation_id)
    with Session(engine) as duplicate_session:
        assert not InvestigationRepository(duplicate_session).claim_start(investigation_id)

    with Session(engine) as check_session:
        assert check_session.get(Investigation, investigation_id).status == "SEARCHING"  # type: ignore[union-attr]

    engine.dispose()


def test_failed_limit_check_can_release_start_claim() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        investigation = Investigation(original_claim="A claim", status="AWAITING_CONFIRMATION")
        session.add(investigation)
        session.commit()
        investigation_id = investigation.id
        repository = InvestigationRepository(session)

        assert repository.claim_start(investigation_id)
        assert repository.release_start_claim(investigation_id)
        assert not repository.release_start_claim(investigation_id)
        assert repository.get(investigation_id).status == "AWAITING_CONFIRMATION"

    engine.dispose()
