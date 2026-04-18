# Multi-Agent AI Personal Finance Advisor — Cursor Execution Plan (v3)

> **⚠️ CURSOR AGENT INSTRUCTION PREAMBLE — READ BEFORE EVERY STEP**
>
> This document is the single source of truth for this project. Execute steps **one at a time**, in order.
> Do not skip ahead. After each step, check the ✅ Acceptance Criteria before moving on.
>
> **If you are being asked to work on an existing repo:** The developer may already have a folder
> skeleton from a previous plan. Your job is to **refactor existing files to match this plan** —
> do not delete folders, just replace file contents. If a file from the old plan is no longer needed,
> leave it empty with a comment explaining it was removed in v2.
>
> **HARD CONSTRAINT — FREE & OPEN SOURCE ONLY. Zero budget.**
> - ✅ Allowed: `yfinance`, `feedparser`, `textblob`, `chromadb`, `sentence-transformers`,
>   `google-generativeai` (Gemini free tier, model=`gemini-1.5-flash` only), `streamlit`,
>   `sqlalchemy` + SQLite, `docker`, `docker-compose`, `asyncio` (Python stdlib), `python-dotenv`,
>   `tenacity`, `loguru`, `pydantic`, `httpx`
> - ❌ Never use: OpenAI API, Anthropic API, PostgreSQL (use SQLite), Apache Kafka (use async queues),
>   any paid API tier, any cloud service that bills money
> - If Gemini rate limits are hit: use the retry logic already built into the code — do NOT suggest
>   upgrading to a paid tier
>
> **Project language:** Python 3.10+. All files need type hints and a module-level docstring.
>
> **Development environment:** Cursor IDE. Run all shell commands in Cursor's integrated terminal.

---

## Why This Architecture (Context for Resume + Learning)

This project teaches and demonstrates:

| What you build | What it shows on a resume |
|---|---|
| 3 specialized agents with defined roles | Multi-agent system design |
| Async message queues between agents | Event-driven architecture |
| LLM Wiki Knowledge Base (Karpathy pattern) | Advanced knowledge system design beyond RAG |
| Persistent, compounding markdown wiki | Stateful AI memory architecture |
| Gemini 1.5 Flash integration with retry | LLM API integration |
| SQLite via SQLAlchemy ORM | Database design & ORM usage |
| Streamlit dashboard | Full-stack AI app delivery |
| Docker + docker-compose | Containerization & DevOps basics |
| `.env` / secrets handling | Production-readiness awareness |

**Why not Kafka?** Kafka is the right tool at scale but requires a running broker, Zookeeper (or KRaft),
Docker networking, consumer group management, and offset tuning — all of which break in non-obvious ways
for a beginner. Python's `asyncio.Queue` is the same conceptual pattern (publish/subscribe, decoupled
producers and consumers) with zero infrastructure. Once this project works, swapping in Kafka is a
one-day task and a great story to tell in interviews: *"I designed it to be message-bus agnostic —
I started with async queues for rapid development and the architecture supports dropping in Kafka."*

**Why not PostgreSQL?** SQLite is a file on disk. No Docker service, no connection strings, no port
conflicts. For a single-user personal project it is functionally identical. Same SQLAlchemy ORM code
works for both — swapping to Postgres later is changing one line in settings.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Container                         │
│                                                                 │
│  ┌──────────────┐   queue: raw_data    ┌───────────────────┐   │
│  │              │ ──────────────────►  │                   │   │
│  │ Ingest Agent │                      │  Analysis Agent   │   │
│  │              │ ──────────────────►  │                   │   │
│  │ - yfinance   │   queue: raw_news    │ - sentiment       │   │
│  │ - RSS feeds  │                      │ - LLM Wiki KB     │   │
│  └──────────────┘                      │ - Gemini LLM      │   │
│                                        └────────┬──────────┘   │
│                                                 │               │
│                                      queue: insights            │
│                                                 │               │
│                                        ┌────────▼──────────┐   │
│                                        │   Storage Agent   │   │
│                                        │                   │   │
│                                        │ - SQLite (ORM)    │   │
│                                        │ - serves UI data  │   │
│                                        └───────────────────┘   │
│                                                 │               │
│                                        ┌────────▼──────────┐   │
│                                        │  Streamlit UI     │   │
│                                        │  (port 8501)      │   │
│                                        └───────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Three agents, three clear jobs:**
- **Ingest Agent** — fetches data (market prices + news), puts it on queues. Knows nothing about analysis.
- **Analysis Agent** — reads from queues, does sentiment + RAG + Gemini, puts insights on queue. Knows nothing about storage.
- **Storage Agent** — reads insights, saves to SQLite, answers UI queries. Knows nothing about data sources.

---

## Final Folder Structure

```
multi-agent-finance/
├── agents/
│   ├── __init__.py
│   ├── ingest_agent.py        # Agent 1: fetches market data + news
│   ├── analysis_agent.py      # Agent 2: sentiment + RAG + Gemini
│   └── storage_agent.py       # Agent 3: SQLite persistence + UI data access
│
├── core/
│   ├── __init__.py
│   ├── queues.py              # Shared asyncio.Queue instances (the "message bus")
│   ├── settings.py            # All config, loaded from .env
│   └── models.py              # SQLAlchemy ORM models (SQLite)
│
├── ui/
│   └── app.py                 # Streamlit dashboard
│
├── data/
│   ├── wiki/                  # LLM Wiki knowledge base (markdown files, auto-maintained)
│   │   ├── index.md           # Catalog of all wiki pages
│   │   ├── log.md             # Append-only operation log
│   │   ├── overview.md        # Rolling market synthesis
│   │   ├── stocks/            # Per-symbol entity pages (AAPL.md, MSFT.md, ...)
│   │   ├── concepts/          # Cross-stock theme pages
│   │   └── insights/          # Filed query answers (good answers compound the wiki)
│   └── finance.db             # SQLite database file (auto-created)
│
├── tests/
│   ├── __init__.py
│   ├── test_ingest.py
│   └── test_analysis.py
│
├── main.py                    # Entry point: starts all 3 agents as async tasks
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── LICENSE
```

> **Note for Cursor working on existing repo:** The old plan had `orchestrator/`, `db/`, `config/`,
> and 5 agent files. Map them as follows:
> - `config/settings.py` → `core/settings.py` (refactor in place)
> - `db/models.py` → `core/models.py` (simplify to SQLite)
> - `orchestrator/orchestrator.py` → replaced by `main.py`
> - `agents/ingest_agent.py` → keep, refactor to use queues not Kafka
> - `agents/sentiment_agent.py` + `agents/analysis_agent.py` → merge into new `agents/analysis_agent.py`
> - `agents/rag_agent.py` → logic moves inside `agents/analysis_agent.py`
> - `agents/report_agent.py` → becomes `agents/storage_agent.py`
> - Old `docker-compose.yml` (had Kafka + Postgres services) → replace with simplified version

---

## Queue Map (replaces Kafka Topic Map)

| Queue name (in `core/queues.py`) | Put by | Got by | Message shape |
|---|---|---|---|
| `raw_market_queue` | ingest_agent | analysis_agent | `{symbol, price, volume, timestamp}` |
| `raw_news_queue` | ingest_agent | analysis_agent | `{headline, url, body, published_at, source}` |
| `insights_queue` | analysis_agent | storage_agent | `{user_query, insight_text, sources, timestamp}` |

---

## Environment Variables

```dotenv
# ── Gemini (free tier — get key FREE at https://aistudio.google.com) ──
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-flash        # FREE model — do NOT change to gemini-pro

# ── Data sources (all free, no key needed) ──
YFINANCE_SYMBOLS=AAPL,MSFT,GOOGL,TSLA,AMZN
NEWS_RSS_FEEDS=https://feeds.finance.yahoo.com/rss/2.0/headline

# ── Local storage ──
SQLITE_PATH=./data/finance.db
CHROMA_PERSIST_DIR=./data/chroma_db

# ── Tuning ──
INGEST_INTERVAL_SECONDS=300          # how often ingest agent fetches (5 min)
ANALYSIS_INTERVAL_SECONDS=600        # how often analysis agent runs (10 min)
GEMINI_RETRY_MAX=5
GEMINI_RETRY_BACKOFF_BASE=2
LOG_LEVEL=INFO
```

---

## Step 1 — Repository Setup

**Context for Cursor:** This is step 1. The goal is a clean GitHub repo with the right base files.
If the repo already exists locally (developer started from an older plan), skip `git init` and
`git remote add` — just create/replace the files listed below.

### 1.1 — If starting fresh

