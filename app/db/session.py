"""Database engine and readiness helpers."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Build one connection-pooled SQLAlchemy engine per process."""

    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_session() -> Iterator[Session]:
    """Provide a transaction-scoped database session."""

    session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with session_factory() as session:
        yield session


def database_is_ready() -> bool:
    """Check PostgreSQL connectivity without exposing exception details."""

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # The health response must remain stable for any driver failure.
        return False
    return True
