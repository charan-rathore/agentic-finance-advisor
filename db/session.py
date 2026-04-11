"""
Legacy session factory (v2).

Prefer using sqlalchemy.orm.Session with the engine returned by core.models.init_db.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from core.models import init_db
from core.settings import settings

_engine = init_db(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a DB session (FastAPI-style); closes on teardown."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
