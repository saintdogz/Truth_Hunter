"""Construct the configured Phase 2 pipeline."""

from sqlalchemy.orm import Session

from app.ai.factory import create_ai_provider
from app.core.config import Settings
from app.investigation.fetcher import FetchPolicy, SafeSourceFetcher
from app.investigation.pipeline import InvestigationPipeline
from app.investigation.repository import InvestigationRepository
from app.search.searxng import SearXNGProvider


def create_pipeline(settings: Settings, session: Session) -> InvestigationPipeline:
    ai = create_ai_provider(settings)
    search = SearXNGProvider(str(settings.searxng_url))
    fetcher = SafeSourceFetcher(
        FetchPolicy(
            timeout_seconds=settings.fetch_timeout_seconds,
            max_bytes=settings.fetch_max_bytes,
            redirect_limit=settings.fetch_redirect_limit,
        )
    )
    return InvestigationPipeline(
        ai,
        search,
        fetcher,
        InvestigationRepository(session),
        search_result_limit=settings.search_result_limit,
        search_delay_seconds=settings.search_delay_seconds,
        search_retry_attempts=settings.search_retry_attempts,
        useful_source_limit=settings.source_useful_limit,
        source_evaluation_limit=settings.source_evaluation_limit,
        ai_source_text_max_chars=settings.ai_source_text_max_chars,
    )
