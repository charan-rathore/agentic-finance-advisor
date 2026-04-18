# Multi-Agent AI Personal Finance Advisor

> A personal project demonstrating multi-agent AI architecture, LLM Wiki knowledge base,
> and containerized deployment — built entirely with free, open-source tools.

## What It Does

Monitors stock prices and financial news in real time, analyzes market sentiment,
maintains a persistent knowledge base using the LLM Wiki pattern, and generates personalized
investment insights using Google Gemini — all automatically, on a schedule.

## Architecture

Three specialized agents communicate via async message queues, with a persistent LLM Wiki knowledge base:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Data Flow Architecture                           │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────┐    raw_market_queue     ┌─────────────────────────────────┐
    │             │ ──────────────────────► │                                 │
    │ Ingest      │                         │     Analysis Agent              │
    │ Agent       │    raw_news_queue       │                                 │
    │             │ ──────────────────────► │ • Sentiment (TextBlob)          │
    │ • yfinance  │                         │ • LLM Wiki Knowledge Base       │
    │ • RSS feeds │                         │ • Gemini LLM                    │
    └─────────────┘                         └─────────────┬───────────────────┘
                                                          │
                                                          │ insights_queue
                                                          │
    ┌─────────────────────────────────────────────────────▼───────────────────┐
    │                        LLM Wiki Knowledge Base                          │
    │                                                                         │
    │  data/wiki/                                                             │
    │  ├── index.md         ← Catalog of all pages                           │
    │  ├── overview.md      ← Market synthesis                               │
    │  ├── log.md           ← Operation history                              │
    │  ├── stocks/          ← Per-symbol entity pages (AAPL.md, MSFT.md)     │
    │  ├── concepts/        ← Cross-stock themes (tech_sector.md)            │
    │  └── insights/        ← Filed query answers (auto-compounding)         │
    │                                                                         │
    │  Operations: ingest_to_wiki() → query_wiki() → lint_wiki()             │
    └─────────────────────────────────────────────────────────────────────────┘
                                            │
                                            │
                                  ┌─────────▼─────────┐      ┌─────────────────┐
                                  │ Storage Agent     │      │ Streamlit UI    │
                                  │                   │ ──── │                 │
                                  │ • SQLite          │      │ • Live Dashboard│
                                  │ • Serves UI data  │      │ • Port 8501     │
                                  └───────────────────┘      └─────────────────┘

| Agent | Responsibility |
| --- | --- |
| **Ingest Agent** | Fetches prices (yfinance), news (RSS), and — when keys are present — SEC EDGAR, FRED, Alpha Vantage, Finnhub. Each heavy source is throttled via `FetchRun` cadences persisted in SQLite and hard-timeboxed so one wedged API cannot stall the loop. |
| **Analysis Agent** | Sentiment analysis (TextBlob) + LLM Wiki maintenance + Gemini insights + beginner-mode onboarding. |
| **Storage Agent** | Persists insights, market snapshots, news articles, and fetch-run state to SQLite; serves data to the UI. |

## Data sources

| Source | Required? | Provides | Free-tier limit |
| --- | --- | --- | --- |
| yfinance (Yahoo Finance) | **Required** | Intraday price + volume per symbol | Unlimited (no key) |
| RSS (Google News per-symbol) | **Required** | Headlines + summaries | Unlimited (no key) |
| Google Gemini | **Required** | LLM synthesis of the wiki + Q&A | 1 M tokens/day |
| SEC EDGAR (`core/sec_client.py`) | Optional | `companyfacts` XBRL (revenue, assets, liabilities, cash) | 10 req/s (just set `SEC_USER_AGENT`) |
| FRED (`FRED_API_KEY`) | Optional | Macro series (CPI, UNRATE, FEDFUNDS, GDP, 10Y, mortgage) | 120 req/min |
| Alpha Vantage (`ALPHA_VANTAGE_API_KEY`) | Optional | `GLOBAL_QUOTE`, `OVERVIEW`, `INCOME_STATEMENT` | 25 req/day, 5 req/min |
| Finnhub (`FINNHUB_API_KEY`) | Optional | Real-time quote, per-company news, recommendation trends | 60 req/min |
| Reddit (`REDDIT_CLIENT_*`) | Optional | Community sentiment from r/stocks, r/investing | 60 req/min |

The agent **runs cleanly when any optional source is missing** — each fetcher
short-circuits and logs a warning, the ingest loop moves on. All payloads land
in `data/raw/` wrapped in the canonical envelope defined by
`core/schemas.RawPayload` (`source`, `endpoint`, `symbol`, `fetched_at`, `url`,
`request_hash`, `status`, `payload`).

## Tech Stack

| Layer | Tool | Why |
| --- | --- | --- |
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
python3.11 -m venv .venv && source .venv/bin/activate  # Requires Python 3.11+
pip install -r requirements.txt
python -m textblob.download_corpora
python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"
cp .env.example .env  # add your Gemini key
python main.py        # agents in terminal
# separate terminal:
streamlit run ui/app.py
```

## Project Structure

```
agents/          # The 3 specialized agents
├── ingest_agent.py      # Fetches market data + news
├── analysis_agent.py    # Sentiment + LLM Wiki + Gemini
└── storage_agent.py     # SQLite persistence + UI data access

core/            # Shared config, DB models, message queues, wiki
├── settings.py          # All configuration from .env
├── models.py            # SQLAlchemy ORM models (SQLite)
├── queues.py            # Async message queues (the "message bus")
└── wiki.py              # LLM Wiki knowledge base operations

