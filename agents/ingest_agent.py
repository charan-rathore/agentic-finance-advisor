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

from core.alpha_vantage_client import fetch_alpha_vantage_for_symbols
from core.fetchers import fetch_macro_indicators
from core.finnhub_client import fetch_finnhub_for_symbols
from core.models import MarketSnapshot, NewsArticle, init_db
from core.queues import raw_market_queue, raw_news_queue
from core.sec_client import fetch_financial_data_for_symbols
from core.settings import settings


def _yf_snapshot(symbol: str) -> dict | None:
    """
    Blocking yfinance call. Tries fast_info first (cheap), then falls back to the
    1-day history endpoint. Returns None when yfinance has no data for the symbol.

    Runs in a thread via run_in_executor so the event loop is never blocked.
    """
    ticker = yf.Ticker(symbol)
    price: float | None = None
    volume: float = 0.0

    try:
        info = ticker.fast_info
        price = getattr(info, "last_price", None)
        if price is None and isinstance(info, dict):
            price = info.get("last_price")
        vol = getattr(info, "three_month_average_volume", None)
        if vol is None and isinstance(info, dict):
            vol = info.get("three_month_average_volume")
        if vol is not None:
            volume = float(vol)
    except Exception as e:
        logger.debug(f"[Ingest] fast_info failed for {symbol}: {e}")

    if price is None:
        try:
            hist = ticker.history(period="1d", auto_adjust=False)
            if len(hist) > 0:
                price = float(hist["Close"].iloc[-1])
                if "Volume" in hist.columns:
                    volume = float(hist["Volume"].iloc[-1])
        except Exception as e:
            logger.debug(f"[Ingest] history fallback failed for {symbol}: {e}")

    if price is None:
        return None

    return {
        "symbol": symbol,
        "price": round(float(price), 2),
        "volume": round(volume, 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "yfinance",
        "market_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


async def fetch_market_data(engine) -> list[dict]:
    """
    Fetch current stock prices using yfinance.

    Uses `fast_info.last_price` when available and falls back to a 1-day history
    close. Symbols with no data are skipped (common outside market hours, or when
    Yahoo is temporarily rate-limiting).
    """
    results: list[dict] = []
    loop = asyncio.get_event_loop()

    for symbol in settings.YFINANCE_SYMBOLS:
        try:
            snap = await loop.run_in_executor(None, _yf_snapshot, symbol)
            if snap is None:
                logger.warning(f"[Ingest] No price data for {symbol} (market closed or rate-limited)")
                continue

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

            logger.info(f"[Ingest] {symbol}: ${snap['price']:.2f}")

        except Exception as e:
            logger.error(f"[Ingest] Error fetching {symbol}: {e}")

    return results


def _default_news_feeds() -> list[str]:
    """
    Build the list of RSS feeds to poll.

    If NEWS_RSS_FEEDS is explicitly set in .env, use that. Otherwise fall back to
    per-symbol Google News RSS searches — the old Yahoo default
    (`feeds.finance.yahoo.com/rss/2.0/headline`) started returning empty XML in
    early 2026 and is no longer usable.
    """
    if settings.NEWS_RSS_FEEDS:
        return settings.NEWS_RSS_FEEDS
    return [
        f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        for symbol in settings.YFINANCE_SYMBOLS
    ]


async def fetch_news(engine) -> list[dict]:
    """
    Fetch news from RSS feeds using feedparser.
    Free, no API key, public feeds.
    """
    articles: list[dict] = []
    loop = asyncio.get_event_loop()

    for feed_url in _default_news_feeds():
        try:
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            if feed.bozo and not feed.entries:
                logger.warning(
                    f"[Ingest] Malformed/empty feed, skipping: {feed_url[:80]}"
                )
                continue

            feed_source = feed.feed.get("title", feed_url) if hasattr(feed, "feed") else feed_url

            for entry in feed.entries[:15]:
                article = {
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "body": entry.get("summary", ""),
                    "published_at": entry.get(
                        "published", datetime.now(timezone.utc).isoformat()
                    ),
                    "source": feed_source,
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

            logger.info(
                f"[Ingest] {len(feed.entries[:15])} articles from {feed_url[:80]}"
            )

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
    Main ingest loop.

    Cadences (all driven by `.env`):
      - Price + news: every INGEST_INTERVAL_SECONDS (default 5 min)
      - Finnhub  (quotes/news/recommendations): every FINNHUB_FETCH_INTERVAL_HOURS
      - Alpha Vantage (quote/overview/income):  every ALPHA_VANTAGE_FETCH_INTERVAL_HOURS
      - SEC EDGAR company facts:                every SEC_FETCH_INTERVAL_HOURS
      - FRED macro indicators:                  every MACRO_FETCH_INTERVAL_HOURS

    Each heavy source tracks its own last-success timestamp in-memory; the
    PROJECT_TODO P2 item "persist fetch state in SQLite" upgrades this later.
    """
    import time

    logger.info("[Ingest Agent] Starting...")
    engine = init_db(settings.DATABASE_URL)

    last_finnhub = 0.0
    last_alpha_vantage = 0.0
    last_sec = 0.0
    last_macro = 0.0

    finnhub_gap = settings.FINNHUB_FETCH_INTERVAL_HOURS * 3600
    alpha_vantage_gap = settings.ALPHA_VANTAGE_FETCH_INTERVAL_HOURS * 3600
    sec_gap = settings.SEC_FETCH_INTERVAL_HOURS * 3600
    macro_gap = settings.MACRO_FETCH_INTERVAL_HOURS * 3600

    while True:
        logger.info("[Ingest Agent] Starting fetch cycle...")

        # ── Frequent: prices + news ─────────────────────────────────────────
        snapshots = await fetch_market_data(engine)
        for snap in snapshots:
            await raw_market_queue.put(snap)
        logger.info(f"[Ingest Agent] {len(snapshots)} market snapshots -> queue")

        articles = await fetch_news(engine)
        for article in articles:
            await raw_news_queue.put(article)
        logger.info(f"[Ingest Agent] {len(articles)} news articles -> queue")

        now = time.time()

        # ── Finnhub (hourly by default) ─────────────────────────────────────
        if settings.FINNHUB_API_KEY and now - last_finnhub > finnhub_gap:
            logger.info("[Ingest Agent] Finnhub refresh...")
            try:
                await fetch_finnhub_for_symbols(settings.YFINANCE_SYMBOLS)
                last_finnhub = now
            except Exception as e:
                logger.error(f"[Ingest Agent] Finnhub failed: {e}")

        # ── Alpha Vantage (daily — 25 req/day limit) ────────────────────────
        if settings.ALPHA_VANTAGE_API_KEY and now - last_alpha_vantage > alpha_vantage_gap:
            logger.info("[Ingest Agent] Alpha Vantage refresh...")
            try:
                await fetch_alpha_vantage_for_symbols(
                    settings.YFINANCE_SYMBOLS, max_symbols=3
                )
                last_alpha_vantage = now
            except Exception as e:
                logger.error(f"[Ingest Agent] Alpha Vantage failed: {e}")

        # ── SEC EDGAR company facts (daily) ─────────────────────────────────
        if now - last_sec > sec_gap:
            logger.info("[Ingest Agent] SEC refresh...")
            try:
                sec_data = await fetch_sec_data()
                for company_data in sec_data:
                    await raw_news_queue.put(
                        {
                            "headline": (
                                f"SEC Financial Data Update: "
                                f"{company_data.get('company_name', 'Unknown')}"
                            ),
                            "url": (
                                "https://data.sec.gov/api/xbrl/companyfacts/"
                                f"CIK{company_data.get('cik', '').zfill(10)}.json"
                            ),
                            "body": (
                                f"Updated financial data for "
                                f"{company_data.get('symbol', 'N/A')}"
                            ),
                            "published_at": company_data.get("fetched_at"),
                            "source": "SEC EDGAR",
                            "data_type": "sec_financial",
                            "raw_data": company_data,
                        }
                    )
                last_sec = now
            except Exception as e:
                logger.error(f"[Ingest Agent] SEC failed: {e}")

        # ── FRED macro (daily) ──────────────────────────────────────────────
        if settings.FRED_API_KEY and now - last_macro > macro_gap:
            logger.info("[Ingest Agent] FRED macro refresh...")
            try:
                await fetch_macro_indicators()
                last_macro = now
            except Exception as e:
                logger.error(f"[Ingest Agent] FRED failed: {e}")

        logger.info(
            f"[Ingest Agent] Cycle done. Sleeping {settings.INGEST_INTERVAL_SECONDS}s..."
        )
        await asyncio.sleep(settings.INGEST_INTERVAL_SECONDS)
