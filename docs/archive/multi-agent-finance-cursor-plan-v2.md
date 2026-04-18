# Multi-Agent AI Personal Finance Advisor — Cursor Execution Plan (v2)

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
| ChromaDB + sentence-transformers | RAG / vector search |
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
│  │ - RSS feeds  │                      │ - ChromaDB RAG    │   │
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
│   ├── chroma_db/             # ChromaDB vector store (auto-created)
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

## Step 4 — Agent 2: Analysis Agent

**Context for Cursor:** This is the most important agent — it does three things in sequence:
1. **Sentiment**: classifies news using TextBlob (offline, free, no API)
2. **RAG**: embeds news into ChromaDB (local, free) and retrieves relevant context
3. **Gemini**: builds a prompt from all signals and calls Gemini 1.5 Flash (free tier)

It consumes from both input queues and puts finished insights on `insights_queue`.

**Rate limit handling is critical:** Gemini free tier allows ~15 requests/minute.
The `tenacity` retry decorator handles this automatically with exponential backoff.
Never remove the retry decorator. Never suggest upgrading to paid.

### 4.1 — Write `agents/analysis_agent.py`

```python
"""
agents/analysis_agent.py

Agent 2: Analysis (Sentiment + RAG + Gemini LLM)

Responsibility: consume raw data, enrich it with sentiment and retrieved
context, call Gemini to generate insights, put results on insights_queue.

Tools used:
  TextBlob      — sentiment analysis, free, runs offline, no API cost
  ChromaDB      — local vector database, free, runs on disk
  sentence-transformers/all-MiniLM-L6-v2
                — embedding model, free, ~80MB download once, then offline
  Gemini 1.5 Flash
                — LLM, FREE TIER (15 req/min, 1M tokens/day)
                  Key from: https://aistudio.google.com/ (no credit card)

Queues consumed:  raw_market_queue, raw_news_queue
Queues produced:  insights_queue
"""

import asyncio
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from loguru import logger
from textblob import TextBlob
import chromadb
from chromadb.utils import embedding_functions
import google.generativeai as genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

from core.settings import settings
from core.queues import raw_market_queue, raw_news_queue, insights_queue


# ── Gemini setup ──────────────────────────────────────────────────────────────
# IMPORTANT: gemini-1.5-flash is the FREE model.
# Do NOT change this to gemini-pro or gemini-1.5-pro — those require billing.
genai.configure(api_key=settings.GEMINI_API_KEY)
_gemini = genai.GenerativeModel(settings.GEMINI_MODEL)


# ── ChromaDB setup ────────────────────────────────────────────────────────────
# sentence-transformers/all-MiniLM-L6-v2:
#   - Free HuggingFace model, ~80MB
#   - Downloads automatically on first run, then cached locally forever
#   - Runs 100% offline after download — no API calls, no cost
_chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
_news_collection = _chroma_client.get_or_create_collection(
    name="financial_news",
    embedding_function=_embed_fn,
    metadata={"hnsw:space": "cosine"},
)


# ── Sentiment ─────────────────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> tuple[str, float]:
    """
    Classify text sentiment using TextBlob.
    TextBlob is free, open-source, and runs completely offline.
    Returns (label, score) where score is -1.0 (negative) to +1.0 (positive).
    """
    score = TextBlob(text).sentiment.polarity
    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"
    return label, round(score, 4)


# ── RAG: embed + retrieve ─────────────────────────────────────────────────────

def embed_article(article: dict) -> None:
    """Store a news article in the local ChromaDB vector store."""
    doc_id = f"news_{abs(hash(article['headline']))}"
    text = article["headline"] + " " + article.get("body", "")
    _news_collection.upsert(
        documents=[text],
        metadatas=[{
            "headline": article["headline"][:200],
            "source": article.get("source", ""),
            "url": article.get("url", ""),
        }],
        ids=[doc_id],
    )


def retrieve_context(query: str, n: int = 4) -> list[dict]:
    """
    Find the most relevant stored articles for a query.
    Returns a list of dicts with text, source, url, and similarity score.
    """
    count = _news_collection.count()
    if count == 0:
        return []

    results = _news_collection.query(
        query_texts=[query],
        n_results=min(n, count),
    )
    docs = []
    if results and results["documents"]:
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            docs.append({
                "text": text[:300],
                "source": meta.get("source", ""),
                "url": meta.get("url", ""),
                "score": round(1 - dist, 3),
            })
    return docs


# ── Gemini call with retry ────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(settings.GEMINI_RETRY_MAX),
    wait=wait_exponential(
        multiplier=settings.GEMINI_RETRY_BACKOFF_BASE,
        min=2,
        max=60,
    ),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _call_gemini_sync(prompt: str) -> str:
    """
    Call Gemini 1.5 Flash (free tier) with automatic retry on rate limits.
    tenacity retries up to GEMINI_RETRY_MAX times with exponential backoff.
    This handles the ~15 req/min free tier limit gracefully — no paid upgrade needed.
    """
    response = _gemini.generate_content(prompt)
    return response.text


async def call_gemini(prompt: str) -> str:
    """Async wrapper — runs the sync Gemini call in a thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_gemini_sync, prompt)


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(
    query: str,
    market_data: list[dict],
    sentiment_items: list[dict],
    rag_docs: list[dict],
) -> str:
    """Assemble the Gemini prompt from all available signals."""
    market_text = "\n".join(
        f"  {d['symbol']}: ${d['price']:.2f}" for d in market_data[:10]
    ) or "  No market data available yet."

    sentiment_text = "\n".join(
        f"  [{s['label'].upper()} {s['score']:+.2f}] {s['headline'][:100]}"
        for s in sentiment_items[:6]
    ) or "  No sentiment data available yet."

    context_text = "\n".join(
        f"  (relevance {d['score']:.2f}) {d['text'][:200]}"
        for d in rag_docs[:3]
    ) or "  No retrieved context available yet."

    return f"""You are a concise, data-driven personal finance AI assistant.
Answer the question below using ONLY the data provided. Do not invent data.

QUESTION: {query}

CURRENT STOCK PRICES:
{market_text}

RECENT NEWS WITH SENTIMENT:
{sentiment_text}

RELEVANT CONTEXT FROM KNOWLEDGE BASE:
{context_text}

Instructions:
- Answer in 3–4 paragraphs maximum
- Reference specific data points (prices, sentiment scores) where relevant
- Be balanced — do not over-promise returns
- End with a one-sentence risk disclaimer
- This is for educational purposes only

YOUR RESPONSE:"""


# ── Main agent loop ───────────────────────────────────────────────────────────

async def run() -> None:
    """
    Main analysis loop. Drains both input queues, then every
    ANALYSIS_INTERVAL_SECONDS generates a Gemini insight from accumulated data.
    """
    logger.info("[Analysis Agent] Starting...")

    # Rolling buffers of recent data (capped size = memory-safe)
    market_buffer: deque = deque(maxlen=50)
    news_buffer: deque = deque(maxlen=100)
    sentiment_buffer: deque = deque(maxlen=100)

    last_analysis: float = 0.0

    while True:
        # ── Drain market queue (non-blocking) ─────────────────────────────────
        drained_market = 0
        while not raw_market_queue.empty():
            item = await raw_market_queue.get()
            market_buffer.append(item)
            drained_market += 1
        if drained_market:
            logger.info(f"[Analysis Agent] Drained {drained_market} market items")

        # ── Drain news queue, embed into ChromaDB, score sentiment ────────────
        drained_news = 0
        while not raw_news_queue.empty():
            article = await raw_news_queue.get()
            news_buffer.append(article)

            # Embed into ChromaDB for RAG retrieval later
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, embed_article, article)

            # Score sentiment
            label, score = analyze_sentiment(
                article["headline"] + " " + article.get("body", "")
            )
            sentiment_buffer.append({
                "headline": article["headline"],
                "label": label,
                "score": score,
            })
            drained_news += 1

        if drained_news:
            logger.info(f"[Analysis Agent] Processed {drained_news} news articles")

        # ── Check if it's time to run a Gemini analysis ───────────────────────
        import time
        now = time.time()
        if now - last_analysis < settings.ANALYSIS_INTERVAL_SECONDS:
            await asyncio.sleep(10)  # check queues again in 10s
            continue

        if not market_buffer and not news_buffer:
            logger.info("[Analysis Agent] No data yet, waiting for ingest agent...")
            await asyncio.sleep(30)
            continue

        logger.info("[Analysis Agent] Running Gemini analysis...")

        query = (
            "Based on the current stock prices and recent financial news, "
            "what is the overall market outlook and are there any notable "
            "opportunities or risks for a retail investor to be aware of?"
        )

        # Retrieve relevant context from ChromaDB
        rag_docs = await asyncio.get_event_loop().run_in_executor(
            None, retrieve_context, query
        )

        # Build prompt and call Gemini (free tier, with retry)
        prompt = build_prompt(
            query,
            list(market_buffer),
            list(sentiment_buffer),
            rag_docs,
        )

        try:
            insight_text = await call_gemini(prompt)
            logger.info(f"[Analysis Agent] Insight generated ({len(insight_text)} chars)")
        except Exception as e:
            logger.error(f"[Analysis Agent] Gemini failed after retries: {e}")
            last_analysis = now
            continue

        # Build sentiment summary string for storage
        pos = sum(1 for s in sentiment_buffer if s["label"] == "positive")
        neg = sum(1 for s in sentiment_buffer if s["label"] == "negative")
        neu = sum(1 for s in sentiment_buffer if s["label"] == "neutral")
        sentiment_summary = f"{pos} positive, {neg} negative, {neu} neutral headlines"

        insight_msg = {
            "user_query": query,
            "insight_text": insight_text,
            "sentiment_summary": sentiment_summary,
            "sources": json.dumps([d.get("url", "") for d in rag_docs if d.get("url")]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await insights_queue.put(insight_msg)
        logger.info("[Analysis Agent] Insight put on insights_queue")
        last_analysis = now
```