```bash
cd ~/projects
mkdir multi-agent-finance && cd multi-agent-finance
git init
git branch -M main
# Replace the URL below with your actual GitHub repo URL
git remote add origin https://github.com/YOUR_USERNAME/multi-agent-finance.git
```

### 1.2 — Create or replace `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/

# Secrets — never commit the real .env
.env

# Local data (auto-generated, no need to version)
data/chroma_db/
data/finance.db
*.db

# Logs
logs/
*.log

# IDE
.idea/
.vscode/

# OS
.DS_Store
Thumbs.db
```

### 1.3 — Create or replace `.env.example`

```dotenv
GEMINI_API_KEY=YOUR_FREE_KEY_FROM_AISTUDIO_GOOGLE_COM
GEMINI_MODEL=gemini-1.5-flash
YFINANCE_SYMBOLS=AAPL,MSFT,GOOGL,TSLA,AMZN
NEWS_RSS_FEEDS=https://feeds.finance.yahoo.com/rss/2.0/headline
SQLITE_PATH=./data/finance.db
CHROMA_PERSIST_DIR=./data/chroma_db
INGEST_INTERVAL_SECONDS=300
ANALYSIS_INTERVAL_SECONDS=600
GEMINI_RETRY_MAX=5
GEMINI_RETRY_BACKOFF_BASE=2
LOG_LEVEL=INFO
```

```bash
# Copy for local use and fill in your real Gemini key
cp .env.example .env
```

### 1.4 — Create or replace `README.md`

```markdown
# Multi-Agent AI Personal Finance Advisor

A multi-agent AI system that monitors stock prices and financial news,
analyzes sentiment, retrieves relevant context (RAG), and generates
personalized investment insights using Google Gemini.

**All tools are free and open-source. Zero cost to run.**

## Tech Stack
- **Agents**: Python asyncio (3 specialized agents)
- **LLM**: Google Gemini 1.5 Flash (free tier)
- **Vector DB**: ChromaDB + sentence-transformers (local, offline)
- **Database**: SQLite via SQLAlchemy
- **Market data**: yfinance (no API key needed)
- **News**: RSS feeds via feedparser
- **UI**: Streamlit
- **Deployment**: Docker + docker-compose

## Quick Start
1. Get a free Gemini API key at https://aistudio.google.com/
2. `cp .env.example .env` and paste your key
3. `docker-compose up --build`
4. Open http://localhost:8501
```

### 1.5 — Set up Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# Windows: .venv\Scripts\activate

python --version                 # Must be 3.10+
```

### 1.6 — Create `requirements.txt`

```text
# Market data — free, no API key
yfinance==0.2.40

# News parsing — free, no API key
feedparser==6.0.11

# Sentiment — runs fully offline, no API cost
textblob==0.18.0
nltk==3.8.1

# Vector DB + embeddings — local, no cloud, no cost
# Model downloads once (~80MB), then runs offline forever
chromadb==0.5.3
sentence-transformers==3.0.1

# LLM — Gemini free tier only
google-generativeai==0.7.2

# Database ORM — SQLite (zero config, file on disk)
sqlalchemy==2.0.30

# UI
streamlit==1.36.0

# Utilities
python-dotenv==1.0.1
tenacity==8.4.1          # retry logic for Gemini rate limits
pydantic==2.7.4
loguru==0.7.2
httpx==0.27.0
```

```bash
pip install -r requirements.txt

# One-time downloads for NLP (free, local)
python -m textblob.download_corpora
python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"
```

### 1.7 — Create folder structure

```bash
mkdir -p agents core ui data/chroma_db data/seed tests docker logs
touch agents/__init__.py core/__init__.py tests/__init__.py
touch agents/ingest_agent.py agents/analysis_agent.py agents/storage_agent.py
touch core/queues.py core/settings.py core/models.py
touch ui/app.py main.py
```

### 1.8 — First commit

```bash
git add .
git commit -m "chore: project setup, requirements, base structure"
git push -u origin main
```

**✅ Acceptance Criteria:**
- `python --version` shows 3.10+
- `pip list` shows all packages from requirements.txt
- `ls agents/` shows 3 `.py` files
- `.env` exists locally but is NOT tracked by git (`git status` should not show `.env`)

---

## Step 2 — Core: Settings, Models, Queues

**Context for Cursor:** Before writing any agent, build the three shared modules in `core/`.
Every agent imports from here. This is the foundation — get it right before touching agents.

### 2.1 — Write `core/settings.py`

```python
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
    YFINANCE_SYMBOLS: list[str] = os.getenv(
        "YFINANCE_SYMBOLS", "AAPL,MSFT,GOOGL,TSLA,AMZN"
    ).split(",")
    NEWS_RSS_FEEDS: list[str] = os.getenv(
        "NEWS_RSS_FEEDS",
        "https://feeds.finance.yahoo.com/rss/2.0/headline",
    ).split(",")

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
```

### 2.2 — Write `core/models.py`

```python
"""
core/models.py

SQLAlchemy ORM models backed by SQLite.
SQLite = a single file on disk. No server, no Docker service, no config.
The same ORM code works with PostgreSQL later by changing one line in settings.py.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, create_engine
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()


class MarketSnapshot(Base):
    """One price reading per symbol per ingest cycle."""
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Float)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)


class NewsArticle(Base):
    """Raw news articles from RSS feeds."""
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    headline = Column(String(500), nullable=False)
    url = Column(String(1000))
    body = Column(Text)
    source = Column(String(100))
    ingested_at = Column(DateTime, default=datetime.utcnow)


class Insight(Base):
    """AI-generated insights from Gemini, with context of what drove them."""
    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_query = Column(Text)
    insight_text = Column(Text, nullable=False)
    sentiment_summary = Column(Text)   # brief summary of sentiment signal used
    sources = Column(Text)             # JSON list of source URLs from RAG
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)
    model_used = Column(String(50), default="gemini-1.5-flash")


def init_db(database_url: str):
    """
    Create all tables if they don't exist.
    Safe to call every time the app starts — won't overwrite existing data.
    Returns the SQLAlchemy engine.
    """
    # For SQLite, ensure the parent directory exists
    if database_url.startswith("sqlite:///"):
        import os
        db_path = database_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine
```

### 2.3 — Write `core/queues.py`

```python
"""
core/queues.py

Shared async message queues — the "message bus" of this multi-agent system.

Why asyncio.Queue instead of Kafka:
  - Zero infrastructure: no broker, no Docker service, no port config
  - Same conceptual model: producers put(), consumers get()
  - Built into Python stdlib — nothing to install
  - Trivially swappable for Kafka or Redis Streams later

These queues are module-level singletons. All agents import the same
queue instances from here, so they truly share the same channels.

Queue contents (all dicts / JSON-serializable):
  raw_market_queue  → {symbol, price, volume, timestamp}
  raw_news_queue    → {headline, url, body, published_at, source}
  insights_queue    → {user_query, insight_text, sources, sentiment_summary, timestamp}
"""

import asyncio

# One queue per data channel — module-level so all agents share the same object
raw_market_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
raw_news_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
insights_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
```

### 2.4 — Verify core modules load cleanly

```bash
python -c "
from core.settings import settings
from core.models import init_db
from core.queues import raw_market_queue, raw_news_queue, insights_queue

engine = init_db(settings.DATABASE_URL)
print('settings OK:', settings.GEMINI_MODEL)
print('db OK:', settings.DATABASE_URL)
print('queues OK: 3 queues created')
"
```

### 2.5 — Commit

```bash
git add core/
git commit -m "feat: add core settings, SQLite models, async queues"
git push
```

**✅ Acceptance Criteria:**
- The verify command above prints 3 OK lines with no errors
- `data/finance.db` file exists (created by `init_db`)
- `data/chroma_db/` directory exists

---

## Step 3 — Agent 1: Ingest Agent

**Context for Cursor:** The ingest agent is the data entry point. It runs in a loop, fetches stock
prices (yfinance — free, no API key) and news (feedparser + RSS — free, no API key), and puts
messages onto the two input queues. It also saves raw data to SQLite for the UI to display.
It knows nothing about analysis or Gemini — pure data collection.

### 3.1 — Write `agents/ingest_agent.py`

