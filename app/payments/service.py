"""Transactional payment ledger, credit reservations, and free entitlements."""

import hashlib
import hmac
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    CreditGrant,
    CreditReservation,
    FreeEntitlement,
    Investigation,
    MonetizationEvent,
    Payment,
    User,
)


class MonetizationError(ValueError):
    pass


class InsufficientCreditsError(MonetizationError):
    pass


class EntitlementError(MonetizationError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MonetizationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def balance(self, user: User) -> int:
        value = self._session.scalar(
            select(func.coalesce(func.sum(CreditGrant.remaining), 0)).where(
                CreditGrant.user_id == user.id,
                CreditGrant.status == "ACTIVE",
            )
        )
        return int(value or 0)

    def record_created_order(self, user: User, provider_order_id: str) -> Payment:
        existing = self._session.scalar(
            select(Payment).where(Payment.provider_order_id == provider_order_id)
        )
        if existing is not None:
            if existing.user_id != user.id:
                raise MonetizationError("Payment order ownership mismatch")
            return existing
        payment = Payment(
            user_id=user.id,
            provider="paypal",
            provider_order_id=provider_order_id,
            amount_minor=self._settings.credit_pack_price_minor,
            currency=self._settings.credit_pack_currency,
            status="CREATED",
            credits_granted=self._settings.credit_pack_size,
        )
        self._session.add(payment)
        self._event("checkout_started", user=user, payment=payment)
        self._session.commit()
        self._session.refresh(payment)
        return payment

    def complete_payment(
        self,
        user: User,
        provider_order_id: str,
        provider_capture_id: str,
        amount_minor: int,
        currency: str,
    ) -> Payment:
        payment = self._session.scalar(
            select(Payment).where(Payment.provider_order_id == provider_order_id).with_for_update()
        )
        if payment is None or payment.user_id != user.id:
            raise MonetizationError("Payment order was not found")
        if amount_minor != payment.amount_minor or currency.upper() != payment.currency:
            raise MonetizationError("Captured payment amount does not match the product")
        if payment.status == "COMPLETED":
            if payment.provider_capture_id != provider_capture_id:
                raise MonetizationError("Payment capture mismatch")
            return payment
        if payment.status not in {"CREATED", "APPROVED"}:
            raise MonetizationError("Payment cannot be completed from its current state")
        payment.provider_capture_id = provider_capture_id
        payment.status = "COMPLETED"
        payment.completed_at = utc_now()
        self._session.add(
            CreditGrant(
                user_id=user.id,
                payment=payment,
                amount=payment.credits_granted,
                remaining=payment.credits_granted,
                status="ACTIVE",
            )
        )
        self._event(
            "payment_completed",
            user=user,
            payment=payment,
            amount_minor=payment.amount_minor,
        )
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            duplicate = self._session.scalar(
                select(Payment).where(Payment.provider_capture_id == provider_capture_id)
            )
            if duplicate is not None and duplicate.provider_order_id == provider_order_id:
                return duplicate
            raise MonetizationError("Payment capture could not be recorded") from exc
        self._session.refresh(payment)
        return payment

    def reserve_credit(self, user: User, investigation: Investigation) -> CreditReservation:
        self._require_ownership(user, investigation)
        existing = self._session.scalar(
            select(CreditReservation).where(CreditReservation.investigation_id == investigation.id)
        )
        if existing is not None:
            if existing.user_id != user.id:
                raise EntitlementError("Investigation entitlement mismatch")
            return existing
        grant = self._session.scalar(
            select(CreditGrant)
            .where(
                CreditGrant.user_id == user.id,
                CreditGrant.status == "ACTIVE",
                CreditGrant.remaining > 0,
            )
            .order_by(CreditGrant.created_at, CreditGrant.id)
            .with_for_update()
        )
        if grant is None:
            raise InsufficientCreditsError("No investigation credits remain")
        grant.remaining -= 1
        reservation = CreditReservation(
            user_id=user.id,
            grant_id=grant.id,
            investigation_id=investigation.id,
            status="RESERVED",
        )
        investigation.entitlement_kind = "CREDIT_RESERVED"
        self._session.add(reservation)
        self._session.commit()
        self._session.refresh(reservation)
        return reservation

    def consume_credit(self, investigation_id: UUID) -> None:
        reservation = self._reservation(investigation_id)
        if reservation.status == "CONSUMED":
            return
        if reservation.status != "RESERVED":
            raise EntitlementError("Credit reservation is not active")
        reservation.status = "CONSUMED"
        reservation.resolved_at = utc_now()
        reservation.investigation.is_unlocked = True
        reservation.investigation.entitlement_kind = "CREDIT"
        self._event("investigation_unlocked", user_id=reservation.user_id)
        self._session.commit()

    def finalize_investigation_credit(self, investigation_id: UUID, *, success: bool) -> None:
        reservation = self._session.scalar(
            select(CreditReservation).where(CreditReservation.investigation_id == investigation_id)
        )
        if reservation is None:
            return
        if success:
            self.consume_credit(investigation_id)
        else:
            self.release_credit(investigation_id)

    def finalize_entitlement(self, investigation_id: UUID, *, success: bool) -> None:
        """Resolve either a reserved paid credit or a provisional free use."""
        reservation = self._session.scalar(
            select(CreditReservation).where(CreditReservation.investigation_id == investigation_id)
        )
        if reservation is not None:
            self.finalize_investigation_credit(investigation_id, success=success)
            return
        if not success:
            self.release_free_attempt(investigation_id)

    def release_credit(self, investigation_id: UUID) -> None:
        reservation = self._session.scalar(
            select(CreditReservation).where(CreditReservation.investigation_id == investigation_id)
        )
        if reservation is None or reservation.status == "RELEASED":
            return
        if reservation.status != "RESERVED":
            return
        if reservation.grant.status == "ACTIVE":
            reservation.grant.remaining += 1
        reservation.status = "RELEASED"
        reservation.resolved_at = utc_now()
        reservation.investigation.entitlement_kind = None
        self._session.commit()

    def use_free_attempt(
        self, investigation: Investigation, session_id: str, user: User | None = None
    ) -> FreeEntitlement:
        if user is not None:
            self._require_ownership(user, investigation)
            if user.free_investigation_used:
                raise EntitlementError("The free investigation has already been used")
        session_hash = self._session_hash(session_id)
        existing = self._session.scalar(
            select(FreeEntitlement).where(FreeEntitlement.session_hash == session_hash)
        )
        if existing is not None:
            if existing.investigation_id != investigation.id:
                raise EntitlementError("The free investigation has already been used")
            return existing
        entitlement = FreeEntitlement(
            session_hash=session_hash,
            user_id=user.id if user else None,
            investigation_id=investigation.id,
        )
        if user is not None:
            user.free_investigation_used = True
        investigation.entitlement_kind = "FREE"
        self._session.add(entitlement)
        self._event("free_investigation_used", user=user)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise EntitlementError("The free investigation has already been used") from exc
        self._session.refresh(entitlement)
        return entitlement

    def release_free_attempt(self, investigation_id: UUID) -> None:
        entitlement = self._session.scalar(
            select(FreeEntitlement).where(FreeEntitlement.investigation_id == investigation_id)
        )
        if entitlement is None:
            return
        if entitlement.user_id is not None:
            user = self._session.get(User, entitlement.user_id)
            if user is not None:
                user.free_investigation_used = False
        investigation = self._session.get(Investigation, investigation_id)
        if investigation is not None:
            investigation.entitlement_kind = None
        self._session.delete(entitlement)
        self._session.commit()

    def entitlement_option(self, user: User | None, session_id: str) -> str:
        """Return FREE, CREDIT, or BLOCKED without mutating entitlement state."""
        session_used = self._session.scalar(
            select(FreeEntitlement.id).where(
                FreeEntitlement.session_hash == self._session_hash(session_id)
            )
        )
        if session_used is None and (user is None or not user.free_investigation_used):
            return "FREE"
        if user is not None and self.balance(user) > 0:
            return "CREDIT"
        return "BLOCKED"

    def unlock_previous_result(self, user: User, investigation: Investigation) -> None:
        self._require_ownership(user, investigation)
        if investigation.status != "COMPLETED":
            raise EntitlementError("Only completed investigations can be unlocked")
        if investigation.is_unlocked:
            return
        self.reserve_credit(user, investigation)
        self.consume_credit(investigation.id)

    def reverse_payment(self, provider_capture_id: str) -> Payment | None:
        payment = self._session.scalar(
            select(Payment)
            .where(Payment.provider_capture_id == provider_capture_id)
            .with_for_update()
        )
        if payment is None:
            return None
        if payment.status in {"REFUNDED", "REVERSED"}:
            return payment
        for grant in payment.grants:
            grant.remaining = 0
            grant.status = "REVOKED"
        payment.status = "REVERSED"
        self._event("payment_reversed", user_id=payment.user_id, payment=payment)
        self._session.commit()
        return payment

    def anonymize_for_account_deletion(self, user: User) -> None:
        fingerprint = hmac.new(
            self._settings.app_secret.get_secret_value().encode(),
            str(user.id).encode(),
            hashlib.sha256,
        ).hexdigest()
        for payment in self._session.scalars(select(Payment).where(Payment.user_id == user.id)):
            payment.user_id = None
            payment.anonymized_owner = fingerprint
        self._session.execute(
            update(MonetizationEvent)
            .where(MonetizationEvent.user_id == user.id)
            .values(user_id=None)
        )
        self._session.execute(delete(CreditReservation).where(CreditReservation.user_id == user.id))
        self._session.execute(delete(CreditGrant).where(CreditGrant.user_id == user.id))
        self._session.execute(delete(FreeEntitlement).where(FreeEntitlement.user_id == user.id))
        self._session.commit()

    def claim_guest_entitlement(self, user: User, session_id: str | None) -> bool:
        if not session_id:
            return False
        entitlement = self._session.scalar(
            select(FreeEntitlement).where(
                FreeEntitlement.session_hash == self._session_hash(session_id)
            )
        )
        if entitlement is None:
            return False
        entitlement.user_id = user.id
        user.free_investigation_used = True
        self._session.commit()
        return True

    def purchase_history(self, user: User) -> list[Payment]:
        return list(
            self._session.scalars(
                select(Payment)
                .where(Payment.user_id == user.id)
                .order_by(Payment.created_at.desc())
            )
        )

    def payment_for_user(self, user: User, provider_order_id: str) -> Payment:
        payment = self._session.scalar(
            select(Payment).where(Payment.provider_order_id == provider_order_id)
        )
        if payment is None or payment.user_id != user.id:
            raise MonetizationError("Payment order was not found")
        return payment

    def record_event(
        self, event_type: str, *, user: User | None = None, amount_minor: int | None = None
    ) -> None:
        self._event(event_type, user=user, amount_minor=amount_minor)
        self._session.commit()

    def process_verified_webhook(self, event: dict[str, object]) -> None:
        event_id = event.get("id")
        event_type = event.get("event_type")
        if not isinstance(event_id, str) or not isinstance(event_type, str):
            raise MonetizationError("Invalid PayPal webhook event")
        if self._session.scalar(
            select(MonetizationEvent.id).where(MonetizationEvent.provider_event_id == event_id)
        ):
            return
        resource = event.get("resource")
        if not isinstance(resource, dict):
            raise MonetizationError("Invalid PayPal webhook resource")
        payment: Payment | None = None
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            capture_id = resource.get("id")
            amount = resource.get("amount")
            supplementary = resource.get("supplementary_data")
            if not isinstance(supplementary, dict):
                raise MonetizationError("PayPal webhook order reference is missing")
            related = supplementary.get("related_ids")
            if not isinstance(related, dict):
                raise MonetizationError("PayPal webhook order reference is missing")
            order_id = related.get("order_id")
            if (
                not isinstance(capture_id, str)
                or not isinstance(order_id, str)
                or not isinstance(amount, dict)
            ):
                raise MonetizationError("PayPal webhook capture is invalid")
            currency = amount.get("currency_code")
            value = amount.get("value")
            payment = self._session.scalar(
                select(Payment).where(Payment.provider_order_id == order_id)
            )
            if payment is None or payment.user_id is None:
                raise MonetizationError("PayPal webhook payment was not found")
            user = self._session.get(User, payment.user_id)
            if user is None or not isinstance(currency, str):
                raise MonetizationError("PayPal webhook payment owner was not found")
            self.complete_payment(
                user,
                order_id,
                capture_id,
                _money_to_minor(value),
                currency,
            )
        elif event_type in {
            "PAYMENT.CAPTURE.REFUNDED",
            "PAYMENT.CAPTURE.REVERSED",
        }:
            capture_id = resource.get("id")
            links = resource.get("links")
            if event_type == "PAYMENT.CAPTURE.REFUNDED":
                capture_id = _related_capture_id(links)
            if not isinstance(capture_id, str):
                raise MonetizationError("PayPal reversal reference is missing")
            payment = self.reverse_payment(capture_id)
        marker = MonetizationEvent(
            event_type=f"paypal:{event_type.lower()}",
            provider_event_id=event_id,
            payment_id=payment.id if payment else None,
        )
        self._session.add(marker)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()

    def _reservation(self, investigation_id: UUID) -> CreditReservation:
        reservation = self._session.scalar(
            select(CreditReservation).where(CreditReservation.investigation_id == investigation_id)
        )
        if reservation is None:
            raise EntitlementError("No credit is reserved for this investigation")
        return reservation

    @staticmethod
    def _require_ownership(user: User, investigation: Investigation) -> None:
        if investigation.user_id != user.id:
            raise EntitlementError("Investigation does not belong to this account")

    def _session_hash(self, session_id: str) -> str:
        return hmac.new(
            self._settings.app_secret.get_secret_value().encode(),
            session_id.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _event(
        self,
        event_type: str,
        *,
        user: User | None = None,
        user_id: UUID | None = None,
        payment: Payment | None = None,
        amount_minor: int | None = None,
    ) -> None:
        self._session.add(
            MonetizationEvent(
                event_type=event_type,
                user_id=user.id if user is not None else user_id,
                payment=payment,
                amount_minor=amount_minor,
            )
        )


def _money_to_minor(value: object) -> int:
    if not isinstance(value, str) or "." not in value:
        raise MonetizationError("PayPal amount is invalid")
    whole, fraction = value.split(".", 1)
    if not whole.isdigit() or not fraction.isdigit() or len(fraction) > 2:
        raise MonetizationError("PayPal amount is invalid")
    return int(whole) * 100 + int(fraction.ljust(2, "0"))


def _related_capture_id(links: object) -> str | None:
    if not isinstance(links, list):
        return None
    for link in links:
        if not isinstance(link, dict) or link.get("rel") != "up":
            continue
        href = link.get("href")
        if isinstance(href, str) and "/captures/" in href:
            return href.rsplit("/captures/", 1)[1].split("?", 1)[0]
    return None
