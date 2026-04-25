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
    # `RAW_DATA_DIR` is the single canonical name. A `DATA_RAW_DIR` alias used
    # to exist both as an env var and a property — it was removed because it
    # made it unclear which name was authoritative and produced two paths of
    # truth that had to be kept in sync.
    RAW_DATA_DIR: str = os.getenv("RAW_DATA_DIR", "./data/raw")
    PROCESSED_DATA_DIR: str = os.getenv("PROCESSED_DATA_DIR", "./data/processed")

    # ── Extended Data Sources ─────────────────────────────────────────────────
    # REQUIRED for full experience:
    #   GEMINI_API_KEY  — without it the advisor cannot synthesise answers.
    # OPTIONAL (agent degrades gracefully if absent):
    #   FRED_API_KEY          → macro indicators (CPI, unemployment, rates)
    #   ALPHA_VANTAGE_API_KEY → quote + fundamentals + income-statement backfill
    #   FINNHUB_API_KEY       → real-time quotes + per-company news + analyst trends
    #   REDDIT_*              → community sentiment from r/stocks, r/investing
    FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "FinanceBot/1.0")

    # ── Fetch cadences (hours) — used by ingest agent to throttle heavy sources ─
    SEC_FETCH_INTERVAL_HOURS: float = float(os.getenv("SEC_FETCH_INTERVAL_HOURS", "24"))
    MACRO_FETCH_INTERVAL_HOURS: float = float(os.getenv("MACRO_FETCH_INTERVAL_HOURS", "24"))
    ALPHA_VANTAGE_FETCH_INTERVAL_HOURS: float = float(
        os.getenv("ALPHA_VANTAGE_FETCH_INTERVAL_HOURS", "24")
    )
    FINNHUB_FETCH_INTERVAL_HOURS: float = float(os.getenv("FINNHUB_FETCH_INTERVAL_HOURS", "1"))

    # ── Wiki Staleness Configuration ──────────────────────────────────────────
    WIKI_LINT_STALE_HOURS_NEWS: int = int(os.getenv("WIKI_LINT_STALE_HOURS_NEWS", "12"))
    WIKI_LINT_STALE_HOURS_PRICE: int = int(os.getenv("WIKI_LINT_STALE_HOURS_PRICE", "6"))
    WIKI_LINT_STALE_HOURS_SEC: int = int(os.getenv("WIKI_LINT_STALE_HOURS_SEC", "168"))
    WIKI_LINT_STALE_HOURS_MACRO: int = int(os.getenv("WIKI_LINT_STALE_HOURS_MACRO", "72"))

    # ── Indian Market Data ────────────────────────────────────────────────────
    # NSE symbols use the `.NS` suffix with yfinance — no new library needed.
    # 10 liquid, large-cap NSE names covering banking, IT, energy, FMCG.
    INDIA_SYMBOLS: list[str] = [
        s.strip()
        for s in os.getenv(
            "INDIA_SYMBOLS",
            "RELIANCE.NS,TCS.NS,HDFCBANK.NS,INFY.NS,ICICIBANK.NS,"
            "HINDUNILVR.NS,BAJFINANCE.NS,SBIN.NS,ADANIENT.NS,WIPRO.NS",
        ).split(",")
        if s.strip()
    ]

    # Wiki directory for Indian knowledge base (parallel to WIKI_DIR for global)
    INDIA_WIKI_DIR: str = os.getenv("INDIA_WIKI_DIR", "./data/wiki_india")

    # Raw data sub-directory for Indian sources
    INDIA_RAW_DATA_DIR: str = os.getenv("INDIA_RAW_DATA_DIR", "./data/raw/india")

    # AMFI mutual fund scheme codes to track (mfapi.in, free, no key required).
    # Format: "code:friendly_name" comma-separated. Chosen for breadth of
    # investment categories relevant to Indian retail investors.
    INDIA_MF_SCHEMES: list[str] = [
        s.strip()
        for s in os.getenv(
            "INDIA_MF_SCHEMES",
            # Nifty 50 index fund — the SIP default for beginners
            "148360:LT_Nifty50_Index,"
            # ELSS tax-saving equity fund (80C benefit, 3-year lock-in)
            "135781:Mirae_ELSS_TaxSaver,"
            # Flexi-cap actively managed equity
            "122639:Parag_Parikh_FlexiCap,"
            # Liquid fund — short-term cash parking (< 91 days)
            "119800:SBI_Liquid,"
            # Balanced Advantage — auto-allocates equity/debt by market level
            "120377:ICICI_BalancedAdvantage,"
            # Short-duration debt — 1–3 year horizon, safer than equity
            "119016:HDFC_ShortTermDebt",
        ).split(",")
        if s.strip()
    ]

    # Fetch cadences for Indian sources (hours)
    INDIA_PRICE_FETCH_INTERVAL_HOURS: float = float(
        os.getenv("INDIA_PRICE_FETCH_INTERVAL_HOURS", "0.083")  # ~5 min
    )
    INDIA_MF_FETCH_INTERVAL_HOURS: float = float(
        os.getenv("INDIA_MF_FETCH_INTERVAL_HOURS", "24")  # NAV updates once daily
    )
    INDIA_RBI_FETCH_INTERVAL_HOURS: float = float(
        os.getenv("INDIA_RBI_FETCH_INTERVAL_HOURS", "24")  # Policy rates rarely change
    )
    INDIA_NEWS_FETCH_INTERVAL_HOURS: float = float(
        os.getenv("INDIA_NEWS_FETCH_INTERVAL_HOURS", "1")
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy connection string for SQLite."""
        return f"sqlite:///{self.SQLITE_PATH}"


settings = Settings()