```python
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
from loguru import logger
import yfinance as yf
import feedparser
from sqlalchemy.orm import Session

from core.settings import settings
from core.queues import raw_market_queue, raw_news_queue
from core.models import init_db, MarketSnapshot, NewsArticle


async def fetch_market_data(engine) -> list[dict]:
    """
    Fetch current stock prices using yfinance.
    yfinance is free — it scrapes Yahoo Finance's public endpoints.
    No API key needed. No rate limit for reasonable personal use.
    """
    results = []
    # Run yfinance (sync library) in a thread so we don't block the async loop
    loop = asyncio.get_event_loop()

    for symbol in settings.YFINANCE_SYMBOLS:
        try:
            ticker = await loop.run_in_executor(None, lambda s=symbol: yf.Ticker(s))
            info = ticker.fast_info
            price = info.last_price

            if price is None:
                logger.warning(f"No price data for {symbol} (market may be closed)")
                continue

            snap = {
                "symbol": symbol,
                "price": round(float(price), 2),
                "volume": round(float(info.three_month_average_volume or 0), 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            results.append(snap)

            # Persist to SQLite
            with Session(engine) as session:
                session.add(MarketSnapshot(
                    symbol=snap["symbol"],
                    price=snap["price"],
                    volume=snap["volume"],
                    captured_at=datetime.now(timezone.utc),
                ))
                session.commit()

            logger.info(f"[Ingest] {symbol}: ${price:.2f}")

        except Exception as e:
            logger.error(f"[Ingest] Error fetching {symbol}: {e}")

    return results


async def fetch_news(engine) -> list[dict]:
    """
    Fetch news from RSS feeds using feedparser.
    feedparser is free and does not require any API key.
    RSS feeds are public — no login, no billing.
    """
    articles = []
    loop = asyncio.get_event_loop()

    for feed_url in settings.NEWS_RSS_FEEDS:
        try:
            # feedparser is sync; run in executor
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            for entry in feed.entries[:15]:  # cap at 15 per feed
                article = {
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "body": entry.get("summary", ""),
                    "published_at": entry.get("published", datetime.now(timezone.utc).isoformat()),
                    "source": feed.feed.get("title", feed_url),
                }
                articles.append(article)

                with Session(engine) as session:
                    session.add(NewsArticle(
                        headline=article["headline"],
                        url=article["url"],
                        body=article["body"],
                        source=article["source"],
                        ingested_at=datetime.now(timezone.utc),
                    ))
                    session.commit()

            logger.info(f"[Ingest] {len(feed.entries[:15])} articles from {feed_url[:50]}")

        except Exception as e:
            logger.error(f"[Ingest] Error fetching feed {feed_url}: {e}")

    return articles


async def run() -> None:
    """
    Main ingest loop. Fetches data every INGEST_INTERVAL_SECONDS, puts on queues.
    Runs forever as an asyncio task.
    """
    logger.info("[Ingest Agent] Starting...")
    engine = init_db(settings.DATABASE_URL)

    while True:
        logger.info("[Ingest Agent] Starting fetch cycle...")

        snapshots = await fetch_market_data(engine)
        for snap in snapshots:
            await raw_market_queue.put(snap)
        logger.info(f"[Ingest Agent] Put {len(snapshots)} market snapshots on queue")

        articles = await fetch_news(engine)
        for article in articles:
            await raw_news_queue.put(article)
        logger.info(f"[Ingest Agent] Put {len(articles)} news articles on queue")

        logger.info(f"[Ingest Agent] Cycle done. Sleeping {settings.INGEST_INTERVAL_SECONDS}s...")
        await asyncio.sleep(settings.INGEST_INTERVAL_SECONDS)
```

### 3.2 — Quick standalone test

```bash
# Temporarily test ingest in isolation (Ctrl+C to stop after one cycle)
python -c "
import asyncio
from agents.ingest_agent import fetch_market_data, fetch_news
from core.models import init_db
from core.settings import settings

engine = init_db(settings.DATABASE_URL)

async def test():
    snaps = await fetch_market_data(engine)
    print('Market snapshots:', len(snaps))
    for s in snaps[:3]:
        print(' ', s)
    articles = await fetch_news(engine)
    print('News articles:', len(articles))
    for a in articles[:2]:
        print(' ', a['headline'][:80])

asyncio.run(test())
"
```

### 3.3 — Commit

```bash
git add agents/ingest_agent.py
git commit -m "feat: ingest agent (yfinance + RSS, async, no paid APIs)"
git push
```

**✅ Acceptance Criteria:**
- Test script prints at least 1 market snapshot with a real price
- Test script prints at least 1 news headline
- `data/finance.db` has rows in `market_snapshots` and `news_articles`

---

## Step 4 — Agent 2: Analysis Agent (LLM Wiki Knowledge Base)

**Context for Cursor:** This is the most important agent. It replaces the old RAG pattern
(ChromaDB vector search) with an **LLM Wiki Knowledge Base** — a pattern by Andrej Karpathy
(April 2026) where the LLM *compiles* incoming data into a persistent, interlinked markdown wiki
instead of re-deriving knowledge from raw chunks on every query.

### Why LLM Wiki instead of RAG?

| | Traditional RAG (old) | LLM Wiki Knowledge Base (new) |
|---|---|---|
| **How it works** | Embed docs → search vectors → retrieve chunks → LLM answers | LLM reads new data and *writes/updates* structured markdown wiki pages |
| **Knowledge accumulation** | None — same raw chunks re-searched every query | Compounding — each ingest enriches the wiki permanently |
| **Cross-document synthesis** | LLM re-discovers links every time | Links, contradictions, entity summaries are pre-computed and stored |
| **Infrastructure** | ChromaDB, sentence-transformers (~80MB model) | Plain markdown files on disk — zero dependencies |
| **Interview story** | "I used RAG" (common) | "I implemented Karpathy's LLM Wiki pattern for persistent financial intelligence" (rare, impressive) |
| **Cost** | Free (local) | Free (local markdown files) |
| **Complexity** | Embedding pipeline + vector DB | File I/O + LLM writes markdown |

**The key insight:** In RAG, the LLM is a reader that re-derives knowledge from scratch every
query. In the LLM Wiki, the LLM is a *writer* that incrementally compiles knowledge into a
structured wiki. Each new article or price event updates the wiki — entity pages (per stock),
concept pages (market trends, sector analysis), a synthesis overview, and a change log.
When Gemini answers a query, it reads the pre-compiled wiki pages rather than raw chunks.

**This is 100% possible with Cursor IDE alone — no paid APIs, no extra infra.** The wiki
is just a folder of markdown files (`data/wiki/`). Gemini 1.5 Flash writes them. You read them.

**Three wiki operations this agent performs:**

1. **Ingest**: When new articles/prices arrive → Gemini reads them and updates relevant wiki pages
2. **Query**: When generating an insight → Gemini reads the wiki's `index.md` + relevant pages
3. **Lint** (periodic): Gemini health-checks the wiki — finds contradictions, orphan pages, stale data

**Rate limit handling is critical:** Gemini free tier allows ~15 requests/minute.
The `tenacity` retry decorator handles this automatically with exponential backoff.
Never remove the retry decorator. Never suggest upgrading to paid.

### 4.1 — Update folder structure for the wiki

```bash
# Add wiki directory alongside chroma_db (chroma_db is now unused — can be removed)
mkdir -p data/wiki
touch data/wiki/index.md data/wiki/log.md data/wiki/overview.md
# Remove chromadb from requirements (no longer needed)
```

Update `requirements.txt` — remove the ChromaDB and sentence-transformers lines:

```text
# REMOVED in v3 (LLM Wiki replaces RAG):
# chromadb==0.5.3
# sentence-transformers==3.0.1
```

Update `core/settings.py` — replace `CHROMA_PERSIST_DIR` with `WIKI_DIR`:

```python
# Replace this line:
# CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
# With:
WIKI_DIR: str = os.getenv("WIKI_DIR", "./data/wiki")
```

Update `.env.example`:

```dotenv
# Replace:
# CHROMA_PERSIST_DIR=./data/chroma_db
# With:
WIKI_DIR=./data/wiki
WIKI_INGEST_EVERY_N_ARTICLES=5    # how many articles to batch before wiki update
WIKI_LINT_INTERVAL_HOURS=6        # how often to run the wiki health-check
```

### 4.2 — Write `core/wiki.py`

