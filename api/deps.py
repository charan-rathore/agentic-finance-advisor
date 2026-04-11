"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from db.session import SessionLocal


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session (closes after request)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