### 4.2 — Test Gemini key works

```bash
python -c "
import google.generativeai as genai
from core.settings import settings
genai.configure(api_key=settings.GEMINI_API_KEY)
m = genai.GenerativeModel('gemini-1.5-flash')
r = m.generate_content('Say: Gemini free tier is working')
print(r.text)
"
```

### 4.3 — Commit

```bash
git add agents/analysis_agent.py
git commit -m "feat: analysis agent (TextBlob + ChromaDB RAG + Gemini free tier)"
git push
```

**✅ Acceptance Criteria:**
- Gemini test prints a response
- `python -c "from agents.analysis_agent import analyze_sentiment; print(analyze_sentiment('stocks are crashing badly'))"` prints `('negative', ...)`
- ChromaDB dir is created at `data/chroma_db/`

---

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
| **Analysis Agent** | Sentiment analysis (TextBlob) + RAG retrieval (ChromaDB) + Gemini LLM |
| **Storage Agent** | Persists insights to SQLite; serves data to the UI |

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Agent orchestration | Python `asyncio` | Event-driven, concurrent, zero infrastructure |
| LLM | Google Gemini 1.5 Flash | Free tier, 1M tokens/day |
| Vector search | ChromaDB + sentence-transformers | Local RAG, no cloud cost |
| Embeddings | `all-MiniLM-L6-v2` | Free HuggingFace model, runs offline |
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

