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
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")

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

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy connection string for SQLite."""
        return f"sqlite:///{self.SQLITE_PATH}"


settings = Settings()
