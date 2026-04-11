"""
Database engine and session factory.

Uses a sync engine for compatibility with Alembic and straightforward transactions.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings

_settings = get_settings()

engine = create_engine(
    str(_settings.database_url),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=_settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session and ensure cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
