"""
core/fetchers.py

Data fetchers for building a comprehensive LLM Wiki knowledge base.

Each function fetches data from a different source and saves raw JSON files
to DATA_RAW_DIR with consistent naming: {source}_{symbol_or_topic}_{YYYYMMDD_HHMM}.json

Data sources (all free):
- SEC EDGAR: Company filings (8-K, 10-Q)
- FRED API: Economic indicators (rates, inflation, unemployment, GDP)
- Reddit: Community sentiment from r/investing, r/stocks
- Google News RSS: Recent news for each symbol
- Market Sentiment: VIX + CNN Fear & Greed index
- Earnings Calendar: Upcoming earnings dates
"""

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

import aiofiles
import feedparser
import pandas as pd
import praw
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from fredapi import Fred
from loguru import logger
from sec_edgar_downloader import Downloader

from core.settings import settings


def _get_timestamp() -> str:
    """Get consistent timestamp for file naming."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


async def _save_json(filepath: Path, data: dict) -> Path:
    """Save data as JSON file asynchronously."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(filepath, 'w') as f:
        await f.write(json.dumps(data, indent=2, default=str))
    logger.debug(f"[Fetcher] Saved {filepath} ({filepath.stat().st_size} bytes)")
    return filepath


async def fetch_sec_filings(symbols: list[str], filing_types: list[str]) -> list[Path]:
    """
    Fetch SEC filings for symbols using sec-edgar-downloader.
    Only fetch filings from the last 30 days to avoid huge downloads.
    """
    results = []
    
    try:
        # Create downloader (runs in thread to avoid blocking)
        loop = asyncio.get_event_loop()
        downloader = await loop.run_in_executor(None, lambda: Downloader("Company", settings.SEC_USER_AGENT))
        
        # Calculate date range (last 30 days)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        for symbol in symbols:
            for filing_type in filing_types:
                try:
                    logger.info(f"[SEC] Fetching {filing_type} filings for {symbol} (last 30 days)")
                    
                    # Download filings (this creates a local directory structure)
                    await loop.run_in_executor(
                        None,
                        lambda: downloader.get(
                            filing_type,
                            symbol,
                            after=start_date.strftime("%Y-%m-%d"),
                            before=end_date.strftime("%Y-%m-%d"),
                            download_details=True
                        )
                    )
                    
                    # Find downloaded files and convert to our JSON format
                    download_dir = Path("sec-edgar-filings") / symbol / filing_type
                    if download_dir.exists():
                        for filing_dir in download_dir.iterdir():
                            if filing_dir.is_dir():
                                # Look for the main filing file
                                filing_files = list(filing_dir.glob("*.txt")) + list(filing_dir.glob("*.htm"))
                                if filing_files:
                                    filing_file = filing_files[0]
                                    filing_text = filing_file.read_text(encoding='utf-8', errors='ignore')
                                    
                                    # Create our standardized JSON
                                    filing_data = {
                                        "symbol": symbol,
                                        "filing_type": filing_type,
                                        "date": filing_dir.name.split("-")[0] if "-" in filing_dir.name else _get_timestamp()[:8],
                                        "text": filing_text[:50000],  # Limit to 50k chars
                                        "url": f"https://www.sec.gov/Archives/edgar/data/{symbol}",
                                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                                        "source": "sec-edgar-downloader"
                                    }
                                    
                                    # Save to our standard location
                                    filename = f"sec_{symbol}_{filing_type}_{_get_timestamp()}.json"
                                    filepath = Path(settings.DATA_RAW_DIR) / filename
                                    saved_path = await _save_json(filepath, filing_data)
                                    results.append(saved_path)
                    
                    # Respect SEC rate limits
                    await asyncio.sleep(0.15)
                    
                except Exception as e:
                    logger.error(f"[SEC] Error fetching {filing_type} for {symbol}: {e}")
                    continue
    
    except Exception as e:
        logger.error(f"[SEC] SEC downloader error: {e}")
    
    logger.info(f"[SEC] Fetched {len(results)} filing files")
    return results


