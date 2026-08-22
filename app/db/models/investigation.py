"""Phase 2 investigation snapshot persistence models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    original_claim: Mapped[str] = mapped_column(Text)
    interpreted_claim: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    claim_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correction_used: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="CREATED", index=True)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supporting_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    contradicting_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pro_arguments: Mapped[list[str]] = mapped_column(JSON, default=list)
    contra_arguments: Mapped[list[str]] = mapped_column(JSON, default=list)
    conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflicting_source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_provider_attempts: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    search_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    search_languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    scoring_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sources: Mapped[list["Source"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    user: Mapped["User | None"] = relationship(back_populates="investigations")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(500), default="")
    domain: Mapped[str] = mapped_column(String(255), index=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    investigation: Mapped[Investigation] = relationship(back_populates="sources")
    evidence: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[str] = mapped_column(String(20))
    strength: Mapped[float] = mapped_column(Float)
    relevance: Mapped[float] = mapped_column(Float)
    quality: Mapped[float] = mapped_column(Float)
    independence: Mapped[float] = mapped_column(Float)
    recency: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    investigation: Mapped[Investigation] = relationship(back_populates="evidence")
    source: Mapped[Source] = relationship(back_populates="evidence")


from app.db.models.feedback import Feedback  # noqa: E402
from app.db.models.user import User  # noqa: E402
