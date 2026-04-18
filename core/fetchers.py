"""
core/fetchers.py

Data fetchers for building a comprehensive LLM Wiki knowledge base.

Each function fetches data from a different source and saves raw JSON files
to RAW_DATA_DIR with consistent naming: {source}_{symbol_or_topic}_{YYYYMMDD_HHMM}.json

Data sources (all free):
- FRED API: Economic indicators (rates, inflation, unemployment, GDP)
- Reddit: Community sentiment from r/investing, r/stocks
- Google News RSS: Recent news for each symbol
- Market Sentiment: VIX + CNN Fear & Greed index
- Earnings Calendar: Upcoming earnings dates

SEC EDGAR fetching lives in `core/sec_client.py` (async httpx companyfacts
endpoint). The old `sec-edgar-downloader`-based path was removed in P1 —
it produced files in a different layout (`./sec-edgar-filings/`) that
`wiki_ingest` never routed anywhere, so it was dead weight.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import feedparser
import pandas as pd
import praw
import requests
import yfinance as yf
from fredapi import Fred
from loguru import logger

from core.settings import settings


def _get_timestamp() -> str:
    """Get consistent timestamp for file naming."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M")


async def _save_json(filepath: Path, data: dict) -> Path:
    """Save data as JSON file asynchronously."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(filepath, "w") as f:
        await f.write(json.dumps(data, indent=2, default=str))
    logger.debug(f"[Fetcher] Saved {filepath} ({filepath.stat().st_size} bytes)")
    return filepath


async def fetch_macro_indicators() -> Path | None:
    """Fetch key economic indicators from FRED API."""
    try:
        if not settings.FRED_API_KEY:
            logger.warning("[FRED] No API key configured, skipping macro data")
            return None

        logger.info("[FRED] Fetching macro economic indicators...")

        # Run FRED API calls in executor (sync library)
        loop = asyncio.get_event_loop()

        def _make_fred() -> Fred:
            return Fred(api_key=settings.FRED_API_KEY)

        fred = await loop.run_in_executor(None, _make_fred)

        # Fetch key indicators
        indicators = {
            "fed_funds_rate": "DFF",
            "cpi_inflation": "CPIAUCSL",
            "unemployment": "UNRATE",
            "gdp": "GDP",
        }

        macro_data = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "FRED",
            "indicators": {},
        }

        for name, series_id in indicators.items():
            try:
                # Get last 30 days of data
                def _get_series(sid: str = series_id) -> object:  # pandas.Series but avoid import
                    return fred.get_series(sid, limit=30)

                data = await loop.run_in_executor(None, _get_series)

                if not data.empty:
                    latest = data.iloc[-1]
                    macro_data["indicators"][name] = {
                        "series_id": series_id,
                        "latest_value": float(latest),
                        "latest_date": str(data.index[-1]),
                        "30_day_change": float(latest - data.iloc[0]) if len(data) > 1 else 0.0,
                    }

            except Exception as e:
                logger.warning(f"[FRED] Error fetching {series_id}: {e}")
                continue

        # Save macro data
        filename = f"macro_indicators_{_get_timestamp()}.json"
        filepath = Path(settings.RAW_DATA_DIR) / filename
        saved_path = await _save_json(filepath, macro_data)

        logger.info(f"[FRED] Saved macro indicators: {len(macro_data['indicators'])} series")
        return saved_path

    except Exception as e:
        logger.error(f"[FRED] Macro indicators fetch failed: {e}")
        return None


async def fetch_reddit_sentiment(symbols: list[str]) -> list[Path]:
    """Fetch Reddit sentiment from r/investing and r/stocks."""
    results: list[Path] = []

    try:
        if not all([settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET]):
            logger.warning("[Reddit] No credentials configured, skipping Reddit data")
            return results

        logger.info(f"[Reddit] Fetching sentiment for {len(symbols)} symbols...")

        # Initialize Reddit client
        loop = asyncio.get_event_loop()

        def _make_reddit() -> object:  # praw.Reddit, but avoid import for typing
            return praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
            )

        reddit = await loop.run_in_executor(None, _make_reddit)

        subreddits = ["investing", "stocks"]

        for symbol in symbols:
            try:
                symbol_posts = []

                for sub_name in subreddits:
                    # Search for posts mentioning the symbol.
                    # Bind loop vars into the lambdas explicitly — otherwise
                    # run_in_executor captures the *names*, not the values, and
                    # every iteration sees the final loop value (ruff B023).
                    search_query = f"{symbol} stock OR ${symbol}"
                    subreddit = await loop.run_in_executor(
                        None, lambda name=sub_name: reddit.subreddit(name)
                    )
                    posts = await loop.run_in_executor(
                        None,
                        lambda sr=subreddit, q=search_query: list(
                            sr.search(q, sort="hot", time_filter="week", limit=15)
                        ),
                    )

                    for post in posts:
                        symbol_posts.append(
                            {
                                "title": post.title,
                                "score": post.score,
                                "body": post.selftext[:1000] if post.selftext else "",
                                "created_utc": post.created_utc,
                                "subreddit": sub_name,
                                "url": f"https://reddit.com{post.permalink}",
                                "num_comments": post.num_comments,
                            }
                        )

                # Save Reddit data for this symbol
                reddit_data = {
                    "symbol": symbol,
                    "posts": symbol_posts,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "reddit",
                    "subreddits": subreddits,
                }

                filename = f"reddit_{symbol}_{_get_timestamp()}.json"
                filepath = Path(settings.RAW_DATA_DIR) / filename
                saved_path = await _save_json(filepath, reddit_data)
                results.append(saved_path)

                logger.info(f"[Reddit] Saved {len(symbol_posts)} posts for {symbol}")

                # Rate limiting
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"[Reddit] Error fetching {symbol}: {e}")
                continue

    except Exception as e:
        logger.error(f"[Reddit] Reddit client error: {e}")

    return results


async def fetch_google_news_rss(symbols: list[str]) -> list[Path]:
    """Fetch Google News RSS feeds for each symbol."""
    results: list[Path] = []

    for symbol in symbols:
        try:
            logger.info(f"[GoogleNews] Fetching news for {symbol}")

            # Google News RSS URL
            url = f"https://news.google.com/rss/search?q={symbol}+stock+news&hl=en-US&gl=US&ceid=US:en"

            # Fetch RSS feed
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, url)

            articles = []
            for entry in feed.entries[:20]:  # Limit to 20 articles
                articles.append(
                    {
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "summary": entry.get("summary", ""),
                        "source": entry.get("source", {}).get("title", "Google News")
                        if entry.get("source")
                        else "Google News",
                    }
                )

            # Save Google News data
            news_data = {
                "symbol": symbol,
                "articles": articles,
                "fetched_at": datetime.now(UTC).isoformat(),
                "source": "google_news_rss",
                "feed_url": url,
            }

            filename = f"googlenews_{symbol}_{_get_timestamp()}.json"
            filepath = Path(settings.RAW_DATA_DIR) / filename
            saved_path = await _save_json(filepath, news_data)
            results.append(saved_path)

            logger.info(f"[GoogleNews] Saved {len(articles)} articles for {symbol}")

            # Rate limiting
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"[GoogleNews] Error fetching {symbol}: {e}")
            continue

    return results


async def fetch_vix_and_fear_greed() -> Path | None:
    """Fetch VIX and CNN Fear & Greed index."""
    try:
        logger.info("[MarketSentiment] Fetching VIX and Fear & Greed...")

        sentiment_data = {"fetched_at": datetime.now(UTC).isoformat(), "source": "market_sentiment"}

        # Fetch VIX via yfinance
        loop = asyncio.get_event_loop()

        def _make_vix_ticker() -> object:  # yfinance.Ticker
            return yf.Ticker("^VIX")

        def _get_vix_hist(ticker: object) -> object:  # pandas.DataFrame
            return ticker.history(period="5d")  # type: ignore

        vix_ticker = await loop.run_in_executor(None, _make_vix_ticker)
        vix_hist = await loop.run_in_executor(None, lambda: _get_vix_hist(vix_ticker))

        if not vix_hist.empty:
            latest_vix = float(vix_hist["Close"].iloc[-1])
            sentiment_data["vix"] = {
                "current_level": latest_vix,
                "5_day_data": vix_hist["Close"].to_dict(),
                "interpretation": (
                    "Low volatility (calm market)"
                    if latest_vix < 15
                    else "Moderate volatility"
                    if latest_vix < 25
                    else "High volatility (fear/uncertainty)"
                ),
            }

        # Fetch CNN Fear & Greed (web scraping)
        try:
            fear_greed_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
            response = await loop.run_in_executor(
                None, lambda: requests.get(fear_greed_url, timeout=10)
            )

            if response.status_code == 200:
                fg_data = response.json()
                if fg_data and "fear_and_greed" in fg_data:
                    fg_score = fg_data["fear_and_greed"]["score"]
                    sentiment_data["fear_greed"] = {
                        "score": fg_score,
                        "rating": fg_data["fear_and_greed"].get("rating", "Unknown"),
                        "interpretation": (
                            "Extreme Fear"
                            if fg_score < 25
                            else "Fear"
                            if fg_score < 45
                            else "Neutral"
                            if fg_score < 55
                            else "Greed"
                            if fg_score < 75
                            else "Extreme Greed"
                        ),
                    }
        except Exception as e:
            logger.warning(f"[MarketSentiment] Could not fetch Fear & Greed: {e}")

        # Save market sentiment data
        filename = f"market_sentiment_{_get_timestamp()}.json"
        filepath = Path(settings.RAW_DATA_DIR) / filename
        saved_path = await _save_json(filepath, sentiment_data)

        logger.info("[MarketSentiment] Saved VIX and Fear & Greed data")
        return saved_path

    except Exception as e:
        logger.error(f"[MarketSentiment] Error: {e}")
        return None


async def fetch_earnings_calendar(symbols: list[str]) -> Path | None:
    """Fetch upcoming earnings dates for symbols."""
    try:
        logger.info(f"[Earnings] Fetching earnings calendar for {len(symbols)} symbols...")

        earnings_data = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": "earnings_calendar",
            "companies": {},
        }

        loop = asyncio.get_event_loop()

        for symbol in symbols:
            try:

                def _make_ticker(s: str = symbol) -> object:  # yfinance.Ticker
                    return yf.Ticker(s)

                def _get_calendar(t: object) -> object:  # pandas.DataFrame | None
                    return t.calendar  # type: ignore

                ticker = await loop.run_in_executor(None, _make_ticker)
                calendar = await loop.run_in_executor(None, lambda t=ticker: _get_calendar(t))

                if calendar is not None and not calendar.empty:
                    # Convert to serializable format
                    earnings_dates = []
                    for date, row in calendar.iterrows():  # type: ignore
                        earnings_dates.append(
                            {
                                "date": str(date),
                                "earnings_estimate": float(row.get("Earnings Estimate", 0))  # type: ignore
                                if pd.notna(row.get("Earnings Estimate"))
                                else None,
                                "revenue_estimate": float(row.get("Revenue Estimate", 0))  # type: ignore
                                if pd.notna(row.get("Revenue Estimate"))
                                else None,
                            }
                        )

                    earnings_data["companies"][symbol] = {
                        "upcoming_earnings": earnings_dates,
                        "next_earnings_date": str(calendar.index[0])  # type: ignore
                        if not calendar.empty  # type: ignore
                        else None,
                    }

                    # Check if earnings are within 7 days
                    if not calendar.empty:  # type: ignore
                        next_date = calendar.index[0]  # type: ignore
                        days_until = (next_date - datetime.now().date()).days
                        if days_until <= 7:
                            earnings_data["companies"][symbol]["high_priority"] = True
                            earnings_data["companies"][symbol]["days_until_earnings"] = days_until

            except Exception as e:
                logger.warning(f"[Earnings] Error fetching calendar for {symbol}: {e}")
                continue

        # Save earnings calendar
        filename = f"earnings_calendar_{_get_timestamp()}.json"
        filepath = Path(settings.RAW_DATA_DIR) / filename
        saved_path = await _save_json(filepath, earnings_data)

        logger.info(f"[Earnings] Saved calendar for {len(earnings_data['companies'])} companies")
        return saved_path

    except Exception as e:
        logger.error(f"[Earnings] Error: {e}")
        return None