async def fetch_macro_indicators() -> Path:
    """Fetch key economic indicators from FRED API."""
    try:
        if not settings.FRED_API_KEY:
            logger.warning("[FRED] No API key configured, skipping macro data")
            return None
        
        logger.info("[FRED] Fetching macro economic indicators...")
        
        # Run FRED API calls in executor (sync library)
        loop = asyncio.get_event_loop()
        fred = await loop.run_in_executor(None, lambda: Fred(api_key=settings.FRED_API_KEY))
        
        # Fetch key indicators
        indicators = {
            "fed_funds_rate": "DFF",
            "cpi_inflation": "CPIAUCSL", 
            "unemployment": "UNRATE",
            "gdp": "GDP"
        }
        
        macro_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "FRED",
            "indicators": {}
        }
        
        for name, series_id in indicators.items():
            try:
                # Get last 30 days of data
                data = await loop.run_in_executor(
                    None, 
                    lambda sid=series_id: fred.get_series(sid, limit=30)
                )
                
                if not data.empty:
                    latest = data.iloc[-1]
                    macro_data["indicators"][name] = {
                        "series_id": series_id,
                        "latest_value": float(latest),
                        "latest_date": str(data.index[-1]),
                        "30_day_change": float(latest - data.iloc[0]) if len(data) > 1 else 0.0
                    }
                    
            except Exception as e:
                logger.warning(f"[FRED] Error fetching {series_id}: {e}")
                continue
        
        # Save macro data
        filename = f"macro_indicators_{_get_timestamp()}.json"
        filepath = Path(settings.DATA_RAW_DIR) / filename
        saved_path = await _save_json(filepath, macro_data)
        
        logger.info(f"[FRED] Saved macro indicators: {len(macro_data['indicators'])} series")
        return saved_path
        
    except Exception as e:
        logger.error(f"[FRED] Macro indicators fetch failed: {e}")
        return None


async def fetch_reddit_sentiment(symbols: list[str]) -> list[Path]:
    """Fetch Reddit sentiment from r/investing and r/stocks."""
    results = []
    
    try:
        if not all([settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET]):
            logger.warning("[Reddit] No credentials configured, skipping Reddit data")
            return results
        
        logger.info(f"[Reddit] Fetching sentiment for {len(symbols)} symbols...")
        
        # Initialize Reddit client
        loop = asyncio.get_event_loop()
        reddit = await loop.run_in_executor(
            None,
            lambda: praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT
            )
        )
        
        subreddits = ['investing', 'stocks']
        
        for symbol in symbols:
            try:
                symbol_posts = []
                
                for sub_name in subreddits:
                    # Search for posts mentioning the symbol
                    search_query = f"{symbol} stock OR ${symbol}"
                    subreddit = await loop.run_in_executor(None, lambda: reddit.subreddit(sub_name))
                    posts = await loop.run_in_executor(
                        None,
                        lambda: list(subreddit.search(search_query, sort='hot', time_filter='week', limit=15))
                    )
                    
                    for post in posts:
                        symbol_posts.append({
                            "title": post.title,
                            "score": post.score,
                            "body": post.selftext[:1000] if post.selftext else "",
                            "created_utc": post.created_utc,
                            "subreddit": sub_name,
                            "url": f"https://reddit.com{post.permalink}",
                            "num_comments": post.num_comments
                        })
                
                # Save Reddit data for this symbol
                reddit_data = {
                    "symbol": symbol,
                    "posts": symbol_posts,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "source": "reddit",
                    "subreddits": subreddits
                }
                
                filename = f"reddit_{symbol}_{_get_timestamp()}.json"
                filepath = Path(settings.DATA_RAW_DIR) / filename
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
    results = []
    
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
                articles.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", ""),
                    "source": entry.get("source", {}).get("title", "Google News") if entry.get("source") else "Google News"
                })
            
            # Save Google News data
            news_data = {
                "symbol": symbol,
                "articles": articles,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "google_news_rss",
                "feed_url": url
            }
            
            filename = f"googlenews_{symbol}_{_get_timestamp()}.json"
            filepath = Path(settings.DATA_RAW_DIR) / filename
            saved_path = await _save_json(filepath, news_data)
            results.append(saved_path)
            
            logger.info(f"[GoogleNews] Saved {len(articles)} articles for {symbol}")
            
            # Rate limiting
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"[GoogleNews] Error fetching {symbol}: {e}")
            continue
    
    return results


