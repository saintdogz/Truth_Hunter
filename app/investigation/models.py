"""Validated structures exchanged throughout the investigation pipeline."""

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimType(str, Enum):
    FACTUAL = "factual"
    OPINION = "opinion"
    MIXED = "mixed"


class ClaimInterpretation(StrictModel):
    interpreted_claim: str = Field(min_length=1, max_length=500)
    language: Literal["en", "hu"]
    claim_type: ClaimType
    confidence: float = Field(ge=0, le=1)


class SearchQueries(StrictModel):
    english: list[str] = Field(min_length=1, max_length=4)
    hungarian: list[str] = Field(min_length=1, max_length=4)


class SearchResult(StrictModel):
    url: HttpUrl
    title: str = Field(default="", max_length=500)
    snippet: str = Field(default="", max_length=2_000)
    engine: str | None = Field(default=None, max_length=100)


class SourceType(str, Enum):
    PRIMARY_OFFICIAL = "PRIMARY_OFFICIAL"
    PRIMARY_RESEARCH = "PRIMARY_RESEARCH"
    ACADEMIC = "ACADEMIC"
    COURT_LEGAL = "COURT_LEGAL"
    ESTABLISHED_MEDIA = "ESTABLISHED_MEDIA"
    EXPERT_ANALYSIS = "EXPERT_ANALYSIS"
    SECONDARY = "SECONDARY"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    UNKNOWN = "UNKNOWN"


class SourceDocument(StrictModel):
    url: HttpUrl
    title: str = Field(default="", max_length=500)
    domain: str = Field(min_length=1, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    published_at: datetime | None = None
    text: str = Field(min_length=1, max_length=100_000)


class EvidencePosition(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    NEUTRAL = "NEUTRAL"


class EvidenceAssessment(StrictModel):
    source_id: UUID | None = None
    position: EvidencePosition
    strength: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    quality: float = Field(ge=0, le=1)
    independence: float = Field(ge=0, le=1)
    recency: float = Field(ge=0, le=1)
    source_type: SourceType
    summary: str = Field(min_length=1, max_length=1_500)
    excerpt: str = Field(default="", max_length=1_000)
    assessment: str = Field(default="", max_length=1_500)


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Verdict(str, Enum):
    TRUE = "TRUE"
    MOSTLY_TRUE = "MOSTLY_TRUE"
    MIXED = "MIXED"
    MOSTLY_FALSE = "MOSTLY_FALSE"
    FALSE = "FALSE"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvidenceBalance(StrictModel):
    supporting: float | None = Field(default=None, ge=0, le=100)
    contradicting: float | None = Field(default=None, ge=0, le=100)
    supporting_weight: float = Field(ge=0)
    contradicting_weight: float = Field(ge=0)
    meaningful: bool
    scoring_version: str


class ConflictResult(StrictModel):
    detected: bool
    summary: str | None = Field(default=None, max_length=1_500)
    conflicting_source_ids: list[UUID] = Field(default_factory=list)
    level: float = Field(default=0, ge=0, le=1)


class AssessmentDraft(StrictModel):
    verdict: Verdict
    balance: EvidenceBalance
    confidence: Confidence
    conflict: ConflictResult
    evidence_sufficient: bool


class InvestigationSummary(StrictModel):
    explanation: str = Field(min_length=1, max_length=2_500)
    pro_arguments: list[str] = Field(default_factory=list, max_length=3)
    contra_arguments: list[str] = Field(default_factory=list, max_length=3)