```python
"""
core/wiki.py

LLM Wiki Knowledge Base — Karpathy Pattern (April 2026)

This module manages a persistent, compounding markdown wiki under data/wiki/.
Instead of re-embedding raw text (RAG), Gemini incrementally writes and maintains
structured wiki pages. Knowledge is compiled once, updated on every ingest, and
read at query time — eliminating redundant re-derivation.

Wiki layout:
  data/wiki/
    index.md         — catalog of all pages (LLM reads this first on any query)
    log.md           — append-only operation log (ingest, query, lint events)
    overview.md      — rolling synthesis: overall market picture, key themes
    stocks/
      AAPL.md        — entity page: price history, news summary, sentiment trend
      MSFT.md
      ...
    concepts/
      tech_sector.md — concept page: cross-stock theme synthesis
      market_risk.md
      ...
    insights/
      YYYY-MM-DD_HH-MM.md  — filed insights (good answers become wiki pages)

Operations:
  ingest_to_wiki(articles, prices) — LLM updates wiki from new data
  query_wiki(question)             — LLM reads index + relevant pages, answers
  lint_wiki()                      — LLM health-checks wiki for contradictions/orphans
"""

import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

from core.settings import settings


# ── Wiki directory helpers ────────────────────────────────────────────────────

def _wiki_path(*parts: str) -> Path:
    """Return a Path inside the wiki directory, creating parent dirs as needed."""
    p = Path(settings.WIKI_DIR).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_wiki_file(rel_path: str) -> str:
    """Read a wiki file. Returns empty string if the file doesn't exist yet."""
    p = _wiki_path(rel_path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _write_wiki_file(rel_path: str, content: str) -> None:
    """Write (overwrite) a wiki file."""
    p = _wiki_path(rel_path)
    p.write_text(content, encoding="utf-8")
    logger.debug(f"[Wiki] Wrote {rel_path} ({len(content)} chars)")


def _append_log(entry: str) -> None:
    """Append a timestamped entry to log.md (append-only operation journal)."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log_path = _wiki_path("log.md")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n## [{timestamp}] {entry}\n")


def list_wiki_pages() -> list[str]:
    """Return all .md file paths relative to wiki root."""
    root = Path(settings.WIKI_DIR)
    if not root.exists():
        return []
    return [str(p.relative_to(root)) for p in root.rglob("*.md")]


# ── Gemini call with retry ────────────────────────────────────────────────────
# (Imported by analysis_agent — also used here for wiki maintenance calls)

import google.generativeai as genai
genai.configure(api_key=settings.GEMINI_API_KEY)
_gemini = genai.GenerativeModel(settings.GEMINI_MODEL)


@retry(
    stop=stop_after_attempt(settings.GEMINI_RETRY_MAX),
    wait=wait_exponential(multiplier=settings.GEMINI_RETRY_BACKOFF_BASE, min=2, max=60),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _call_gemini_sync(prompt: str) -> str:
    return _gemini.generate_content(prompt).text


async def call_gemini(prompt: str) -> str:
    """Async wrapper for the sync Gemini call."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_gemini_sync, prompt)


# ── Operation 1: Ingest → Wiki update ────────────────────────────────────────

async def ingest_to_wiki(articles: list[dict], prices: list[dict]) -> None:
    """
    Core wiki operation: LLM reads new articles/prices and updates wiki pages.

    For each symbol mentioned in the batch, Gemini updates that symbol's entity page.
    It also updates the overview.md synthesis and the index.md catalog.
    A log entry records what happened.

    This is the 'compile once' step — knowledge is structured here so that
    query_wiki() can read pre-synthesized pages instead of raw chunks.
    """
    if not articles and not prices:
        return

    logger.info(f"[Wiki] Ingesting {len(articles)} articles, {len(prices)} prices...")

    # ── Step 1: Update per-symbol entity pages ────────────────────────────────
    # Group articles by mentioned symbols
    symbols = [p["symbol"] for p in prices]
    articles_text = "\n".join(
        f"- [{a.get('source','')}] {a['headline']}: {a.get('body','')[:200]}"
        for a in articles[:20]
    )
    prices_text = "\n".join(
        f"- {p['symbol']}: ${p['price']:.2f} (vol: {p.get('volume','?')})"
        for p in prices
    )

    for symbol in symbols[:5]:  # cap at 5 per cycle to respect rate limits
        existing_page = _read_wiki_file(f"stocks/{symbol}.md")
        prompt = f"""You are maintaining a financial knowledge base wiki.
Update the wiki page for stock symbol {symbol}.

EXISTING PAGE CONTENT (may be empty if this is the first time):
{existing_page or '(new page — create it)'}

NEW DATA TO INTEGRATE:
Current prices:
{prices_text}

Recent news articles:
{articles_text}

INSTRUCTIONS:
- Write a complete updated markdown page for {symbol}
- Include sections: ## Summary, ## Recent Price Action, ## News & Sentiment, ## Key Risks, ## Cross-References
- In Cross-References, link to related concept pages using [[wikilink]] syntax
- Keep the page under 400 words — be concise and factual
- Do NOT invent data. Only use what's in NEW DATA above.
- If existing page has info not contradicted by new data, preserve it.
- End with a `> Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}` line

WRITE THE COMPLETE PAGE NOW (markdown only, no preamble):"""

        page_content = await call_gemini(prompt)
        _write_wiki_file(f"stocks/{symbol}.md", page_content)
        logger.info(f"[Wiki] Updated stocks/{symbol}.md")

    # ── Step 2: Update overview synthesis ────────────────────────────────────
    existing_overview = _read_wiki_file("overview.md")
    prompt = f"""You are maintaining a financial knowledge base wiki.
Update the market overview synthesis page.

EXISTING OVERVIEW:
{existing_overview or '(new — create it)'}

NEW DATA THIS CYCLE:
Prices: {prices_text}
Articles: {articles_text}

Write a concise updated overview (under 300 words) covering:
## Market Overview
## Key Themes This Cycle
## Stocks to Watch
## Risk Signals

Be factual, cite specific prices/headlines. Use [[wikilink]] to reference stock pages.
End with `> Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`

WRITE THE OVERVIEW NOW (markdown only):"""

    overview = await call_gemini(prompt)
    _write_wiki_file("overview.md", overview)

    # ── Step 3: Rebuild index.md catalog ─────────────────────────────────────
    all_pages = list_wiki_pages()
    index_lines = ["# Wiki Index\n", f"> {len(all_pages)} pages | "
                   f"Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"]
    index_lines.append("## Stock Pages\n")
    for page in sorted(p for p in all_pages if p.startswith("stocks/")):
        symbol = page.replace("stocks/", "").replace(".md", "")
        index_lines.append(f"- [[{symbol}]] → `{page}`\n")
    index_lines.append("\n## Concept Pages\n")
    for page in sorted(p for p in all_pages if p.startswith("concepts/")):
        index_lines.append(f"- `{page}`\n")
    index_lines.append("\n## Insights Archive\n")
    for page in sorted(p for p in all_pages if p.startswith("insights/")):
        index_lines.append(f"- `{page}`\n")
    _write_wiki_file("index.md", "".join(index_lines))

    # ── Step 4: Log the ingest event ─────────────────────────────────────────
    _append_log(
        f"ingest | {len(articles)} articles, {len(prices)} prices | "
        f"updated: {', '.join(symbols[:5])}"
    )
    logger.info("[Wiki] Ingest complete.")


# ── Operation 2: Query the wiki ───────────────────────────────────────────────

async def query_wiki(question: str) -> tuple[str, list[str]]:
    """
    Answer a question using the wiki.

    The LLM reads index.md first (the catalog), identifies relevant pages,
    reads those pages, then synthesizes an answer. This mirrors how a human
    would use a good wiki — check the index, read the relevant entries, answer.

    Returns (answer_text, list_of_pages_consulted).

    Good answers are automatically filed back into the wiki as insights/ pages,
    so your explorations compound the knowledge base just like ingested data does.
    """
    index_content = _read_wiki_file("index.md")
    overview_content = _read_wiki_file("overview.md")

    if not index_content:
        return (
            "The wiki is still being built — no pages available yet. "
            "Wait for the first ingest cycle to complete.",
            [],
        )

    # ── Step 1: LLM reads index to find relevant pages ────────────────────────
    routing_prompt = f"""You are a financial wiki assistant.
A user has asked: "{question}"

Here is the wiki index (catalog of all pages):
{index_content}

List the 3-5 most relevant page paths to read for answering this question.
Reply with ONLY a newline-separated list of file paths (e.g. stocks/AAPL.md).
No other text."""

    routing_response = await call_gemini(routing_prompt)
    relevant_paths = [
        line.strip() for line in routing_response.strip().splitlines()
        if line.strip() and line.strip().endswith(".md")
    ]

    # ── Step 2: Read those pages ─────────────────────────────────────────────
    pages_context = ""
    consulted = []
    for path in relevant_paths[:5]:
        content = _read_wiki_file(path)
        if content:
            pages_context += f"\n\n### From `{path}`:\n{content}"
            consulted.append(path)

    # Always include overview for context
    if overview_content and "overview.md" not in consulted:
        pages_context = f"\n\n### From `overview.md`:\n{overview_content}" + pages_context
        consulted.insert(0, "overview.md")

    # ── Step 3: Generate the answer from pre-compiled wiki content ────────────
    answer_prompt = f"""You are a concise, data-driven personal finance AI assistant.
Answer the question below using ONLY the wiki content provided.
Do not invent data. Be specific — cite prices, dates, and headlines from the wiki.

QUESTION: {question}

WIKI CONTENT:
{pages_context}

Instructions:
- Answer in 3–4 paragraphs maximum
- Reference specific data points from the wiki (prices, sentiment, trends)
- Be balanced — do not over-promise returns
- End with a one-sentence risk disclaimer
- This is for educational purposes only

YOUR RESPONSE:"""

    answer = await call_gemini(answer_prompt)

    # ── Step 4: File the insight back into the wiki ───────────────────────────
    # Good answers compound the knowledge base — they don't disappear into chat
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    insight_page = f"# Insight: {question[:80]}\n\n{answer}\n\n" \
                   f"---\n*Sources consulted: {', '.join(consulted)}*\n" \
                   f"*Generated: {timestamp} UTC*\n"
    _write_wiki_file(f"insights/{timestamp}.md", insight_page)
    _append_log(f"query | \"{question[:60]}...\" | consulted: {', '.join(consulted)}")

    return answer, consulted


# ── Operation 3: Lint the wiki ────────────────────────────────────────────────

async def lint_wiki() -> str:
    """
    Periodic wiki health-check. Gemini reviews the wiki for:
    - Contradictions between pages (e.g. conflicting price narratives)
    - Stale claims superseded by newer data
    - Orphan pages with no inbound links
    - Important entities without their own page
    - Missing cross-references

    Returns a summary of the lint report, also filed as a wiki page.
    This keeps the wiki healthy as it grows and is a great story for interviews:
    'The system self-audits its own knowledge base periodically.'
    """
    index_content = _read_wiki_file("index.md")
    log_tail = _read_wiki_file("log.md")[-2000:]  # last ~2000 chars of log

    prompt = f"""You are auditing a financial knowledge base wiki.

WIKI INDEX:
{index_content}

RECENT LOG (last operations):
{log_tail}

Perform a health check and report:
1. **Potential contradictions** — pages that may conflict with each other
2. **Stale pages** — pages likely to have outdated info (older than 1 day)
3. **Orphan pages** — pages with no inbound links from other pages
4. **Missing pages** — important entities/concepts mentioned but lacking their own page
5. **Suggested next ingests** — what data would most improve the wiki right now?

Be specific. Reference page names. Keep the report under 300 words.

LINT REPORT:"""

    report = await call_gemini(prompt)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    _write_wiki_file(f"insights/lint_{timestamp}.md", f"# Wiki Lint Report\n\n{report}\n")
    _append_log(f"lint | health-check complete")
    logger.info("[Wiki] Lint complete.")
    return report
```

