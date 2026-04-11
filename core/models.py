"""
core/models.py

SQLAlchemy ORM models backed by SQLite.
SQLite = a single file on disk. No server, no Docker service, no config.
The same ORM code works with PostgreSQL later by changing one line in settings.py.
"""

import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


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


def init_db(database_url: str):
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
