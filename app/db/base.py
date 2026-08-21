"""SQLAlchemy declarative model base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for models introduced in later implementation phases."""
