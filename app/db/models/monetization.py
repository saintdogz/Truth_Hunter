"""Phase 5 payment, credit, free-use, and monetization-event models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    anonymized_owner: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider_capture_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), index=True)
    credits_granted: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="payments")
    grants: Mapped[list["CreditGrant"]] = relationship(back_populates="payment")


class CreditGrant(Base):
    __tablename__ = "credit_grants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[int] = mapped_column(Integer)
    remaining: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="credit_grants")
    payment: Mapped[Payment] = relationship(back_populates="grants")
    reservations: Mapped[list["CreditReservation"]] = relationship(back_populates="grant")


class CreditReservation(Base):
    __tablename__ = "credit_reservations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    grant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("credit_grants.id", ondelete="CASCADE"), index=True
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="RESERVED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    grant: Mapped[CreditGrant] = relationship(back_populates="reservations")
    investigation: Mapped["Investigation"] = relationship(back_populates="credit_reservation")


class FreeEntitlement(Base):
    __tablename__ = "free_entitlements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True, index=True
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), unique=True, index=True
    )
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MonetizationEvent(Base):
    __tablename__ = "monetization_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_event_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    payment: Mapped[Payment | None] = relationship()


from app.db.models.investigation import Investigation  # noqa: E402
from app.db.models.user import User  # noqa: E402
