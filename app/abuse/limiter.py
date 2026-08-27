"""Persistent, privacy-safe public action limits."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AbuseRateLimit


def public_client_key(request: Request, settings: Settings, action: str) -> str:
    """Return a keyed digest without persisting a raw IP or session identifier."""
    host = request.client.host if request.client else "unknown"
    session_identity = request.session.get("user_id") or request.session.get("guest_session_id")
    identity = f"{action}|{host}|{session_identity or 'anonymous'}"
    return hmac.new(
        settings.app_secret.get_secret_value().encode(), identity.encode(), hashlib.sha256
    ).hexdigest()


def allow_public_action(
    session: Session,
    *,
    action: str,
    key_hash: str,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Consume one attempt from a durable fixed window."""
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(seconds=window_seconds)
    session.execute(
        delete(AbuseRateLimit).where(
            AbuseRateLimit.window_started_at < cutoff - timedelta(seconds=window_seconds)
        )
    )
    bucket = session.get(AbuseRateLimit, (action, key_hash), with_for_update=True)
    if bucket is None:
        session.add(
            AbuseRateLimit(
                action=action,
                key_hash=key_hash,
                window_started_at=current_time,
                attempts=1,
            )
        )
        session.commit()
        return True
    window_started_at = bucket.window_started_at
    if window_started_at.tzinfo is None:
        window_started_at = window_started_at.replace(tzinfo=timezone.utc)
    if window_started_at <= cutoff:
        bucket.window_started_at = current_time
        bucket.attempts = 1
        session.commit()
        return True
    if bucket.attempts >= limit:
        session.rollback()
        return False
    bucket.attempts += 1
    session.commit()
    return True
