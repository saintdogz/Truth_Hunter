"""Web-facing Phase 3 service around the Phase 2 pipeline."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.db.models import Investigation
from app.db.session import get_engine
from app.investigation.factory import create_pipeline
from app.investigation.models import ClaimInterpretation
from app.investigation.repository import InvestigationNotFoundError


class InvestigationWebService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def interpret(
        self,
        original_claim: str,
        *,
        user_id: UUID | None = None,
        session_id: str | None = None,
    ) -> tuple[UUID, ClaimInterpretation]:
        with Session(get_engine()) as session:
            pipeline = create_pipeline(self._settings, session)
            try:
                return await pipeline.create_and_interpret(
                    original_claim, user_id=user_id, session_id=session_id
                )
            finally:
                await pipeline.aclose()

    async def investigate(
        self, investigation_id: UUID, confirmed_claim: str, *, corrected: bool
    ) -> None:
        with Session(get_engine()) as session:
            pipeline = create_pipeline(self._settings, session)
            try:
                await pipeline.investigate_confirmed(
                    investigation_id, confirmed_claim, corrected=corrected
                )
            finally:
                await pipeline.aclose()

    def get(self, investigation_id: UUID) -> Investigation:
        with Session(get_engine()) as session:
            statement = (
                select(Investigation)
                .where(Investigation.id == investigation_id)
                .options(
                    selectinload(Investigation.sources),
                    selectinload(Investigation.evidence),
                    selectinload(Investigation.feedback),
                )
            )
            investigation = session.scalar(statement)
            if investigation is None:
                raise InvestigationNotFoundError(str(investigation_id))
            session.expunge(investigation)
            return investigation
