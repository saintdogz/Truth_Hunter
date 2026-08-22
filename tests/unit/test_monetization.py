"""Deterministic Phase 5 payment and credit-ledger tests."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.service import AccountService
from app.core.config import Settings
from app.db.base import Base
from app.db.models import CreditGrant, Investigation, Payment
from app.payments.service import (
    EntitlementError,
    InsufficientCreditsError,
    MonetizationService,
)


def settings() -> Settings:
    return Settings(
        app_env="test",
        app_secret="monetization-test-secret",
        database_url="postgresql+psycopg://test:test@localhost/test",
        email_delivery_mode="development",
        monetization_enabled=False,
        owner_payment_testing_enabled=False,
        credit_pack_price_minor=300,
        credit_pack_currency="EUR",
        credit_pack_size=5,
    )


def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def user_and_investigation(db: Session):  # type: ignore[no-untyped-def]
    config = settings()
    account = AccountService(db, config)
    user = account.register("buyer@example.com", "correct horse battery staple")
    account.verify_email(account.verification_token(user))
    investigation = Investigation(
        user_id=user.id,
        original_claim="A sufficiently long test claim for monetization.",
        status="AWAITING_CONFIRMATION",
    )
    db.add(investigation)
    db.commit()
    return config, user, investigation


def complete_pack(service: MonetizationService, user):  # type: ignore[no-untyped-def]
    service.record_created_order(user, "ORDER-1")
    return service.complete_payment(user, "ORDER-1", "CAPTURE-1", 300, "eur")


def test_payment_completion_is_idempotent_and_grants_five_credits() -> None:
    with session() as db:
        config, user, _ = user_and_investigation(db)
        service = MonetizationService(db, config)

        first = complete_pack(service, user)
        second = service.complete_payment(user, "ORDER-1", "CAPTURE-1", 300, "EUR")

        assert first.id == second.id
        assert service.balance(user) == 5
        assert db.scalar(select(func.count(CreditGrant.id))) == 1


def test_credit_is_reserved_then_consumed_or_released() -> None:
    with session() as db:
        config, user, investigation = user_and_investigation(db)
        service = MonetizationService(db, config)
        complete_pack(service, user)

        service.reserve_credit(user, investigation)
        assert service.balance(user) == 4

        service.release_credit(investigation.id)
        assert service.balance(user) == 5

        second = Investigation(
            user_id=user.id,
            original_claim="Another sufficiently long claim for a paid investigation.",
            status="AWAITING_CONFIRMATION",
        )
        db.add(second)
        db.commit()
        service.reserve_credit(user, second)
        service.consume_credit(second.id)

        assert service.balance(user) == 4
        assert second.is_unlocked is True
        assert second.entitlement_kind == "CREDIT"


def test_free_attempt_is_single_use_across_session_and_account() -> None:
    with session() as db:
        config, user, investigation = user_and_investigation(db)
        service = MonetizationService(db, config)

        service.use_free_attempt(investigation, "guest-session", user)
        assert user.free_investigation_used is True

        other = Investigation(
            user_id=user.id,
            original_claim="A different sufficiently long claim for free-use enforcement.",
            status="AWAITING_CONFIRMATION",
        )
        db.add(other)
        db.commit()
        with pytest.raises(EntitlementError):
            service.use_free_attempt(other, "another-session", user)


def test_unlock_previous_result_uses_one_credit() -> None:
    with session() as db:
        config, user, investigation = user_and_investigation(db)
        service = MonetizationService(db, config)
        investigation.status = "COMPLETED"
        investigation.entitlement_kind = "FREE"
        db.commit()
        complete_pack(service, user)

        service.unlock_previous_result(user, investigation)

        assert investigation.is_unlocked is True
        assert service.balance(user) == 4


def test_reversal_removes_only_unused_credits() -> None:
    with session() as db:
        config, user, investigation = user_and_investigation(db)
        service = MonetizationService(db, config)
        payment = complete_pack(service, user)
        service.reserve_credit(user, investigation)
        service.consume_credit(investigation.id)

        reversed_payment = service.reverse_payment("CAPTURE-1")

        assert reversed_payment is not None
        assert reversed_payment.status == "REVERSED"
        assert investigation.is_unlocked is True
        assert service.balance(user) == 0
        assert payment.grants[0].remaining == 0


def test_reservation_requires_available_credit() -> None:
    with session() as db:
        config, user, investigation = user_and_investigation(db)
        with pytest.raises(InsufficientCreditsError):
            MonetizationService(db, config).reserve_credit(user, investigation)


def test_account_deletion_anonymizes_payment_owner() -> None:
    with session() as db:
        config, user, _ = user_and_investigation(db)
        service = MonetizationService(db, config)
        payment = complete_pack(service, user)

        service.anonymize_for_account_deletion(user)

        db.refresh(payment)
        assert payment.user_id is None
        assert payment.anonymized_owner is not None
        assert "buyer" not in payment.anonymized_owner
        assert db.scalar(select(func.count(Payment.id))) == 1
