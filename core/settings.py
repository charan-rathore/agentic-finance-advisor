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
    RAW_DATA_DIR: str = os.getenv("RAW_DATA_DIR", "./data/raw")
    PROCESSED_DATA_DIR: str = os.getenv("PROCESSED_DATA_DIR", "./data/processed")

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy connection string for SQLite."""
        return f"sqlite:///{self.SQLITE_PATH}"


settings = Settings()