### 4.3 — Write `agents/analysis_agent.py` (updated for LLM Wiki)

```python
"""
agents/analysis_agent.py

Agent 2: Analysis (Sentiment + LLM Wiki Knowledge Base + Gemini LLM)

Responsibility: consume raw data from queues, maintain the LLM Wiki knowledge
base, generate insights by querying the wiki, put results on insights_queue.

This agent replaces the old RAG (ChromaDB) pattern with the LLM Wiki pattern
(Karpathy, April 2026). Instead of embedding chunks and searching vectors at
query time, Gemini incrementally compiles incoming data into a persistent,
interlinked markdown wiki under data/wiki/. Queries read pre-compiled pages.

Tools used:
  TextBlob      — sentiment analysis, free, offline
  core/wiki.py  — LLM Wiki knowledge base (plain markdown files, Gemini writes them)
  Gemini 1.5 Flash — FREE TIER (15 req/min, 1M tokens/day)

Queues consumed:  raw_market_queue, raw_news_queue
Queues produced:  insights_queue
"""

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from loguru import logger
from textblob import TextBlob

from core.settings import settings
from core.queues import raw_market_queue, raw_news_queue, insights_queue
from core.wiki import ingest_to_wiki, query_wiki, lint_wiki


# ── Sentiment ─────────────────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> tuple[str, float]:
    """
    TextBlob sentiment: free, offline, no API.
    Returns (label, score) where score is -1.0 to +1.0.
    """
    score = TextBlob(text).sentiment.polarity
    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"
    return label, round(score, 4)


# ── Main agent loop ───────────────────────────────────────────────────────────

async def run() -> None:
    """
    Main analysis loop.

    Every ANALYSIS_INTERVAL_SECONDS:
      1. Drain queues and run sentiment on news
      2. Batch-ingest new data into the LLM Wiki (Gemini updates wiki pages)
      3. Query the wiki with a market outlook question
      4. Put the insight on insights_queue for storage agent

    Every WIKI_LINT_INTERVAL_HOURS:
      5. Run wiki lint (Gemini health-checks the knowledge base)
    """
    logger.info("[Analysis Agent] Starting (LLM Wiki mode)...")

    market_buffer: deque = deque(maxlen=50)
    news_buffer: deque = deque(maxlen=100)
    sentiment_buffer: deque = deque(maxlen=100)

    last_analysis: float = 0.0
    last_lint: float = 0.0
    lint_interval_seconds = float(
        getattr(settings, "WIKI_LINT_INTERVAL_HOURS", 6)
    ) * 3600
    ingest_batch_size = int(getattr(settings, "WIKI_INGEST_EVERY_N_ARTICLES", 5))

    while True:
        # ── Drain market queue ────────────────────────────────────────────────
        while not raw_market_queue.empty():
            item = await raw_market_queue.get()
            market_buffer.append(item)

        # ── Drain news queue + sentiment ──────────────────────────────────────
        new_articles: list[dict] = []
        while not raw_news_queue.empty():
            article = await raw_news_queue.get()
            news_buffer.append(article)
            label, score = analyze_sentiment(
                article["headline"] + " " + article.get("body", "")
            )
            enriched = {**article, "sentiment_label": label, "sentiment_score": score}
            sentiment_buffer.append(enriched)
            new_articles.append(enriched)

        # ── Ingest batch into wiki when we have enough new articles ───────────
        if len(new_articles) >= ingest_batch_size:
            logger.info(
                f"[Analysis Agent] Triggering wiki ingest "
                f"({len(new_articles)} articles, {len(market_buffer)} prices)..."
            )
            await ingest_to_wiki(new_articles, list(market_buffer))

        # ── Check if it's time for a Gemini insight query ─────────────────────
        now = time.time()
        if now - last_analysis < settings.ANALYSIS_INTERVAL_SECONDS:
            await asyncio.sleep(10)
            continue

        if not market_buffer and not news_buffer:
            logger.info("[Analysis Agent] No data yet, waiting for ingest agent...")
            await asyncio.sleep(30)
            continue

        # Ensure wiki is up to date before querying
        if new_articles:
            await ingest_to_wiki(new_articles, list(market_buffer))

        logger.info("[Analysis Agent] Querying wiki for market insight...")

        question = (
            "Based on the current stock prices and recent financial news, "
            "what is the overall market outlook and are there any notable "
            "opportunities or risks for a retail investor to be aware of?"
        )

        insight_text, pages_consulted = await query_wiki(question)

        # Build sentiment summary for storage
        pos = sum(1 for s in sentiment_buffer if s.get("sentiment_label") == "positive")
        neg = sum(1 for s in sentiment_buffer if s.get("sentiment_label") == "negative")
        neu = sum(1 for s in sentiment_buffer if s.get("sentiment_label") == "neutral")
        sentiment_summary = f"{pos} positive, {neg} negative, {neu} neutral headlines"

        insight_msg = {
            "user_query": question,
            "insight_text": insight_text,
            "sentiment_summary": sentiment_summary,
            "sources": json.dumps(pages_consulted),   # wiki pages consulted
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await insights_queue.put(insight_msg)
        logger.info(
            f"[Analysis Agent] Insight generated from {len(pages_consulted)} wiki pages"
        )
        last_analysis = now

        # ── Periodic wiki lint ────────────────────────────────────────────────
        if now - last_lint > lint_interval_seconds:
            logger.info("[Analysis Agent] Running wiki lint...")
            await lint_wiki()
            last_lint = now

        await asyncio.sleep(10)
```

### 4.4 — Test Gemini key and wiki ingest

