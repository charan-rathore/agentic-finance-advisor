# Architecture

Multi-agent LLM-powered finance advisor with zero external costs. Free-tier-only stack.

## Core Principles

1. **Zero cost** — Google Gemini free tier (1M tokens/day) + yfinance + RSS feeds + SQLite
2. **LLM Wiki over RAG** — persistent markdown knowledge base that compounds over time
3. **Async multi-agent** — three specialized agents communicate via `asyncio.Queue`
4. **Fail-safe data fetching** — cadence tracking, timeouts, graceful degradation

## System Overview

```
┌─ Ingest Agent ─────┐    ┌─ Analysis Agent ──┐    ┌─ Storage Agent ────┐
│ • yfinance prices  │───→│ • Sentiment (TB)  │───→│ • SQLite persist   │
│ • Google News RSS  │    │ • LLM Wiki updates │    │ • Query interface  │
│ • SEC EDGAR facts  │    │ • Gemini synthesis │    │ • Health metrics   │
│ • FRED macro       │    │ • Beginner routing │    └────────────────────┘
│ • Alpha Vantage    │    └────────────────────┘              │
│ • Finnhub          │                                        │
└────────────────────┘                                        ▼
         │                                           ┌─ Streamlit UI ─────┐
         │                                           │ • Dashboard + chat │
         ▼                                           │ • System Health    │
┌─ Raw Data ─────────┐                               │ • Beginner mode    │
│ data/raw/           │                               └────────────────────┘
│ • JSON envelopes    │                                        ▲
│ • Per-source cadence│                                        │
└─────────────────────┘                                        │
         │                                                     │
         ▼                                                     │
┌─ LLM Wiki ─────────┐                                         │
│ data/wiki/          │─────────────────────────────────────────┘
│ • stocks/AAPL.md    │
│ • concepts/*.md     │
│ • insights/*.md     │
└─────────────────────┘
```

## Three-Agent Pipeline

### 1. Ingest Agent (`agents/ingest_agent.py`)

**Responsibility:** Fetch market data, news, and SEC filings on configurable cadences.

- **Price data:** yfinance every 5 minutes (default)
- **News:** Google News RSS per symbol every 5 minutes
- **SEC company facts:** async httpx client every 24 hours
- **Macro indicators:** FRED API every 24 hours  
- **Premium sources:** Alpha Vantage (quotes/fundamentals), Finnhub (real-time/news)

**Output:** Raw JSON payloads saved to `data/raw/` + messages to `raw_market_queue` / `raw_news_queue`

**Resilience:** Per-source fetch-state tracking (SQLite), timeouts, exponential backoff, content-hash deduplication

### 2. Analysis Agent (`agents/analysis_agent.py`)

**Responsibility:** LLM knowledge synthesis and user query handling.

- **Wiki maintenance:** Processes raw data into structured `data/wiki/` markdown pages
- **Sentiment analysis:** TextBlob on news headlines → bullish/bearish/neutral classification
- **LLM routing:** Detects beginner vs. experienced queries → different Gemini prompts
- **Health monitoring:** `lint_wiki()` every 6 hours → contradiction detection + stale page flagging

**Output:** Updated wiki pages + messages to `insights_queue`

**Core innovation:** **LLM Wiki** (Karpathy pattern) — persistent markdown knowledge base that compounds over time instead of re-deriving everything from raw text

### 3. Storage Agent (`agents/storage_agent.py`)

**Responsibility:** Data persistence and query interface for the UI.

- **SQLite ORM:** 3 tables (`market_snapshots`, `news_articles`, `insights`) via SQLAlchemy
- **Query helpers:** `get_latest_prices()`, `get_recent_headlines()`, `get_recent_insights()`
- **Wiki interface:** Read operations for Streamlit (analysis agent handles writes)

**Output:** Structured data for Streamlit dashboard

## Data Architecture

### Raw Data Layer (`data/raw/`)

All external API responses saved as JSON with provenance metadata:

- **SEC:** `data/raw/sec/company_facts_<CIK>_<timestamp>.json`
- **Alpha Vantage:** `data/raw/alpha_vantage/<endpoint>_<symbol>_<timestamp>.json`  
- **Finnhub:** `data/raw/finnhub/<endpoint>_<symbol>_<timestamp>.json`
- **News/macro:** Flat files with source prefix

**Envelope schema:** `{source, endpoint, symbol, fetched_at, url, request_hash, status, payload}`

### LLM Wiki (`data/wiki/`)

Structured markdown knowledge base maintained by Gemini:

