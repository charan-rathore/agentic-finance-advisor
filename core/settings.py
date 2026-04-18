"""
core/settings.py

Single source of truth for all configuration.
Reads from .env file (local dev) or environment variables (Docker).
All agents import `settings` from here — never call os.getenv() directly in agents.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── Gemini ── FREE TIER ONLY ──────────────────────────────────────────────
    # gemini-1.5-flash is the free model. Do NOT change to gemini-pro.
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_RETRY_MAX: int = int(os.getenv("GEMINI_RETRY_MAX", "5"))
    GEMINI_RETRY_BACKOFF_BASE: float = float(os.getenv("GEMINI_RETRY_BACKOFF_BASE", "2"))

    # ── Storage ───────────────────────────────────────────────────────────────
    # SQLite: a single file, no server needed. Perfect for personal projects.
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "./data/finance.db")
    WIKI_DIR: str = os.getenv("WIKI_DIR", "./data/wiki")
    WIKI_INGEST_EVERY_N_ARTICLES: int = int(os.getenv("WIKI_INGEST_EVERY_N_ARTICLES", "5"))
    WIKI_LINT_INTERVAL_HOURS: float = float(os.getenv("WIKI_LINT_INTERVAL_HOURS", "6"))

    # ── Data sources (all free, no API key required) ──────────────────────────
    YFINANCE_SYMBOLS: list[str] = [
        s.strip()
        for s in os.getenv("YFINANCE_SYMBOLS", "AAPL,MSFT,GOOGL,TSLA,AMZN").split(",")
        if s.strip()
    ]
    NEWS_RSS_FEEDS: list[str] = [
        u.strip()
        for u in os.getenv(
            "NEWS_RSS_FEEDS",
            "https://feeds.finance.yahoo.com/rss/2.0/headline",
        ).split(",")
        if u.strip()
    ]

    # ── Timing ────────────────────────────────────────────────────────────────
    INGEST_INTERVAL_SECONDS: int = int(os.getenv("INGEST_INTERVAL_SECONDS", "300"))
    ANALYSIS_INTERVAL_SECONDS: int = int(os.getenv("ANALYSIS_INTERVAL_SECONDS", "600"))

    # ── SEC EDGAR API ─────────────────────────────────────────────────────────
    # SEC requires User-Agent header with contact info (free, no API key needed)
    SEC_USER_AGENT: str = os.getenv("SEC_USER_AGENT", "Personal Finance Advisor bot@example.com")
    SEC_BASE_URL: str = "https://data.sec.gov/api/xbrl"
    
    # ── Data Storage ──────────────────────────────────────────────────────────
    # Historical note: `DATA_RAW_DIR` was a duplicate alias. Kept as a property for
    # backward compatibility; writes should use RAW_DATA_DIR.
    RAW_DATA_DIR: str = os.getenv("RAW_DATA_DIR", os.getenv("DATA_RAW_DIR", "./data/raw"))
    PROCESSED_DATA_DIR: str = os.getenv("PROCESSED_DATA_DIR", "./data/processed")

    @property
    def DATA_RAW_DIR(self) -> str:  # noqa: N802 — preserved name used by older callers
        return self.RAW_DATA_DIR

    # ── Extended Data Sources ─────────────────────────────────────────────────
    FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "FinanceBot/1.0")
    SEC_FILING_TYPES: list[str] = [
        s.strip()
        for s in os.getenv("SEC_FILING_TYPES", "8-K,10-Q").split(",")
        if s.strip()
    ]

    # ── Fetch cadences (hours) — used by ingest agent to throttle heavy sources ─
    SEC_FETCH_INTERVAL_HOURS: float = float(os.getenv("SEC_FETCH_INTERVAL_HOURS", "24"))
    MACRO_FETCH_INTERVAL_HOURS: float = float(os.getenv("MACRO_FETCH_INTERVAL_HOURS", "24"))
    ALPHA_VANTAGE_FETCH_INTERVAL_HOURS: float = float(
        os.getenv("ALPHA_VANTAGE_FETCH_INTERVAL_HOURS", "24")
    )
    FINNHUB_FETCH_INTERVAL_HOURS: float = float(
        os.getenv("FINNHUB_FETCH_INTERVAL_HOURS", "1")
    )

    # ── Wiki Staleness Configuration ──────────────────────────────────────────
    WIKI_LINT_STALE_HOURS_NEWS: int = int(os.getenv("WIKI_LINT_STALE_HOURS_NEWS", "12"))
    WIKI_LINT_STALE_HOURS_PRICE: int = int(os.getenv("WIKI_LINT_STALE_HOURS_PRICE", "6"))
    WIKI_LINT_STALE_HOURS_SEC: int = int(os.getenv("WIKI_LINT_STALE_HOURS_SEC", "168"))
    WIKI_LINT_STALE_HOURS_MACRO: int = int(os.getenv("WIKI_LINT_STALE_HOURS_MACRO", "72"))

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy connection string for SQLite."""
        return f"sqlite:///{self.SQLITE_PATH}"


settings = Settings()