```bash
# Test Gemini works
python -c "
import google.generativeai as genai
from core.settings import settings
genai.configure(api_key=settings.GEMINI_API_KEY)
m = genai.GenerativeModel('gemini-1.5-flash')
r = m.generate_content('Say: LLM Wiki knowledge base is working')
print(r.text)
"

# Test wiki ingest with fake data
python -c "
import asyncio
from core.wiki import ingest_to_wiki, query_wiki
from core.settings import settings
import os; os.makedirs(settings.WIKI_DIR, exist_ok=True)

fake_articles = [
    {'headline': 'Apple reports record Q2 earnings', 'body': 'Revenue up 15% YoY', 'source': 'Reuters', 'url': 'http://example.com/1'},
    {'headline': 'Microsoft Azure growth slows', 'body': 'Cloud revenue missed estimates', 'source': 'Bloomberg', 'url': 'http://example.com/2'},
]
fake_prices = [
    {'symbol': 'AAPL', 'price': 189.5, 'volume': 52000000},
    {'symbol': 'MSFT', 'price': 415.2, 'volume': 21000000},
]

async def test():
    await ingest_to_wiki(fake_articles, fake_prices)
    print('Wiki pages created:')
    import os
    for root, dirs, files in os.walk(settings.WIKI_DIR):
        for f in files:
            path = os.path.join(root, f)
            print(' ', path, '—', len(open(path).read()), 'chars')
    print()
    answer, pages = await query_wiki('What is the outlook for Apple stock?')
    print('Query answer preview:')
    print(answer[:300])
    print('Pages consulted:', pages)

asyncio.run(test())
"
```

### 4.5 — Commit

```bash
git add agents/analysis_agent.py core/wiki.py data/wiki/
git commit -m "feat: replace RAG with LLM Wiki knowledge base (Karpathy pattern)"
git push
```

**✅ Acceptance Criteria:**
- Gemini test prints a response
- Wiki test creates files under `data/wiki/stocks/`, `data/wiki/index.md`, `data/wiki/overview.md`
- Query test returns an answer and lists page names as sources
- `python -c "from agents.analysis_agent import analyze_sentiment; print(analyze_sentiment('stocks are crashing badly'))"` prints `('negative', ...)`

---

        try:
            insight_text = await call_gemini(prompt)
            logger.info(f"[Analysis Agent] Insight generated ({len(insight_text)} chars)")
        except Exception as e:
            logger.error(f"[Analysis Agent] Gemini failed after retries: {e}")
            last_analysis = now
            continue



## Step 5 — Agent 3: Storage Agent

**Context for Cursor:** The storage agent is the simplest. It reads insights from `insights_queue`
and saves them to SQLite. It also exposes simple functions that the Streamlit UI calls directly
(no HTTP layer needed — Streamlit and the storage agent run in the same Python process via `main.py`).

### 5.1 — Write `agents/storage_agent.py`

```python
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
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.settings import settings
from core.queues import insights_queue
from core.models import init_db, Insight


# Module-level engine — initialized once, shared by async loop and UI query functions
_engine = None


def get_engine():
    """Return the SQLAlchemy engine, initializing it if needed."""
    global _engine
    if _engine is None:
        _engine = init_db(settings.DATABASE_URL)
    return _engine


# ── Async consumer loop ───────────────────────────────────────────────────────

async def run() -> None:
    """
    Listens on insights_queue forever.
    Every time the analysis agent produces an insight, this saves it to SQLite.
    """
    logger.info("[Storage Agent] Starting...")
    engine = get_engine()

    while True:
        try:
            # Wait for next insight (blocks until one arrives)
            insight = await asyncio.wait_for(insights_queue.get(), timeout=5.0)

            with Session(engine) as session:
                session.add(Insight(
                    user_query=insight.get("user_query", ""),
                    insight_text=insight.get("insight_text", ""),
                    sentiment_summary=insight.get("sentiment_summary", ""),
                    sources=insight.get("sources", "[]"),
                    generated_at=datetime.now(timezone.utc),
                    model_used=settings.GEMINI_MODEL,
                ))
                session.commit()

            logger.info("[Storage Agent] Insight saved to SQLite")

        except asyncio.TimeoutError:
            # No insight arrived in 5s — that's fine, just loop
            continue
        except Exception as e:
            logger.error(f"[Storage Agent] Error saving insight: {e}")


# ── UI query functions (called directly by Streamlit) ─────────────────────────
# These are regular sync functions — Streamlit is not async.

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

    results = []
    for row in rows:
        try:
            sources = json.loads(row.sources) if row.sources else []
        except Exception:
            sources = []
        results.append({
            "id": row.id,
            "user_query": row.user_query or "",
            "insight_text": row.insight_text,
            "sentiment_summary": row.sentiment_summary or "",
            "sources": sources,
            "generated_at": str(row.generated_at),
            "model_used": row.model_used or "gemini-1.5-flash",
        })
    return results


def get_latest_prices() -> list[dict]:
    """Return the most recent price for each tracked symbol."""
    engine = get_engine()
    with Session(engine) as session:
        rows = session.execute(text("""
            SELECT symbol, price, volume, captured_at
            FROM market_snapshots
            WHERE (symbol, captured_at) IN (
                SELECT symbol, MAX(captured_at)
                FROM market_snapshots
                GROUP BY symbol
            )
            ORDER BY symbol
        """)).fetchall()
    return [
        {"symbol": r.symbol, "price": r.price,
         "volume": r.volume, "captured_at": str(r.captured_at)}
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
        {"headline": r.headline, "source": r.source,
         "url": r.url, "ingested_at": str(r.ingested_at)}
        for r in rows
    ]
```

### 5.2 — Commit

```bash
git add agents/storage_agent.py
git commit -m "feat: storage agent (SQLite persistence + UI query functions)"
git push
```

---

## Step 6 — Main Entry Point

**Context for Cursor:** `main.py` is the single entry point that starts all 3 agents as concurrent
asyncio tasks. This replaces the old `orchestrator.py`. When Docker runs the container, it runs
`python main.py`. The Streamlit UI runs as a separate process (separate Docker service) but imports
the storage agent's query functions directly.

### 6.1 — Write `main.py`

```python
"""
main.py

Entry point for the multi-agent finance advisor.

Starts all 3 agents as concurrent asyncio tasks:
  - ingest_agent:   fetches data every INGEST_INTERVAL_SECONDS
  - analysis_agent: processes data every ANALYSIS_INTERVAL_SECONDS
  - storage_agent:  saves insights to SQLite as they arrive

All agents share the same async queues (defined in core/queues.py).
They run concurrently in a single process — no inter-process communication needed.

To run locally:  python main.py
In Docker:       CMD ["python", "main.py"]  (see Dockerfile)
"""

import asyncio
from loguru import logger
from core.settings import settings

# Configure loguru log level from settings
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    level=settings.LOG_LEVEL,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
)


async def main():
    """Launch all agents as concurrent async tasks."""
    # Import here so logger is configured before agents import it
    from agents.ingest_agent import run as ingest_run
    from agents.analysis_agent import run as analysis_run
    from agents.storage_agent import run as storage_run

    logger.info("=" * 60)
    logger.info("  Multi-Agent Finance Advisor starting")
    logger.info(f"  Ingest interval:   {settings.INGEST_INTERVAL_SECONDS}s")
    logger.info(f"  Analysis interval: {settings.ANALYSIS_INTERVAL_SECONDS}s")
    logger.info(f"  Gemini model:      {settings.GEMINI_MODEL} (free tier)")
    logger.info("=" * 60)

    # Create all 3 agent tasks — they run concurrently
    tasks = [
        asyncio.create_task(ingest_run(), name="ingest_agent"),
        asyncio.create_task(analysis_run(), name="analysis_agent"),
        asyncio.create_task(storage_run(), name="storage_agent"),
    ]

    # Run until one task crashes, then log which one and why
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    for task in done:
        if task.exception():
            logger.error(f"Task '{task.get_name()}' crashed: {task.exception()}")

    # Cancel remaining tasks cleanly
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.error("All agents stopped. Check logs above for the cause.")


if __name__ == "__main__":
    asyncio.run(main())
```

### 6.2 — Test full pipeline locally (no Docker yet)

```bash
# With .env filled in and venv active:
# Set a short interval for testing (override in terminal)
INGEST_INTERVAL_SECONDS=30 ANALYSIS_INTERVAL_SECONDS=60 python main.py

# You should see all 3 agents start, then after ~30s see ingest data,
# then after ~60s see a Gemini insight generated.
# Ctrl+C to stop.
```

### 6.3 — Commit

```bash
git add main.py
git commit -m "feat: main.py entry point, all 3 agents as asyncio tasks"
git push
```

