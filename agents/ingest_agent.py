"""
agents/ingest_agent.py

Agent 1: Data Ingestion

Responsibility: fetch market data and news, publish to queues, save to DB.

Data sources used (ALL FREE — no API key required):
  - yfinance: wraps Yahoo Finance public data, completely free
  - feedparser: parses RSS feeds, completely free

Queues produced:
  - raw_market_queue: one message per stock symbol per cycle
  - raw_news_queue:   one message per news article per cycle

SQLite tables written:
  - market_snapshots
  - news_articles

This agent does NOT call Gemini or do any analysis.
"""

import asyncio
from datetime import datetime, timezone

import feedparser
import yfinance as yf
from loguru import logger
from sqlalchemy.orm import Session

from core.models import MarketSnapshot, NewsArticle, init_db
from core.queues import raw_market_queue, raw_news_queue
from core.settings import settings
from core.sec_client import fetch_financial_data_for_symbols


async def fetch_market_data(engine) -> list[dict]:
    """
    Fetch current stock prices using yfinance.
    yfinance is free — it scrapes Yahoo Finance's public endpoints.
    No API key needed. No rate limit for reasonable personal use.
    """
    results: list[dict] = []
    loop = asyncio.get_event_loop()

    for symbol in settings.YFINANCE_SYMBOLS:
        try:

            def _make_ticker(s: str = symbol):
                return yf.Ticker(s)

            ticker = await loop.run_in_executor(None, _make_ticker)
            info = ticker.fast_info
            price = getattr(info, "last_price", None) if info is not None else None
            if price is None and isinstance(info, dict):
                price = info.get("last_price")

            if price is None:
                logger.warning(f"No price data for {symbol} (market may be closed)")
                continue

            vol = getattr(info, "three_month_average_volume", None) if info is not None else None
            if vol is None and isinstance(info, dict):
                vol = info.get("three_month_average_volume", 0)

            snap = {
                "symbol": symbol,
                "price": round(float(price), 2),
                "volume": round(float(vol or 0), 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            results.append(snap)

            with Session(engine) as session:
                session.add(
                    MarketSnapshot(
                        symbol=snap["symbol"],
                        price=snap["price"],
                        volume=snap["volume"],
                        captured_at=datetime.now(timezone.utc),
                    )
                )
                session.commit()

            logger.info(f"[Ingest] {symbol}: ${float(price):.2f}")

        except Exception as e:
            logger.error(f"[Ingest] Error fetching {symbol}: {e}")

    return results


async def fetch_news(engine) -> list[dict]:
    """
    Fetch news from RSS feeds using feedparser.
    feedparser is free and does not require any API key.
    RSS feeds are public — no login, no billing.
    """
    articles: list[dict] = []
    loop = asyncio.get_event_loop()

    for feed_url in settings.NEWS_RSS_FEEDS:
        try:
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            for entry in feed.entries[:15]:
                article = {
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "body": entry.get("summary", ""),
                    "published_at": entry.get(
                        "published", datetime.now(timezone.utc).isoformat()
                    ),
                    "source": feed.feed.get("title", feed_url),
                }
                articles.append(article)

                with Session(engine) as session:
                    session.add(
                        NewsArticle(
                            headline=article["headline"],
                            url=article["url"],
                            body=article["body"],
                            source=article["source"],
                            ingested_at=datetime.now(timezone.utc),
                        )
                    )
                    session.commit()

            logger.info(f"[Ingest] {len(feed.entries[:15])} articles from {feed_url[:50]}")

        except Exception as e:
            logger.error(f"[Ingest] Error fetching feed {feed_url}: {e}")

    return articles


async def fetch_sec_data() -> list[dict]:
    """
    Fetch SEC financial data for tracked symbols.
    This runs less frequently than price/news (maybe once per day).
    """
    try:
        logger.info("[Ingest Agent] Fetching SEC financial data...")
        sec_data = await fetch_financial_data_for_symbols(settings.YFINANCE_SYMBOLS)
        logger.info(f"[Ingest Agent] Fetched SEC data for {len(sec_data)} companies")
        return sec_data
    except Exception as e:
        logger.error(f"[Ingest Agent] Error fetching SEC data: {e}")
        return []


async def run() -> None:
    """
    Main ingest loop. Fetches data every INGEST_INTERVAL_SECONDS, puts on queues.
    SEC data is fetched less frequently (every 24 hours) since it changes slowly.
    Runs forever as an asyncio task.
    """
    logger.info("[Ingest Agent] Starting...")
    engine = init_db(settings.DATABASE_URL)
    
    # Track when we last fetched SEC data (fetch once per day)
    last_sec_fetch = 0
    sec_fetch_interval = 24 * 3600  # 24 hours in seconds

    while True:
        logger.info("[Ingest Agent] Starting fetch cycle...")

        # Always fetch market data and news (real-time)
        snapshots = await fetch_market_data(engine)
        for snap in snapshots:
            await raw_market_queue.put(snap)
        logger.info(f"[Ingest Agent] Put {len(snapshots)} market snapshots on queue")

        articles = await fetch_news(engine)
        for article in articles:
            await raw_news_queue.put(article)
        logger.info(f"[Ingest Agent] Put {len(articles)} news articles on queue")

        # Fetch SEC data less frequently (once per day)
        import time
        now = time.time()
        if now - last_sec_fetch > sec_fetch_interval:
            logger.info("[Ingest Agent] Time for SEC data refresh...")
            sec_data = await fetch_sec_data()
            
            # Put SEC data on the news queue with special marking
            for company_data in sec_data:
                sec_article = {
                    "headline": f"SEC Financial Data Update: {company_data.get('company_name', 'Unknown')}",
                    "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company_data.get('cik', '').zfill(10)}.json",
                    "body": f"Updated financial data for {company_data.get('symbol', 'N/A')}: "
                           f"Revenue: ${company_data.get('recent_revenue', {}).get('value', 'N/A'):,} "
                           f"Assets: ${company_data.get('recent_assets', {}).get('value', 'N/A'):,}",
                    "published_at": company_data.get('fetched_at'),
                    "source": "SEC EDGAR",
                    "data_type": "sec_financial",  # Special marker for wiki processing
                    "raw_data": company_data,  # Include full financial data
                }
                await raw_news_queue.put(sec_article)
            
            logger.info(f"[Ingest Agent] Put {len(sec_data)} SEC financial updates on queue")
            last_sec_fetch = now

        logger.info(f"[Ingest Agent] Cycle done. Sleeping {settings.INGEST_INTERVAL_SECONDS}s...")
        await asyncio.sleep(settings.INGEST_INTERVAL_SECONDS)
