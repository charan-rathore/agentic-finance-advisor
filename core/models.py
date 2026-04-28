"""
core/models.py

SQLAlchemy ORM models backed by SQLite.
SQLite = a single file on disk. No server, no Docker service, no config.
The same ORM code works with PostgreSQL later by changing one line in settings.py.
"""

import os
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class MarketSnapshot(Base):
    """One price reading per symbol per ingest cycle."""

    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Float)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)


class NewsArticle(Base):
    """Raw news articles from RSS feeds."""

    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    headline = Column(String(500), nullable=False)
    url = Column(String(1000))
    body = Column(Text)
    source = Column(String(100))
    ingested_at = Column(DateTime, default=datetime.utcnow)


class Insight(Base):
    """AI-generated insights from Gemini, with context of what drove them."""

    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_query = Column(Text)
    insight_text = Column(Text, nullable=False)
    sentiment_summary = Column(Text)  # brief summary of sentiment signal used
    sources = Column(Text)  # JSON list of source URLs from RAG
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)
    model_used = Column(String(50), default="gemini-1.5-flash")


class FetchRun(Base):
    """
    One row per (source, key) that records when we last tried a fetch, when we
    last succeeded, and the content hash of the last successful payload.

    This replaces the in-memory `last_finnhub`/`last_sec`/... locals inside
    `ingest_agent.run()` so restarts don't re-hammer every API, and it also
    gives the UI a place to show "last refreshed at ...".
    """

    __tablename__ = "fetch_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(40), nullable=False, index=True)
    key = Column(String(40), nullable=False, index=True, default="")
    last_attempt_at = Column(DateTime, default=datetime.utcnow)
    last_success_at = Column(DateTime, nullable=True)
    last_content_hash = Column(String(64), nullable=True)
    last_error = Column(Text, nullable=True)


class SourceRegistry(Base):
    """
    Provenance registry — one row per unique external URL the system has
    fetched from. Upserted on every fetch cycle by `core.trust.register_source`.

    Answers: *where did our data come from, is that source trusted, and is it
    currently reachable?* Read by the Streamlit "Sources & History" page.

    Note: `url` is stored verbatim and is `unique=True`. Volatile query
    parameters (timestamps, cache-busters) will therefore create multiple rows
    for what is logically the same endpoint — that is intentional for the
    first cut; a `url_normalized` companion column is a future refinement.
    """

    __tablename__ = "source_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(1000), nullable=False, unique=True, index=True)
    domain = Column(String(200), nullable=False, index=True)
    source_name = Column(String(200))
    source_type = Column(String(50))
    is_trusted = Column(Boolean, default=False)
    is_reachable = Column(Boolean, default=True)
    http_status = Column(Integer)
    first_fetched_at = Column(DateTime, default=datetime.utcnow)
    last_fetched_at = Column(DateTime, default=datetime.utcnow)
    fetch_count = Column(Integer, default=1)


class UserProfile(Base):
    """
    Single-user investor profile collected during onboarding.

    First-row semantics: the application always reads/writes the row with
    the lowest ``id``. Multi-user support can be added later by adding an
    auth token column and filtering on it.
    """

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, default="Investor")
    monthly_income = Column(String(50), nullable=False)  # range label e.g. "₹50k–₹1L"
    monthly_sip_budget = Column(String(50), nullable=False)  # range label e.g. "₹2k–₹5k"
    risk_tolerance = Column(String(20), nullable=False)  # "low" | "medium" | "high"
    tax_bracket_pct = Column(Float, nullable=False)  # 0.0 | 5.0 | 20.0 | 30.0
    primary_goal = Column(String(100), nullable=False)  # free-form short phrase
    horizon_pref = Column(String(20), nullable=False)  # "short" | "intermediate" | "long"
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class KnowledgeVersion(Base):
    """
    Audit trail for every wiki page update. One row per write to any
    `data/wiki/**/*.md` file, created by `core.trust.record_wiki_version`.

    Answers: *what changed on this page, when, and which sources drove the
    change?* Used by the Streamlit UI to render per-page version history and
    the word-count-over-time growth chart.

    `source_urls` is a JSON list stored in TEXT for SQLite portability; on
    Postgres migration this could become `JSONB` without changing the ORM
    contract. There is no FK to `source_registry.url` — that link is soft so
    a URL expiring from the registry never blocks version history writes.
    """

    __tablename__ = "knowledge_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page_name = Column(String(300), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow, index=True)
    change_summary = Column(Text)
    source_urls = Column(Text)
    source_types = Column(Text)
    word_count_before = Column(Integer, default=0)
    word_count_after = Column(Integer, nullable=False)
    triggered_by = Column(String(100))


def init_db(database_url: str) -> object:  # sqlalchemy.Engine
    """
    Create all tables if they don't exist.
    Safe to call every time the app starts — won't overwrite existing data.
    Returns the SQLAlchemy engine.
    """
    # For SQLite file paths, ensure the parent directory exists
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        db_path = database_url.replace("sqlite:///", "", 1)
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine
