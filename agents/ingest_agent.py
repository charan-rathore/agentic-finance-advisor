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
import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import feedparser
import yfinance as yf
from loguru import logger
from sqlalchemy.orm import Session, sessionmaker

from core.alpha_vantage_client import fetch_alpha_vantage_for_symbols
from core.fetch_state import record_failure, record_success, should_fetch
from core.fetchers import fetch_macro_indicators
from core.fetchers_india import (
    fetch_amfi_nav,
    fetch_india_news_rss,
    fetch_india_prices,
    fetch_rbi_rates,
)
from core.finnhub_client import fetch_finnhub_for_symbols
from core.models import MarketSnapshot, NewsArticle, init_db
from core.queues import raw_india_queue, raw_market_queue, raw_news_queue
from core.sec_client import fetch_financial_data_for_symbols
from core.settings import settings

# Hard ceiling for any single slow-source fetch block. Belt-and-suspenders on
# top of per-client timeouts so one wedged API can never stall the ingest loop.
_HEAVY_FETCH_TIMEOUT_SECONDS = 180.0


# NOTE: the runtime staleness threshold lives in ``agents/storage_agent.py``
# (where the UI's data-label decision is computed). The previous module-level
# constant here was unused — removed to avoid the impression that tweaking it
# changes behaviour.


def _yf_snapshot(symbol: str) -> dict | None:
    """Blocking yfinance call for one US symbol.

    Enriched to return:
      price, prev_close, change_abs, change_pct,
      fetched_at, data_label ("Live" | "Previous Close" | "Delayed"),
      source, volume.

    Strategy:
    1. fast_info: last_price + regular_market_previous_close (cheapest).
    2. history(period="5d") fallback: use last non-NaN close as price,
       second-to-last as prev_close.
    3. Return None and log a warning when no price can be determined.

    Runs in a thread via run_in_executor so the event loop is never blocked.
    """
    ticker = yf.Ticker(symbol)
    fetched_at = datetime.now(UTC)
    price: float | None = None
    prev_close: float | None = None
    volume: float = 0.0
    tz = "America/New_York"

    # ── Attempt 1: fast_info ──────────────────────────────────────────────────
    try:
        fi = ticker.fast_info
        raw_price = getattr(fi, "last_price", None)
        raw_prev = getattr(fi, "regular_market_previous_close", None) or getattr(
            fi, "previous_close", None
        )
        tz = getattr(fi, "timezone", "America/New_York") or "America/New_York"

        if raw_price is not None and not math.isnan(float(raw_price)):
            price = float(raw_price)
        if raw_prev is not None and not math.isnan(float(raw_prev)):
            prev_close = float(raw_prev)

        vol = getattr(fi, "last_volume", None) or getattr(
            fi, "three_month_average_volume", None
        )
        if vol is not None:
            volume = float(vol)

    except Exception as e:
        logger.debug(f"[Ingest] fast_info failed for {symbol}: {e}")

    # ── Attempt 2: history fallback ───────────────────────────────────────────
    if price is None:
        try:
            hist = ticker.history(period="5d", auto_adjust=False)
            if not hist.empty:
                closes = hist["Close"].dropna()
                if not closes.empty:
                    price = float(closes.iloc[-1])
                    if "Volume" in hist.columns:
                        volume = float(
                            hist["Volume"].iloc[hist.index.get_loc(closes.index[-1])]
                        )
                    if len(closes) >= 2 and prev_close is None:
                        prev_close = float(closes.iloc[-2])
        except Exception as e:
            logger.warning(f"[Ingest] history fallback failed for {symbol}: {e}")

    if price is None:
        logger.warning(f"[Ingest] No price data available for {symbol} — skipping")
        return None

    # ── Derived fields ────────────────────────────────────────────────────────
    change_abs: float | None = None
    change_pct: float | None = None
    if prev_close is not None and prev_close != 0:
        change_abs = round(price - prev_close, 2)
        change_pct = round((price - prev_close) / prev_close * 100, 2)

    # ── Data freshness label ──────────────────────────────────────────────────
    # NYSE/NASDAQ regular hours: Mon–Fri 09:30–16:00 ET (EST/EDT auto-handled)
    et_now = fetched_at.astimezone(ZoneInfo("America/New_York"))
    weekday = et_now.weekday()
    hour = et_now.hour + et_now.minute / 60
    market_open = weekday < 5 and 9.5 <= hour <= 16.0

    if market_open:
        data_label = "Live"
    else:
        data_label = "Previous Close"

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "prev_close": round(prev_close, 2) if prev_close is not None else None,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "volume": round(volume, 0),
        "exchange_tz": tz,
        "fetched_at": fetched_at.isoformat(),
        "data_label": data_label,
        "captured_at": fetched_at.isoformat(),
        "source": "yfinance",
        "market_time": fetched_at.strftime("%Y-%m-%d %H:%M UTC"),
    }


async def fetch_market_data(engine: object) -> list[dict]:  # engine: sqlalchemy.Engine
    """
    Fetch current stock prices using yfinance.

    Uses `fast_info.last_price` when available and falls back to a 1-day history
    close. Symbols with no data are skipped (common outside market hours, or when
    Yahoo is temporarily rate-limiting).
    """
    results: list[dict] = []
    pending_rows: list[MarketSnapshot] = []
    loop = asyncio.get_event_loop()

    for symbol in settings.YFINANCE_SYMBOLS:
        try:
            snap = await loop.run_in_executor(None, _yf_snapshot, symbol)
            if snap is None:
                logger.warning(
                    f"[Ingest] No price data for {symbol} (market closed or rate-limited)"
                )
                continue

            results.append(snap)
            pending_rows.append(
                MarketSnapshot(
                    symbol=snap["symbol"],
                    price=snap["price"],
                    volume=snap["volume"],
                    captured_at=datetime.now(UTC),
                )
            )

            logger.info(f"[Ingest] {symbol}: ${snap['price']:.2f}")

        except Exception as e:
            logger.error(f"[Ingest] Error fetching {symbol}: {e}")

    if pending_rows:
        try:
            with Session(engine) as session:
                session.add_all(pending_rows)
                session.commit()
        except Exception as e:
            logger.error(f"[Ingest] Batched market_snapshots commit failed: {e}")

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


async def fetch_news(engine: object) -> list[dict]:  # engine: sqlalchemy.Engine
    """
    Fetch news from RSS feeds using feedparser.
    Free, no API key, public feeds.
    """
    articles: list[dict] = []
    pending_rows: list[NewsArticle] = []
    loop = asyncio.get_event_loop()

    for feed_url in _default_news_feeds():
        try:
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            if feed.bozo and not feed.entries:
                logger.warning(f"[Ingest] Malformed/empty feed, skipping: {feed_url[:80]}")
                continue

            feed_source = feed.feed.get("title", feed_url) if hasattr(feed, "feed") else feed_url

            for entry in feed.entries[:15]:
                article = {
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "body": entry.get("summary", ""),
                    "published_at": entry.get("published", datetime.now(UTC).isoformat()),
                    "source": feed_source,
                }
                articles.append(article)
                pending_rows.append(
                    NewsArticle(
                        headline=article["headline"],
                        url=article["url"],
                        body=article["body"],
                        source=article["source"],
                        ingested_at=datetime.now(UTC),
                    )
                )

            logger.info(f"[Ingest] {len(feed.entries[:15])} articles from {feed_url[:80]}")

        except Exception as e:
            logger.error(f"[Ingest] Error fetching feed {feed_url}: {e}")

    if pending_rows:
        try:
            with Session(engine) as session:
                session.add_all(pending_rows)
                session.commit()
        except Exception as e:
            logger.error(f"[Ingest] Batched news_articles commit failed: {e}")

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


async def _guarded(
    coro: object, *, label: str, timeout: float = _HEAVY_FETCH_TIMEOUT_SECONDS
) -> object:
    """
    Run `coro` but never let it block the ingest loop for more than `timeout`
    seconds. Logs + returns `None` on timeout or exception so one wedged API
    cannot stall the whole agent.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        logger.error(f"[Ingest Agent] {label} timed out after {timeout}s — skipping")
    except Exception as e:
        logger.error(f"[Ingest Agent] {label} failed: {e}")
    return None


async def run() -> None:
    """
    Main ingest loop.

    Cadences (all driven by `.env`):
      - Price + news: every INGEST_INTERVAL_SECONDS (default 5 min)
      - Finnhub  (quotes/news/recommendations): every FINNHUB_FETCH_INTERVAL_HOURS
      - Alpha Vantage (quote/overview/income):  every ALPHA_VANTAGE_FETCH_INTERVAL_HOURS
      - SEC EDGAR company facts:                every SEC_FETCH_INTERVAL_HOURS
      - FRED macro indicators:                  every MACRO_FETCH_INTERVAL_HOURS

    Cadences are persisted in SQLite (`fetch_runs` table, see
    `core/fetch_state.py`) so restarts don't re-hammer every API. Every heavy
    fetch is wrapped in `_guarded(...)` with a hard timeout so one wedged
    upstream cannot stall the loop.
    """
    logger.info("[Ingest Agent] Starting...")
    engine = init_db(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)

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

        with SessionLocal() as state_session:
            # ── Finnhub (hourly by default) ─────────────────────────────────
            if settings.FINNHUB_API_KEY and should_fetch(
                state_session,
                "finnhub",
                interval_hours=settings.FINNHUB_FETCH_INTERVAL_HOURS,
            ):
                logger.info("[Ingest Agent] Finnhub refresh...")
                result = await _guarded(
                    fetch_finnhub_for_symbols(settings.YFINANCE_SYMBOLS),
                    label="Finnhub",
                )
                if result is not None:
                    record_success(state_session, "finnhub")
                else:
                    record_failure(state_session, "finnhub", error="timeout_or_exception")

            # ── Alpha Vantage (daily — 25 req/day limit) ────────────────────
            if settings.ALPHA_VANTAGE_API_KEY and should_fetch(
                state_session,
                "alpha_vantage",
                interval_hours=settings.ALPHA_VANTAGE_FETCH_INTERVAL_HOURS,
            ):
                logger.info("[Ingest Agent] Alpha Vantage refresh...")
                result = await _guarded(
                    fetch_alpha_vantage_for_symbols(settings.YFINANCE_SYMBOLS, max_symbols=3),
                    label="Alpha Vantage",
                )
                if result is not None:
                    record_success(state_session, "alpha_vantage")
                else:
                    record_failure(state_session, "alpha_vantage", error="timeout_or_exception")

            # ── SEC EDGAR company facts (daily) ─────────────────────────────
            if should_fetch(
                state_session,
                "sec",
                interval_hours=settings.SEC_FETCH_INTERVAL_HOURS,
            ):
                logger.info("[Ingest Agent] SEC refresh...")
                sec_data = await _guarded(fetch_sec_data(), label="SEC")
                if sec_data is not None:
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
                    record_success(state_session, "sec")
                else:
                    record_failure(state_session, "sec", error="timeout_or_exception")

            # ── FRED macro (daily) ──────────────────────────────────────────
            if settings.FRED_API_KEY and should_fetch(
                state_session,
                "fred",
                interval_hours=settings.MACRO_FETCH_INTERVAL_HOURS,
            ):
                logger.info("[Ingest Agent] FRED macro refresh...")
                result = await _guarded(fetch_macro_indicators(), label="FRED")
                if result is not None:
                    record_success(state_session, "fred")
                else:
                    record_failure(state_session, "fred", error="timeout_or_exception")

            # ── India: NSE prices + news (every ~5 min) ─────────────────────
            if should_fetch(
                state_session,
                "india_prices",
                interval_hours=settings.INDIA_PRICE_FETCH_INTERVAL_HOURS,
            ):
                logger.info("[Ingest Agent] India NSE prices refresh...")
                india_prices = await _guarded(fetch_india_prices(), label="India NSE prices")
                india_news = await _guarded(fetch_india_news_rss(), label="India news RSS")
                if india_prices is not None:
                    record_success(state_session, "india_prices")
                    # Publish to india queue so analysis agent can consume
                    await raw_india_queue.put(
                        {
                            "type": "india_cycle",
                            "prices": india_prices,
                            "news_batches": india_news or [],
                        }
                    )
                    logger.info(
                        f"[Ingest Agent] India: {len(india_prices)} prices, "
                        f"{len(india_news or [])} news batches -> queue"
                    )
                else:
                    record_failure(state_session, "india_prices", error="timeout_or_exception")

            # ── India: AMFI mutual fund NAVs (daily) ────────────────────────
            if should_fetch(
                state_session,
                "india_amfi_nav",
                interval_hours=settings.INDIA_MF_FETCH_INTERVAL_HOURS,
            ):
                logger.info("[Ingest Agent] India AMFI NAV refresh...")
                nav_records = await _guarded(fetch_amfi_nav(), label="India AMFI NAV")
                if nav_records is not None:
                    record_success(state_session, "india_amfi_nav")
                    await raw_india_queue.put({"type": "india_nav", "nav_records": nav_records})
                    logger.info(f"[Ingest Agent] India: {len(nav_records)} NAV records -> queue")
                else:
                    record_failure(state_session, "india_amfi_nav", error="timeout_or_exception")

            # ── India: RBI policy rates (daily) ─────────────────────────────
            if should_fetch(
                state_session,
                "india_rbi_rates",
                interval_hours=settings.INDIA_RBI_FETCH_INTERVAL_HOURS,
            ):
                logger.info("[Ingest Agent] India RBI rates refresh...")
                rbi_rates = await _guarded(fetch_rbi_rates(), label="India RBI rates")
                if rbi_rates is not None:
                    record_success(state_session, "india_rbi_rates")
                    await raw_india_queue.put({"type": "india_rbi", "rbi_rates": rbi_rates})
                    logger.info("[Ingest Agent] India: RBI rates -> queue")
                else:
                    record_failure(state_session, "india_rbi_rates", error="timeout_or_exception")

        logger.info(f"[Ingest Agent] Cycle done. Sleeping {settings.INGEST_INTERVAL_SECONDS}s...")
        await asyncio.sleep(settings.INGEST_INTERVAL_SECONDS)
