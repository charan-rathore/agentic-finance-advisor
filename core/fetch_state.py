"""
core/fetch_state.py

Persisted fetch-cadence tracker.

Each data source (finnhub, alpha_vantage, sec, fred, google_news, ...) has a
row in the `fetch_runs` SQLite table per logical `key` (usually a ticker, or
empty string for non-ticker sources like 'fred').  Callers ask:

    should_fetch(session, "finnhub", "AAPL", interval_hours=1)

and we answer True/False based on `last_success_at`.  Callers then call:

    record_attempt(session, source, key)
    record_success(session, source, key, content_hash=...)
    record_failure(session, source, key, error="...")

Why in SQLite and not just a JSON file?
- Survives container restarts (otherwise every restart re-hammers every API).
- The UI already talks to SQLite, so "last refreshed at" is one SELECT away.
- Transactions give us race-safety if we ever fan out fetchers concurrently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from core.models import FetchRun


def _row(session: Session, source: str, key: str = "") -> FetchRun:
    row = session.query(FetchRun).filter_by(source=source, key=key).one_or_none()
    if row is None:
        row = FetchRun(source=source, key=key)
        session.add(row)
    return row


def should_fetch(
    session: Session,
    source: str,
    key: str = "",
    *,
    interval_hours: float,
) -> bool:
    """Return True iff the last successful fetch is older than `interval_hours`."""
    row = session.query(FetchRun).filter_by(source=source, key=key).one_or_none()
    if row is None or row.last_success_at is None:
        return True
    age = datetime.utcnow() - row.last_success_at
    return age > timedelta(hours=interval_hours)


def record_attempt(session: Session, source: str, key: str = "") -> None:
    row = _row(session, source, key)
    row.last_attempt_at = datetime.utcnow()
    session.commit()


def record_success(
    session: Session,
    source: str,
    key: str = "",
    *,
    content_hash: str | None = None,
) -> None:
    row = _row(session, source, key)
    now = datetime.utcnow()
    row.last_attempt_at = now
    row.last_success_at = now
    row.last_content_hash = content_hash
    row.last_error = None
    session.commit()


def record_failure(session: Session, source: str, key: str = "", *, error: str) -> None:
    row = _row(session, source, key)
    row.last_attempt_at = datetime.utcnow()
    row.last_error = error[:500]
    session.commit()
    logger.warning(f"[FetchState] {source}/{key} failed: {error[:100]}")


def iso(dt: datetime | None) -> str | None:
    """Helper to format a UTC timestamp for the UI."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC).isoformat()