**Why async queues instead of Kafka?**
Same publish/subscribe pattern, zero infrastructure for a personal project.
The architecture is message-bus agnostic — swapping in Kafka or Redis Streams
requires only changing `core/queues.py`.

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

> "I have an existing repo with the structure from the old plan. Refactor it to match the v2 plan.
> Specifically:
> - Replace `config/settings.py` content with `core/settings.py` content from the new plan
> - Replace `db/models.py` with `core/models.py` (SQLite, 3 tables)
> - Create `core/queues.py` with the async queue definitions
> - Rewrite `agents/ingest_agent.py` to use asyncio and queues instead of Kafka
> - Merge `agents/sentiment_agent.py` + `agents/analysis_agent.py` + `agents/rag_agent.py`
>   into one new `agents/analysis_agent.py`
> - Rename `agents/report_agent.py` to `agents/storage_agent.py` and rewrite it
> - Replace `orchestrator/orchestrator.py` with `main.py` at project root
> - Replace `docker-compose.yml` with the v2 version (remove Kafka + Postgres services)
> - For any file that no longer exists in v2, add a comment at the top:
>   `# DEPRECATED in v2 — functionality moved to [new file]`
>   but do not delete the file"

---

## Appendix B — Free Tier Reference

| Service | Limit | Behavior when hit |
|---|---|---|
| Gemini 1.5 Flash | 15 req/min, 1M tokens/day | Auto-retry with backoff (built in) |
| yfinance | Soft limit ~2000 req/day | 5-min poll interval avoids this |
| RSS feeds | None | Polite 5-min interval |
| ChromaDB | Unlimited (local disk) | None |
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

**ChromaDB `no space left` error:**
`data/chroma_db/` is growing. Run: `rm -rf data/chroma_db/ && mkdir data/chroma_db/`
to reset the vector store (harmless — it just re-embeds on next run).

**Streamlit shows "no insights yet" after 30+ minutes:**
Check agent logs: `docker-compose logs app`
Most likely cause: Gemini API key is invalid or `GEMINI_MODEL` was changed to a paid model.

**`sqlite3.OperationalError: unable to open database file`:**
The `data/` directory doesn't exist. Run `mkdir -p data` then restart.