**✅ Acceptance Criteria:**
- Running `main.py` shows all 3 agents starting in logs
- After 1 ingest cycle, `data/finance.db` has rows in `market_snapshots`
- After 1 analysis cycle, `data/finance.db` has a row in `insights`

---

## Step 7 — Streamlit UI

**Context for Cursor:** The UI is a Streamlit app. It imports storage agent query functions
directly (same codebase, no HTTP needed). It auto-refreshes to show live data.
Streamlit is free and open-source.

### 7.1 — Write `ui/app.py`

```python
"""
ui/app.py

Streamlit dashboard for the Multi-Agent Finance Advisor.

Data source: imports query functions from agents/storage_agent.py directly.
No HTTP API needed — Streamlit runs in the same codebase.

To run locally:  streamlit run ui/app.py
In Docker:       separate service in docker-compose.yml (port 8501)
"""

import sys
import os
import time
import streamlit as st

# Allow imports from project root when running as a Docker container
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.storage_agent import get_recent_insights, get_latest_prices, get_recent_headlines

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Finance Advisor",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Multi-Agent AI Finance Advisor")
st.caption(
    "Powered by Google Gemini 1.5 Flash (free tier) · "
    "Data: Yahoo Finance + RSS feeds · "
    "All open-source, zero cost"
)

# ── Market Prices ─────────────────────────────────────────────────────────────
st.header("Current Market Prices")
prices = get_latest_prices()

if prices:
    cols = st.columns(min(len(prices), 5))
    for col, item in zip(cols, prices):
        col.metric(label=item["symbol"], value=f"${item['price']:,.2f}")
    st.caption(f"Last updated: {prices[0]['captured_at']}")
else:
    st.info("⏳ Waiting for first data fetch (up to 5 minutes)...")

# ── Recent Headlines ──────────────────────────────────────────────────────────
st.header("Recent News Headlines")
headlines = get_recent_headlines(limit=10)

if headlines:
    for h in headlines:
        url = h.get("url", "")
        headline_text = h["headline"]
        if url:
            st.markdown(f"- [{headline_text[:120]}]({url}) — *{h['source']}*")
        else:
            st.markdown(f"- {headline_text[:120]} — *{h['source']}*")
else:
    st.info("⏳ No headlines yet...")

# ── AI Insights ───────────────────────────────────────────────────────────────
st.header("AI-Generated Insights")
st.caption("Generated by Gemini 1.5 Flash · Refreshes every 10 minutes")

insights = get_recent_insights(limit=5)

if insights:
    for insight in insights:
        with st.expander(
            f"🤖 {insight['generated_at'][:16]}  —  {insight['sentiment_summary']}",
            expanded=(insight == insights[0]),  # expand the most recent one
        ):
            st.write(insight["insight_text"])

            if insight["sources"]:
                valid_sources = [s for s in insight["sources"] if s]
                if valid_sources:
                    st.caption("Sources: " + " · ".join(valid_sources[:3]))

            st.caption(f"Model: {insight['model_used']}")
else:
    st.info(
        "⏳ No insights yet. The analysis agent runs every 10 minutes. "
        "Check back shortly or reduce ANALYSIS_INTERVAL_SECONDS in .env for faster testing."
    )

# ── Footer + refresh ──────────────────────────────────────────────────────────
st.divider()
col1, col2 = st.columns([3, 1])
col1.caption("This is a personal project for educational purposes. Not financial advice.")
if col2.button("🔄 Refresh"):
    st.rerun()
```

### 7.2 — Test UI locally

```bash
# In a separate terminal while main.py is running:
streamlit run ui/app.py
# Open: http://localhost:8501
```

### 7.3 — Commit

```bash
git add ui/app.py
git commit -m "feat: Streamlit dashboard, reads from SQLite via storage agent"
git push
```

---

## Step 8 — Docker Setup

**Context for Cursor:** Containerize everything. Two Docker services:
1. `app` — runs `main.py` (all 3 agents)
2. `ui` — runs `streamlit run ui/app.py`

Both share a Docker volume so they read/write the same SQLite file and ChromaDB directory.
No Kafka container. No Postgres container. No Zookeeper. This is the entire docker-compose.

### 8.1 — Write `Dockerfile`

```dockerfile
# Single Dockerfile for both the agents (main.py) and UI (ui/app.py)
# python:3.11-slim: official image, free, minimal size
FROM python:3.11-slim

WORKDIR /app

# System deps needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (Docker layer cache — only re-runs if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download NLP data at build time so containers start instantly
# These are free, offline resources — no API calls
RUN python -m textblob.download_corpora && \
    python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"

# Pre-download the sentence-transformers embedding model (~80MB, one-time, then cached)
# This prevents a slow first-run download inside the container
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy all source code
COPY . .

# Create data directories
RUN mkdir -p /app/data/chroma_db /app/data

# Default command — overridden per service in docker-compose.yml
CMD ["python", "main.py"]
```

### 8.2 — Write `.dockerignore`

```
.venv/
__pycache__/
*.pyc
.env
data/
logs/
.git/
*.db
```

### 8.3 — Write `docker-compose.yml`

```yaml
version: "3.9"

# Shared volume so both services read/write the same SQLite + ChromaDB files
volumes:
  shared_data:

services:

  # ── Agents (ingest + analysis + storage) ────────────────────────────────────
  app:
    build: .
    container_name: finance_agents
    command: python main.py
    env_file: .env
    volumes:
      - shared_data:/app/data   # SQLite + ChromaDB on shared volume
    restart: on-failure
    # For faster local testing, override intervals:
    # environment:
    #   INGEST_INTERVAL_SECONDS: "30"
    #   ANALYSIS_INTERVAL_SECONDS: "60"

  # ── Streamlit UI ─────────────────────────────────────────────────────────────
  ui:
    build: .
    container_name: finance_ui
    command: streamlit run ui/app.py --server.port=8501 --server.address=0.0.0.0
    env_file: .env
    ports:
      - "8501:8501"
    volumes:
      - shared_data:/app/data   # Same volume — reads SQLite written by agents
    depends_on:
      - app
    restart: on-failure
```

### 8.4 — Build and run

```bash
# Build images (first build takes a few minutes — downloads NLP models)
docker-compose build

# Start everything
docker-compose up -d

# Watch logs from all services
docker-compose logs -f

# Check status
docker-compose ps
```

### 8.5 — Verify end to end

```bash
# After ~5 minutes (first ingest cycle), check DB has data:
docker exec finance_agents python -c "
from agents.storage_agent import get_latest_prices, get_recent_insights
print('Prices:', get_latest_prices())
print('Insights:', len(get_recent_insights()), 'generated so far')
"

# Open UI:
# http://localhost:8501
```

### 8.6 — Final commit and tag

```bash
git add Dockerfile .dockerignore docker-compose.yml
git commit -m "feat: Dockerfile + docker-compose (2 services, shared volume, no Kafka/Postgres)"
git push

git tag -a v0.1.0 -m "MVP: 3-agent finance advisor, all open-source, zero cost"
git push origin v0.1.0
```

**✅ Acceptance Criteria:**
- `docker-compose ps` shows `finance_agents` and `finance_ui` both running
- `http://localhost:8501` loads the dashboard
- After 10–15 minutes, at least one insight appears in the UI

---

## Step 9 — Tests

**Context for Cursor:** Write basic tests for the two most important agent functions.
Use Python's built-in `unittest` — no extra test framework to install.

### 9.1 — Write `tests/test_ingest.py`

```python
"""tests/test_ingest.py — basic tests for ingest agent functions."""

import unittest
from unittest.mock import patch, MagicMock


class TestFetchMarketData(unittest.TestCase):

    def test_bad_symbol_is_skipped(self):
        """If yfinance returns no price, the symbol should be skipped gracefully."""
        import asyncio
        from core.models import init_db
        from core.settings import settings
        from agents.ingest_agent import fetch_market_data

        with patch("agents.ingest_agent.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.fast_info.last_price = None
            engine = init_db("sqlite:///:memory:")
            result = asyncio.run(fetch_market_data(engine))
            self.assertEqual(result, [])

    def test_sentiment_label_ranges(self):
        """Sentiment labels map correctly to polarity score ranges."""
        from agents.analysis_agent import analyze_sentiment
        self.assertEqual(analyze_sentiment("amazing profit boom")[0], "positive")
        self.assertEqual(analyze_sentiment("terrible crash disaster")[0], "negative")
        self.assertEqual(analyze_sentiment("the market was open today")[0], "neutral")


class TestSettings(unittest.TestCase):

    def test_database_url_is_sqlite(self):
        """DATABASE_URL must be SQLite — not Postgres or anything paid."""
        from core.settings import settings
        self.assertTrue(
            settings.DATABASE_URL.startswith("sqlite:///"),
            "DATABASE_URL must use SQLite (free, local). Never use Postgres here.",
        )

    def test_gemini_model_is_free_tier(self):
        """Gemini model must be the free flash model, not the paid pro model."""
        from core.settings import settings
        self.assertIn(
            "flash",
            settings.GEMINI_MODEL,
            "GEMINI_MODEL must be gemini-1.5-flash (free tier). "
            "gemini-pro requires billing and is not allowed.",
        )


if __name__ == "__main__":
    unittest.main()
```

