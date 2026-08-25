"""Read-only aggregation of operational investigation telemetry."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Feedback, Investigation, PublicReport, User

TERMINAL_STATUSES = {"COMPLETED", "FAILED", "SEARCH_FAILED"}
FAILURE_GUIDANCE = {
    "rate_limit": ("Rate limited", "Transient · cooldown and fallback active", True),
    "quota": ("Quota exhausted", "Check provider allowance; bounded fallback active", False),
    "availability": ("Provider unavailable", "Transient · retry and fallback active", True),
    "model_output": ("Invalid model output", "Fallback active; review if recurring", True),
    "payload_too_large": ("Request too large", "Review provider input limits", True),
    "configuration": ("Configuration rejected", "Check model and API-key configuration", False),
    "authentication": ("Authentication failed", "Check the affected provider credential", False),
    "invalid_response": ("Invalid response", "Transient · inspect provider health", True),
}


def _duration_seconds(item: Investigation, now: datetime) -> int | None:
    end = item.completed_at
    if end is None and item.status not in TERMINAL_STATUSES:
        end = now
    if end is None:
        return None
    start = item.created_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, round((end - start).total_seconds()))


def dashboard_snapshot(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    timestamp = now or datetime.now(timezone.utc)
    investigations = list(
        session.scalars(select(Investigation).order_by(Investigation.created_at.desc())).all()
    )
    users = list(session.scalars(select(User)).all())
    feedback_rows = list(session.scalars(select(Feedback)).all())
    public_reports = list(
        session.scalars(select(PublicReport).order_by(PublicReport.created_at.desc())).all()
    )
    status_counts = Counter(item.status for item in investigations)
    provider_outcomes: Counter[tuple[str, str]] = Counter()
    failure_categories: Counter[str] = Counter()
    provider_calls: Counter[str] = Counter()
    fallback_investigations = 0
    paid_calls = 0
    durations: list[int] = []

    for item in investigations:
        providers_seen: list[str] = []
        for attempt in item.ai_provider_attempts or []:
            provider = str(attempt.get("provider", "unknown"))
            outcome = str(attempt.get("status", "unknown"))
            provider_outcomes[(provider, outcome)] += 1
            if outcome != "cooldown":
                provider_calls[provider] += 1
            if provider not in providers_seen and outcome != "cooldown":
                providers_seen.append(provider)
            category = attempt.get("category")
            if outcome == "failed" and isinstance(category, str):
                failure_categories[category] += 1
            if attempt.get("tier") == "paid" and outcome == "succeeded":
                paid_calls += 1
        if len(providers_seen) > 1:
            fallback_investigations += 1
        duration = _duration_seconds(item, timestamp)
        if duration is not None and item.status == "COMPLETED":
            durations.append(duration)

    completed = status_counts["COMPLETED"]
    failed = status_counts["FAILED"] + status_counts["SEARCH_FAILED"]
    terminal = completed + failed
    active_users = [user for user in users if user.deleted_at is None]
    seven_days_ago = timestamp - timedelta(days=7)
    recent_users = [
        user
        for user in users
        if user.deleted_at is None
        and (
            user.created_at.replace(tzinfo=timezone.utc)
            if user.created_at.tzinfo is None
            else user.created_at
        )
        >= seven_days_ago
    ]
    helpful_feedback = sum(item.value == "HELPFUL" for item in feedback_rows)
    provider_names = sorted({provider for provider, _ in provider_outcomes})
    provider_summary = [
        {
            "provider": provider,
            "succeeded": provider_outcomes[(provider, "succeeded")],
            "failed": provider_outcomes[(provider, "failed")],
            "cooldown": provider_outcomes[(provider, "cooldown")],
            "calls": provider_calls[provider],
            "success_rate": round(
                provider_outcomes[(provider, "succeeded")] / provider_calls[provider] * 100
            )
            if provider_calls[provider]
            else 0,
        }
        for provider in provider_names
    ]
    daily_rows: list[dict[str, object]] = []
    max_daily = 1
    for days_ago in range(6, -1, -1):
        day = (timestamp - timedelta(days=days_ago)).date()
        items = [item for item in investigations if item.created_at.date() == day]
        completed_count = sum(item.status == "COMPLETED" for item in items)
        failed_count = sum(item.status in {"FAILED", "SEARCH_FAILED"} for item in items)
        max_daily = max(max_daily, len(items))
        daily_rows.append(
            {
                "label": day.strftime("%a"),
                "date": day.isoformat(),
                "all": len(items),
                "completed": completed_count,
                "failed": failed_count,
            }
        )

    return {
        "generated_at": timestamp,
        "totals": {
            "all": len(investigations),
            "completed": completed,
            "failed": failed,
            "running": sum(
                count for status, count in status_counts.items() if status not in TERMINAL_STATUSES
            ),
            "success_rate": round(completed / terminal * 100, 1) if terminal else 0.0,
            "average_seconds": round(sum(durations) / len(durations)) if durations else None,
            "fallback_investigations": fallback_investigations,
            "paid_calls": paid_calls,
        },
        "users": {
            "registered": len(users),
            "active": len(active_users),
            "verified": sum(user.email_verified for user in active_users),
            "deleted": len(users) - len(active_users),
            "new_last_7_days": len(recent_users),
        },
        "feedback": {
            "total": len(feedback_rows),
            "helpful": helpful_feedback,
            "not_helpful": len(feedback_rows) - helpful_feedback,
            "helpful_rate": round(helpful_feedback / len(feedback_rows) * 100, 1)
            if feedback_rows
            else None,
        },
        "reports": {
            "total": len(public_reports),
            "open": sum(item.status == "OPEN" for item in public_reports),
            "reviewed": sum(item.status != "OPEN" for item in public_reports),
            "recent": [
                {
                    "investigation_id": item.investigation_id,
                    "reason": item.reason,
                    "status": item.status,
                    "created_at": item.created_at,
                }
                for item in public_reports[:10]
            ],
        },
        "statuses": status_counts.most_common(),
        "providers": [
            {"provider": provider, "outcome": outcome, "count": count}
            for (provider, outcome), count in sorted(provider_outcomes.items())
        ],
        "provider_summary": provider_summary,
        "daily": daily_rows,
        "max_daily": max_daily,
        "failures": [
            {
                "category": category,
                "label": FAILURE_GUIDANCE.get(
                    category, (category.replace("_", " "), "Review logs", False)
                )[0],
                "action": FAILURE_GUIDANCE.get(category, ("", "Review logs", False))[1],
                "retryable": FAILURE_GUIDANCE.get(category, ("", "", False))[2],
                "count": count,
            }
            for category, count in failure_categories.most_common()
        ],
        "recent": [
            {
                "id": item.id,
                "created_at": item.created_at,
                "status": item.status,
                "verdict": item.verdict,
                "language": item.language,
                "model": item.ai_model,
                "sources": item.source_count,
                "duration_seconds": _duration_seconds(item, timestamp),
            }
            for item in investigations[:25]
        ],
    }
