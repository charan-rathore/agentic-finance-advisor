"""
agents/storage_agent.py

Agent 3: Storage & Data Access

Responsibility:
  1. Consume insights from insights_queue and persist to SQLite
  2. Provide query functions the Streamlit UI calls to read data

No Gemini calls. No external APIs. Pure SQLite reads and writes.

Queues consumed:  insights_queue
SQLite tables written: insights
SQLite tables read:    insights, market_snapshots, news_articles, insights
"""

import asyncio
import json
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.models import Insight, init_db
from core.queues import insights_queue
from core.settings import settings

_engine = None


def get_engine() -> object:  # sqlalchemy.Engine
    """Return the SQLAlchemy engine, initializing it if needed."""
    global _engine
    if _engine is None:
        _engine = init_db(settings.DATABASE_URL)
    return _engine


async def run() -> None:
    """
    Listens on insights_queue forever.
    Every time the analysis agent produces an insight, this saves it to SQLite.
    """
    logger.info("[Storage Agent] Starting...")
    engine = get_engine()

    while True:
        try:
            insight = await asyncio.wait_for(insights_queue.get(), timeout=5.0)

            with Session(engine) as session:
                session.add(
                    Insight(
                        user_query=insight.get("user_query", ""),
                        insight_text=insight.get("insight_text", ""),
                        sentiment_summary=insight.get("sentiment_summary", ""),
                        sources=insight.get("sources", "[]"),
                        generated_at=datetime.now(UTC),
                        model_used=settings.GEMINI_MODEL,
                    )
                )
                session.commit()

            logger.info("[Storage Agent] Insight saved to SQLite")

        except TimeoutError:
            continue
        except Exception as e:
            logger.error(f"[Storage Agent] Error saving insight: {e}")


def get_recent_insights(limit: int = 5) -> list[dict]:
    """Return the most recent AI-generated insights for display in the UI."""
    engine = get_engine()
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT id, user_query, insight_text, sentiment_summary, "
                "sources, generated_at, model_used "
                "FROM insights ORDER BY generated_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()

    results: list[dict] = []
    for row in rows:
        try:
            sources = json.loads(row.sources) if row.sources else []
        except Exception:
            sources = []
        results.append(
            {
                "id": row.id,
                "user_query": row.user_query or "",
                "insight_text": row.insight_text,
                "sentiment_summary": row.sentiment_summary or "",
                "sources": sources,
                "generated_at": str(row.generated_at),
                "model_used": row.model_used or "gemini-1.5-flash",
            }
        )
    return results


def get_latest_prices() -> list[dict]:
    """Return the most recent price for each tracked symbol."""
    engine = get_engine()
    with Session(engine) as session:
        rows = session.execute(
            text("""
            SELECT symbol, price, volume, captured_at
            FROM market_snapshots
            WHERE (symbol, captured_at) IN (
                SELECT symbol, MAX(captured_at)
                FROM market_snapshots
                GROUP BY symbol
            )
            ORDER BY symbol
        """)
        ).fetchall()
    return [
        {
            "symbol": r.symbol,
            "price": r.price,
            "volume": r.volume,
            "captured_at": str(r.captured_at),
        }
        for r in rows
    ]


def get_recent_headlines(limit: int = 20) -> list[dict]:
    """Return recent ingested news headlines."""
    engine = get_engine()
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT headline, source, url, ingested_at "
                "FROM news_articles ORDER BY ingested_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()
    return [
        {
            "headline": r.headline,
            "source": r.source,
            "url": r.url,
            "ingested_at": str(r.ingested_at),
        }
        for r in rows
    ]