data/
├── wiki/                # LLM Wiki knowledge base (markdown files)
│   ├── index.md         # Catalog of all wiki pages
│   ├── overview.md      # Rolling market synthesis
│   ├── log.md           # Append-only operation log
│   ├── stocks/          # Per-symbol entity pages (AAPL.md, MSFT.md, ...)
│   ├── concepts/        # Cross-stock theme pages (incl. `finance_basics.md`)
│   └── insights/        # Filed query answers (good answers compound the wiki)
├── raw/                 # Raw API payloads (envelope-wrapped via core/schemas.py)
│   ├── finnhub/         # Finnhub quote/news/recommendation JSON
│   ├── alpha_vantage/   # Alpha Vantage quote/overview/income JSON
│   ├── sec/             # SEC EDGAR companyfacts JSON
│   └── (other sources)
├── reference/
│   └── companies.yaml   # Per-ticker risk profile + wiki cross-refs (17 tickers)
└── finance.db           # SQLite database file (auto-created)

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

**Why async queues instead of Kafka?**
Same publish/subscribe pattern, zero infrastructure for a personal project.
The architecture is message-bus agnostic — swapping in Kafka or Redis Streams
requires only changing `core/queues.py`.

**Why SQLite instead of PostgreSQL?**
Single user, single machine. Same SQLAlchemy ORM — one line change to upgrade.

**Why Gemini 1.5 Flash?**
Only free LLM with a generous enough free tier (1M tokens/day) to run a
scheduled personal project without hitting limits or paying anything.

## LLM Wiki Operations

The knowledge base has three main operations:

1. **`ingest_to_wiki(articles, prices)`** — LLM reads new data and updates wiki pages
   - Updates per-symbol entity pages (stocks/AAPL.md, stocks/MSFT.md)
   - Updates market overview synthesis (overview.md)
   - Rebuilds page catalog (index.md)
   - Logs all operations (log.md)

2. **`query_wiki(question)`** — LLM reads wiki to answer questions
   - Reads index.md to find relevant pages
   - Reads those pages for context
   - Synthesizes answer from pre-compiled knowledge
   - Files good answers back into insights/ for compounding

3. **`lint_wiki()`** — Periodic health-check (every 6 hours)
   - Finds contradictions between pages
   - Identifies stale or orphaned content
   - Suggests missing cross-references
   - Self-audits knowledge base integrity

## Operational tooling

- `python scripts/dedupe_sec_raw.py [--apply]` — SHA-256 dedupe for
  `data/raw/sec/`. Dry-run by default; useful if the content-hash short-circuit
  in `core/sec_client.py` ever regresses.
- **Dev setup (ruff + mypy + pre-commit):** see `docs/DEV.md`. TL;DR
  `pip install -r requirements-dev.txt && pre-commit install`.
- `python scripts/run_data_fetch_once.py` — one-shot harness that calls every
  data source once and prints a status table. Every source is wrapped in an
  individual `asyncio.wait_for(...)` so one wedged API cannot hang the script.
  Flags: `--only finnhub,fred_macro`, `--symbols AAPL,MSFT`, `--timeout 30`.
- `python scripts/smoke_new_fetchers.py` — smoke-test the Finnhub and Alpha
  Vantage clients against the live APIs.
- `core/fetch_state.py` — SQLite-backed fetch cadence tracker (`fetch_runs`
  table). Restarts no longer re-hammer every API; the ingest loop queries
  `should_fetch(source, key, interval_hours=N)` before each heavy call.
- `core/schemas.RawPayload` — canonical envelope enforced by the Alpha Vantage
  and Finnhub clients. `wiki_ingest` understands both the new envelope and
  legacy flat payloads already on disk.

## Safety against stalled fetches

Every slow data source is wrapped in two concentric timeouts:

1. Per-HTTP-request: each client sets `httpx.AsyncClient(timeout=30.0)` and
   uses `tenacity` with `stop_after_attempt(3)` for retries.
2. Per-source in the ingest loop: `agents.ingest_agent._guarded(...)` uses
   `asyncio.wait_for(coro, timeout=_HEAVY_FETCH_TIMEOUT_SECONDS)` so one wedged
   API cannot block the 5-minute ingest cycle for more than 3 minutes.

If a fetch times out, `FetchRun.last_error` is set to `timeout_or_exception`
and the next cycle will try again after the configured interval.

## Future Improvements

- [ ] Swap async queues for Apache Kafka for distributed deployment
- [ ] Add user-input queries via the UI (currently auto-generated)
- [ ] Add portfolio tracking (user enters holdings, system monitors them)
- [ ] Migrate to PostgreSQL for multi-user support
- [ ] Add more data sources (SEC filings, earnings calendars)
- [ ] Implement concept page auto-generation (sector analysis, market themes)

## Legacy folders

Everything carried over from the pre-v3 skeleton lives under `legacy/` —
`legacy/api/`, `legacy/db/`, `legacy/frontend/`, `legacy/rag/`,
`legacy/alembic/`, plus the deprecated stub agents (budget/expense/fraud/…)
moved out of `agents/`. See `legacy/LEGACY.md` for a file-by-file map of what
replaced each module in v3. Nothing in `core/`, `agents/{ingest,analysis,storage}_agent.py`,
`ui/app.py`, or `main.py` imports from `legacy/`.
