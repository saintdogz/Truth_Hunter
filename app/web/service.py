"""Web-facing Phase 3 service around the Phase 2 pipeline."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.db.models import Investigation, Source
from app.db.session import get_engine
from app.investigation.factory import create_pipeline
from app.investigation.models import ClaimInterpretation
from app.investigation.pipeline import InvestigationPipelineError
from app.investigation.repository import InvestigationNotFoundError, InvestigationRepository

logger = logging.getLogger(__name__)


class InvestigationWebService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def recover_interrupted(self) -> int:
        with Session(get_engine()) as session:
            recovered = InvestigationRepository(session).recover_interrupted()
        if recovered:
            logger.warning("Marked %s interrupted investigations as terminal", recovered)
        return recovered

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
            except InvestigationPipelineError:
                logger.warning("Investigation %s ended in a terminal failure", investigation_id)
            finally:
                await pipeline.aclose()

    def get(self, investigation_id: UUID) -> Investigation:
        with Session(get_engine()) as session:
            statement = (
                select(Investigation)
                .where(Investigation.id == investigation_id)
                .options(
                    selectinload(Investigation.sources).selectinload(Source.evidence),
                    selectinload(Investigation.evidence),
                    selectinload(Investigation.feedback),
                )
            )
            investigation = session.scalar(statement)
            if investigation is None:
                raise InvestigationNotFoundError(str(investigation_id))
            session.expunge(investigation)
            return investigation

    def get_public(self, public_slug: str) -> Investigation:
        with Session(get_engine()) as session:
            statement = (
                select(Investigation)
                .where(
                    Investigation.public_slug == public_slug,
                    Investigation.is_public.is_(True),
                    Investigation.status == "COMPLETED",
                )
                .options(
                    selectinload(Investigation.sources).selectinload(Source.evidence),
                    selectinload(Investigation.evidence),
                    selectinload(Investigation.feedback),
                )
            )
            investigation = session.scalar(statement)
            if investigation is None:
                raise InvestigationNotFoundError(public_slug)
            session.expunge(investigation)
            return investigation
