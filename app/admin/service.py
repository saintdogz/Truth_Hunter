"""Read-only aggregation of operational investigation telemetry."""

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Investigation

TERMINAL_STATUSES = {"COMPLETED", "FAILED"}


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
    status_counts = Counter(item.status for item in investigations)
    provider_outcomes: Counter[tuple[str, str]] = Counter()
    failure_categories: Counter[str] = Counter()
    fallback_investigations = 0
    paid_calls = 0
    durations: list[int] = []

    for item in investigations:
        providers_seen: list[str] = []
        for attempt in item.ai_provider_attempts or []:
            provider = str(attempt.get("provider", "unknown"))
            outcome = str(attempt.get("status", "unknown"))
            provider_outcomes[(provider, outcome)] += 1
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
    failed = status_counts["FAILED"]
    terminal = completed + failed
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
        "statuses": status_counts.most_common(),
        "providers": [
            {"provider": provider, "outcome": outcome, "count": count}
            for (provider, outcome), count in sorted(provider_outcomes.items())
        ],
        "failures": failure_categories.most_common(),
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