### 9.2 — Run tests

```bash
python -m pytest tests/ -v
# Or without pytest:
python -m unittest discover tests/
```

### 9.3 — Commit

```bash
git add tests/
git commit -m "test: basic tests for ingest, sentiment, settings constraints"
git push
```

---

## Step 10 — Polish README for Resume

**Context for Cursor:** Replace `README.md` with a full project description suitable for a GitHub
portfolio. This is what recruiters and interviewers will read.

### 10.1 — Replace `README.md`

```markdown
# Multi-Agent AI Personal Finance Advisor

> A personal project demonstrating multi-agent AI architecture, RAG, LLM integration,
> and containerized deployment — built entirely with free, open-source tools.

## What It Does

Monitors stock prices and financial news in real time, analyzes market sentiment,
retrieves relevant context from a local knowledge base, and generates personalized
investment insights using Google Gemini — all automatically, on a schedule.

## Architecture

Three specialized agents communicate via async message queues:

```
Ingest Agent  →  [raw_market_queue]  →  Analysis Agent  →  [insights_queue]  →  Storage Agent
              →  [raw_news_queue]   →                                         →  Streamlit UI
```

| Agent | Responsibility |
|---|---|
| **Ingest Agent** | Fetches stock prices (yfinance) and news (RSS/feedparser) on a schedule |
| **Analysis Agent** | Sentiment analysis (TextBlob) + LLM Wiki KB maintenance + Gemini LLM |
| **Storage Agent** | Persists insights to SQLite; serves data to the UI |

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Agent orchestration | Python `asyncio` | Event-driven, concurrent, zero infrastructure |
| LLM | Google Gemini 1.5 Flash | Free tier, 1M tokens/day |
| Knowledge Base | LLM Wiki (Karpathy pattern) | Persistent, compounding markdown wiki — no vector DB needed |
| Sentiment | TextBlob | Free, offline NLP |
| Market data | yfinance | Free Yahoo Finance wrapper |
| News | feedparser (RSS) | Free, no API key |
| Database | SQLite + SQLAlchemy | Zero-config, file-based |
| UI | Streamlit | Free, Python-native dashboard |
| Deployment | Docker + docker-compose | Fully containerized |

**Total cost to run: $0.00**

## Quick Start

### Prerequisites
- Docker + docker-compose installed
- Free Gemini API key from https://aistudio.google.com/ (no credit card needed)

### Run

```bash
git clone https://github.com/YOUR_USERNAME/multi-agent-finance
cd multi-agent-finance
cp .env.example .env
# Edit .env: paste your GEMINI_API_KEY
docker-compose up --build
```

Open **http://localhost:8501** for the dashboard.

First insights appear after ~10 minutes (one full ingest + analysis cycle).

### Run locally (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your Gemini key
python main.py        # agents in terminal
# separate terminal:
streamlit run ui/app.py
```

## Project Structure

```
agents/          # The 3 specialized agents
core/            # Shared config, DB models, message queues
ui/              # Streamlit dashboard
tests/           # Unit tests
main.py          # Entry point (starts all agents)
docker-compose.yml
```

## Design Decisions

**Why LLM Wiki instead of RAG (ChromaDB)?**
Traditional RAG re-derives knowledge from raw chunks on every query. The LLM Wiki pattern
(Karpathy, April 2026) has Gemini incrementally compile incoming data into a persistent,
interlinked markdown wiki. Knowledge compounds — cross-references are pre-built, contradictions
pre-flagged, synthesis pre-written. Queries read pre-compiled pages instead of searching vectors.
No embedding model download, no vector DB infrastructure — just markdown files on disk.

**Why SQLite instead of PostgreSQL?**
Single user, single machine. Same SQLAlchemy ORM — one line change to upgrade.

**Why Gemini 1.5 Flash?**
Only free LLM with a generous enough free tier (1M tokens/day) to run a
scheduled personal project without hitting limits or paying anything.

## Future Improvements
- [ ] Swap async queues for Apache Kafka for distributed deployment
- [ ] Add user-input queries via the UI (currently auto-generated)
- [ ] Add portfolio tracking (user enters holdings, system monitors them)
- [ ] Migrate to PostgreSQL for multi-user support
- [ ] Add more data sources (SEC filings, earnings calendars)
```

### 10.2 — Final push

```bash
git add README.md
git commit -m "docs: complete README for portfolio/resume"
git push
```

---

## Appendix A — Adapting Existing Skeleton to This Plan

If you already created files based on the old plan (v1 with Kafka + Postgres), tell Cursor:

> "I have an existing repo with the structure from the old plan. Refactor it to match the v3 plan.
> Specifically:
> - Replace `config/settings.py` content with `core/settings.py` content from the new plan
> - Replace `db/models.py` with `core/models.py` (SQLite, 3 tables)
> - Create `core/queues.py` with the async queue definitions
> - **Create `core/wiki.py`** with the LLM Wiki knowledge base module (3 operations: ingest_to_wiki, query_wiki, lint_wiki)
> - Rewrite `agents/ingest_agent.py` to use asyncio and queues instead of Kafka
> - **Replace ChromaDB RAG in `agents/analysis_agent.py`** with LLM Wiki:
>   - Remove all chromadb imports, embed_article(), retrieve_context(), and ChromaDB client setup
>   - Remove sentence-transformers from requirements.txt
>   - Import ingest_to_wiki, query_wiki, lint_wiki from core.wiki
>   - In the agent loop, replace the embed + retrieve + build_prompt + call_gemini pattern
>     with: ingest_to_wiki() on new data, query_wiki() to get the insight
>   - Add periodic lint_wiki() call every WIKI_LINT_INTERVAL_HOURS
> - Rename `agents/report_agent.py` to `agents/storage_agent.py` and rewrite it
> - Replace `orchestrator/orchestrator.py` with `main.py` at project root
> - Replace `docker-compose.yml` with the v3 version (remove Kafka + Postgres services)
> - Replace `CHROMA_PERSIST_DIR` env var with `WIKI_DIR` everywhere
> - Replace `data/chroma_db/` folder references with `data/wiki/`
> - For any file that no longer exists in v3, add a comment at the top:
>   `# DEPRECATED in v3 — functionality moved to [new file]`
>   but do not delete the file"

---

## Appendix B — Free Tier Reference

| Service | Limit | Behavior when hit |
|---|---|---|
| Gemini 1.5 Flash | 15 req/min, 1M tokens/day | Auto-retry with backoff (built in) |
| yfinance | Soft limit ~2000 req/day | 5-min poll interval avoids this |
| RSS feeds | None | Polite 5-min interval |
| LLM Wiki (markdown files) | Unlimited (local disk) | None |
| SQLite | Unlimited (local file) | None |
| GitHub | Unlimited public repos | None |

## Appendix C — Troubleshooting

**`GEMINI_API_KEY` not working:**
```bash
python -c "import google.generativeai as genai; genai.configure(api_key='YOUR_KEY'); print(genai.GenerativeModel('gemini-1.5-flash').generate_content('hi').text)"
```
Get a free key at https://aistudio.google.com/ — no credit card, no billing setup.

**sentence-transformers slow on first run:**
Normal. It downloads `all-MiniLM-L6-v2` (~80MB) once then caches it.
In Docker this happens at build time so containers start instantly.

**Wiki shows empty pages after first ingest:**
Gemini rate limit hit during ingest. Check logs for `[tenacity]` retries. Wait 1 minute,
then trigger manually: `python -c "import asyncio; from core.wiki import lint_wiki; asyncio.run(lint_wiki())"`

**`data/wiki/` is missing or empty after 30+ minutes:**
Check agent logs: `docker-compose logs app`
Most likely cause: Gemini API key is invalid or `GEMINI_MODEL` was changed to a paid model.

**`sqlite3.OperationalError: unable to open database file`:**
The `data/` directory doesn't exist. Run `mkdir -p data` then restart.