```
data/wiki/
├── index.md              # Catalog of all pages (LLM reads this first)
├── log.md                # Operation history (append-only)
├── overview.md           # Market synthesis ("rolling 24h view")
├── stocks/               
│   ├── AAPL.md           # Per-symbol: price trends + news + fundamentals
│   ├── MSFT.md
│   └── ...
├── concepts/
│   ├── finance_basics.md # Beginner primer (stocks vs bonds, risk/return)
│   └── tech_sector.md    # Cross-company thematic analysis  
└── insights/
    ├── 2026-04-18_10-30.md   # Timestamped analyses + lint reports
    └── beginner_*.md         # Tailored beginner responses
```

**YAML frontmatter:** Each page carries `{page_type, last_updated, ttl_hours, symbol?, confidence, data_sources}`

**Staleness detection:** UI + lint system flag pages past their TTL for refresh

### SQLite Schema (`core/models.py`)

Three flat tables for UI data:

- **`market_snapshots`:** `(symbol, price, volume, captured_at)`
- **`news_articles`:** `(headline, url, body, source, ingested_at)`
- **`insights`:** `(insight_text, sentiment_summary, model_used, sources, generated_at)`

**Fetch state tracking:** `fetch_runs` table prevents API re-hammering after restarts

## Key Design Decisions

### Why LLM Wiki over RAG?

- **Compounding knowledge:** Wiki pages improve over time as new data arrives
- **Human-readable:** Markdown is debuggable; embeddings are opaque
- **Cost efficiency:** No vector DB infrastructure or embedding model costs
- **Narrative coherence:** LLM maintains story threads across market events

### Why asyncio over threading?

- **I/O bound workload:** 95% waiting on HTTP APIs (yfinance, SEC, Gemini)
- **Zero deployment complexity:** Single process scales to 100s of concurrent requests  
- **Queue-based messaging:** `asyncio.Queue` gives us Kafka semantics with zero config

### Why SQLite over PostgreSQL?

- **Zero ops overhead:** File on disk, no server process
- **Desktop-first:** Personal finance advisor, not multi-tenant SaaS
- **Migration-ready:** Same SQLAlchemy ORM works with Postgres later

### Why three agents vs. one?

- **Separation of concerns:** Ingest (I/O bound), Analysis (CPU bound), Storage (CRUD)
- **Independent cadences:** News every 5min, SEC every 24h, wiki lint every 6h
- **Fault isolation:** One wedged API doesn't stall the entire system

## Operational Excellence

### Health Monitoring

- **System Health tab:** Real-time wiki freshness + raw data metrics (no Gemini calls)
- **`lint_wiki()`:** Full Gemini-powered audit (stale pages, contradictions, cross-refs)
- **Fetch state tracking:** SQLite persistence prevents re-hammering APIs after restart

### Error Handling

- **Per-source timeouts:** Heavy fetches wrapped in `asyncio.wait_for(..., 180s)`
- **Exponential backoff:** `tenacity` retry decorators on HTTP clients
- **Graceful degradation:** Missing API keys → logs warning, continues with available data
- **Content deduplication:** SHA-256 check before saving SEC company facts

### Development Quality

- **Linting:** `ruff` (E/F/I/B/UP/W rules) + `mypy` with `disallow_untyped_defs` ratchet  
- **Testing:** 35 unit tests covering data transforms, cadence logic, wiki health
- **Pre-commit hooks:** Auto-format + lint on every `git commit`
- **Documentation:** `docs/DEV.md` (tooling), `legacy/LEGACY.md` (deprecated modules)

## Scaling & Extension

### Current Limits

- **Symbols:** 17 hardcoded tickers (NVDA, AAPL, GOOGL, MSFT, ...)
- **LLM calls:** Gemini free tier (15 RPM, 1M tokens/day, 32K context window)
- **Storage:** SQLite (read-heavy, single writer)

### Growth Path

1. **More data sources:** Earnings calendars, insider trading, social sentiment
2. **Personalization:** Portfolio tracking, watchlists, custom risk profiles  
3. **Advanced analysis:** Sector rotation, technical indicators, macro correlations
4. **Multi-tenant:** PostgreSQL + user authentication + per-user wikis

### Migration Readiness

- **Database:** SQLAlchemy ORM abstracts engine differences
- **Queues:** `core/queues.py` interface layer (swap asyncio.Queue → Redis/SQS)
- **LLM:** Model adapter pattern in `core/wiki.py` (swap Gemini → Claude/GPT)

---

**Historical Context:** This architecture evolved from v1 (complex microservices) → v2 (simplified async) → v3 (LLM Wiki). Previous plan documents live in `docs/archive/` for reference.