async def fetch_vix_and_fear_greed() -> Path:
    """Fetch VIX and CNN Fear & Greed index."""
    try:
        logger.info("[MarketSentiment] Fetching VIX and Fear & Greed...")
        
        sentiment_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "market_sentiment"
        }
        
        # Fetch VIX via yfinance
        loop = asyncio.get_event_loop()
        vix_ticker = await loop.run_in_executor(None, lambda: yf.Ticker("^VIX"))
        vix_hist = await loop.run_in_executor(None, lambda: vix_ticker.history(period="5d"))
        
        if not vix_hist.empty:
            latest_vix = float(vix_hist['Close'].iloc[-1])
            sentiment_data["vix"] = {
                "current_level": latest_vix,
                "5_day_data": vix_hist['Close'].to_dict(),
                "interpretation": (
                    "Low volatility (calm market)" if latest_vix < 15 else
                    "Moderate volatility" if latest_vix < 25 else
                    "High volatility (fear/uncertainty)"
                )
            }
        
        # Fetch CNN Fear & Greed (web scraping)
        try:
            fear_greed_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(fear_greed_url, timeout=10)
            )
            
            if response.status_code == 200:
                fg_data = response.json()
                if fg_data and 'fear_and_greed' in fg_data:
                    fg_score = fg_data['fear_and_greed']['score']
                    sentiment_data["fear_greed"] = {
                        "score": fg_score,
                        "rating": fg_data['fear_and_greed'].get('rating', 'Unknown'),
                        "interpretation": (
                            "Extreme Fear" if fg_score < 25 else
                            "Fear" if fg_score < 45 else
                            "Neutral" if fg_score < 55 else
                            "Greed" if fg_score < 75 else
                            "Extreme Greed"
                        )
                    }
        except Exception as e:
            logger.warning(f"[MarketSentiment] Could not fetch Fear & Greed: {e}")
        
        # Save market sentiment data
        filename = f"market_sentiment_{_get_timestamp()}.json"
        filepath = Path(settings.DATA_RAW_DIR) / filename
        saved_path = await _save_json(filepath, sentiment_data)
        
        logger.info("[MarketSentiment] Saved VIX and Fear & Greed data")
        return saved_path
        
    except Exception as e:
        logger.error(f"[MarketSentiment] Error: {e}")
        return None


async def fetch_earnings_calendar(symbols: list[str]) -> Path:
    """Fetch upcoming earnings dates for symbols."""
    try:
        logger.info(f"[Earnings] Fetching earnings calendar for {len(symbols)} symbols...")
        
        earnings_data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "earnings_calendar",
            "companies": {}
        }
        
        loop = asyncio.get_event_loop()
        
        for symbol in symbols:
            try:
                ticker = await loop.run_in_executor(None, lambda s=symbol: yf.Ticker(s))
                calendar = await loop.run_in_executor(None, lambda: ticker.calendar)
                
                if calendar is not None and not calendar.empty:
                    # Convert to serializable format
                    earnings_dates = []
                    for date, row in calendar.iterrows():
                        earnings_dates.append({
                            "date": str(date),
                            "earnings_estimate": float(row.get('Earnings Estimate', 0)) if pd.notna(row.get('Earnings Estimate')) else None,
                            "revenue_estimate": float(row.get('Revenue Estimate', 0)) if pd.notna(row.get('Revenue Estimate')) else None,
                        })
                    
                    earnings_data["companies"][symbol] = {
                        "upcoming_earnings": earnings_dates,
                        "next_earnings_date": str(calendar.index[0]) if not calendar.empty else None
                    }
                    
                    # Check if earnings are within 7 days
                    if not calendar.empty:
                        next_date = calendar.index[0]
                        days_until = (next_date - datetime.now().date()).days
                        if days_until <= 7:
                            earnings_data["companies"][symbol]["high_priority"] = True
                            earnings_data["companies"][symbol]["days_until_earnings"] = days_until
                
            except Exception as e:
                logger.warning(f"[Earnings] Error fetching calendar for {symbol}: {e}")
                continue
        
        # Save earnings calendar
        filename = f"earnings_calendar_{_get_timestamp()}.json"
        filepath = Path(settings.DATA_RAW_DIR) / filename
        saved_path = await _save_json(filepath, earnings_data)
        
        logger.info(f"[Earnings] Saved calendar for {len(earnings_data['companies'])} companies")
        return saved_path
        
    except Exception as e:
        logger.error(f"[Earnings] Error: {e}")
        return None

