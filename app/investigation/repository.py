"""Persistence operations for immutable investigation snapshots."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import EvidenceRecord, Investigation, Source
from app.investigation.models import (
    AssessmentDraft,
    ClaimInterpretation,
    EvidenceAssessment,
    InvestigationSummary,
    SourceDocument,
)


class InvestigationNotFoundError(LookupError):
    pass


class InvestigationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        original_claim: str,
        *,
        user_id: UUID | None = None,
        session_id: str | None = None,
    ) -> Investigation:
        investigation = Investigation(
            original_claim=original_claim,
            status="CREATED",
            user_id=user_id,
            session_id=session_id if user_id is None else None,
        )
        self._session.add(investigation)
        self._session.commit()
        self._session.refresh(investigation)
        return investigation

    def get(self, investigation_id: UUID) -> Investigation:
        investigation = self._session.get(Investigation, investigation_id)
        if investigation is None:
            raise InvestigationNotFoundError(str(investigation_id))
        return investigation

    def set_status(self, investigation_id: UUID, status: str) -> None:
        investigation = self.get(investigation_id)
        investigation.status = status
        self._session.commit()

    def save_interpretation(
        self, investigation_id: UUID, interpretation: ClaimInterpretation
    ) -> None:
        investigation = self.get(investigation_id)
        investigation.interpreted_claim = interpretation.interpreted_claim
        investigation.language = interpretation.language
        investigation.claim_type = interpretation.claim_type.value
        investigation.status = "AWAITING_CONFIRMATION"
        self._session.commit()

    def add_source(self, investigation_id: UUID, document: SourceDocument) -> Source:
        source = Source(
            investigation_id=investigation_id,
            url=str(document.url),
            title=document.title,
            domain=document.domain,
            publisher=document.publisher,
            published_at=document.published_at,
            extracted_text=document.text,
        )
        self._session.add(source)
        self._session.commit()
        self._session.refresh(source)
        return source

    def save_confirmed_claim(
        self, investigation_id: UUID, confirmed_claim: str, *, corrected: bool = False
    ) -> None:
        investigation = self.get(investigation_id)
        if corrected and investigation.correction_used:
            raise ValueError("The single claim correction has already been used")
        investigation.interpreted_claim = confirmed_claim
        investigation.correction_used = investigation.correction_used or corrected
        self._session.commit()

    def add_evidence(
        self, investigation_id: UUID, source: Source, item: EvidenceAssessment
    ) -> None:
        source.source_type = item.source_type.value
        source.quality_score = item.quality
        source.relevance_score = item.relevance
        source.excerpt = item.excerpt
        record = EvidenceRecord(
            investigation_id=investigation_id,
            source_id=source.id,
            position=item.position.value,
            strength=item.strength,
            relevance=item.relevance,
            quality=item.quality,
            independence=item.independence,
            recency=item.recency,
            summary=item.summary,
        )
        self._session.add(record)
        self._session.commit()

    def complete(
        self,
        investigation_id: UUID,
        assessment: AssessmentDraft,
        summary: InvestigationSummary,
        *,
        ai_model: str,
        ai_provider_attempts: list[dict[str, object]],
        prompt_version: str,
        search_provider: str,
        source_count: int,
    ) -> None:
        investigation = self.get(investigation_id)
        investigation.status = "COMPLETED"
        investigation.verdict = assessment.verdict.value
        investigation.supporting_score = assessment.balance.supporting
        investigation.contradicting_score = assessment.balance.contradicting
        investigation.confidence = assessment.confidence.value
        investigation.summary = summary.explanation
        investigation.pro_arguments = summary.pro_arguments
        investigation.contra_arguments = summary.contra_arguments
        investigation.conflict_detected = assessment.conflict.detected
        investigation.conflict_summary = assessment.conflict.summary
        investigation.conflicting_source_ids = [
            str(source_id) for source_id in assessment.conflict.conflicting_source_ids
        ]
        investigation.ai_model = ai_model
        investigation.ai_provider_attempts = ai_provider_attempts
        investigation.prompt_version = prompt_version
        investigation.search_provider = search_provider
        investigation.search_languages = ["en", "hu"]
        investigation.scoring_version = assessment.balance.scoring_version
        investigation.source_count = source_count
        investigation.completed_at = datetime.now(timezone.utc)
        self._session.commit()
