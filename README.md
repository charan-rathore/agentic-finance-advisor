# FinSight AI

**An agentic investment advisor that grounds every answer in live market data, explains
the reasoning behind each recommendation, and tells you exactly how much to trust it.**

No black boxes. No generic advice. No hallucinations dressed up as insight.

---

## The Problem With Financial Guidance Today

Most financial apps dump data on you and leave you to figure out what to do with it.
Chatbots give confident answers with no verifiable sources. Human advisors cost money
most people don't have. The result: millions of people with real savings, real goals,
and no clear path forward.

The three barriers that stop people from investing are not ambition:

- **Complexity.** Products assume you already know what SIP, ELSS, PPF, and LTCG mean.
- **Trust.** "Best fund" lists change every month; nobody explains why.
- **Advice gap.** Personalised guidance exists for high-net-worth clients. Everyone else gets content marketing.

---

## What FinSight AI Does Differently

Three things simultaneously, which no existing product combines:

**1. Teaches before it recommends.**
When you ask a question the system detects that you're new to investing, it explains
the concept first using plain language and local examples, then gives the recommendation.
You leave understanding *why*, not just *what*.

**2. Grounds every answer in live, verifiable data.**
Three specialised agents run continuously: one fetches market prices, fund NAVs, macro
rates, and news every 5 minutes; one compiles that data into a structured knowledge base
using Gemini; one persists everything to a queryable store. When you ask a question,
the answer comes from current knowledge, not a training snapshot from 18 months ago.

**3. Shows you how much to trust the answer.**
Every response carries a confidence score (0.30 to 1.00) computed from observable signals:
how fresh the data is, how many independent sources agree, whether any consulted page is
flagged as stale. The rubric is documented and shown to users. No competitor does this.

---

## Feature Overview

| Feature | Description |
| --- | --- |
| Live market dashboard | Prices, change%, status (Live / Previous Close / Delayed), last updated timestamp |
| India market track | NSE stocks, mutual fund NAVs (AMFI), RBI policy rates |
| Global market track | US equities, SEC filings, FRED macro, Alpha Vantage, Finnhub |
| AI advisor (Q&A) | Ask anything; beginner vs. expert mode auto-detected from your question |
| Personalisation | 5-question onboarding stores your income, goal, horizon, risk tolerance |
| Hindi support | One checkbox routes all answers through Gemini in Hindi |
| Trust Layer | Source registry, knowledge version history, confidence scoring on every answer |
| System Health | Wiki freshness, stale page detection, raw data inventory |
| Sources & History | Every data source the system fetched from, with trust and reachability status |

---

## Architecture: Three Agents, One Knowledge Base

```
Data Sources
  NSE prices (yfinance .NS)
  Mutual fund NAVs (AMFI)      -->  Ingest Agent  -->  data/raw/
  RBI policy rates                   (every 5 min)
  Indian market news (RSS)
  US equities + SEC + FRED
  Alpha Vantage + Finnhub
            |
            v
  Analysis Agent  -->  data/wiki_india/   (Indian knowledge base)
  (continuous)    -->  data/wiki/         (Global knowledge base)
            |
            v
  Storage Agent  -->  SQLite
  (event-driven)       market_snapshots
                       news_articles
                       insights
                       source_registry
                       knowledge_versions
                       user_profiles
            |
            v
  Streamlit UI  (port 8501)
```

The knowledge base compounds: every query answer is filed back as a versioned insight
page. The more the system runs, the richer and faster the answers become.

---

## Tech Stack

| Component | Tool | Why |
| --- | --- | --- |
| Agent runtime | Python asyncio | Three parallel agents, zero infrastructure |
| LLM | Google Gemini 2.5 Flash | Free tier, 1M tokens/day, excellent multilingual support |
| Knowledge base | LLM Wiki (Karpathy pattern) | Persistent compounding markdown, no vector DB |
| India prices | yfinance (.NS symbols) | NSE prices, free, no API key |
| Mutual fund NAVs | AMFI API (mfapi.in) | Free, daily updates, all SEBI-registered schemes |
| RBI macro | RBI DBIE JSON endpoint | Repo rate, CRR, SLR, free |
| News | feedparser (Google News RSS) | Per-symbol news, India locale, free |
| US data | SEC EDGAR, FRED, Alpha Vantage, Finnhub | Company facts, macro, fundamentals |
| Sentiment | TextBlob | Offline NLP, classifies headlines as bullish/bearish/neutral |
| Database | SQLite + SQLAlchemy | Zero-config, migrates to Postgres trivially |
| UI | Streamlit | Python-native dashboard |
| Trust Layer | core/trust.py | Source registry, knowledge versioning, confidence scoring |

**Total running cost: $0 / month on the free tier.**

---

## Quick Start

### Prerequisites

- Python 3.11+
- Free Gemini API key from [aistudio.google.com](https://aistudio.google.com/) (no credit card needed)

### Run locally

```bash
git clone <repo>
cd starter-project

python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# One-time: download TextBlob sentiment data
python -m textblob.download_corpora

cp .env.example .env
# Add your GEMINI_API_KEY to .env
# All other API keys are optional -- the system runs without them

# Terminal 1: start the three agents
python main.py

# Terminal 2: start the dashboard
streamlit run ui/app.py
# Opens at http://localhost:8501
```

First answers appear after approximately 10 minutes (one full data fetch and wiki
compilation cycle). Use `python scripts/run_data_fetch_once.py` to seed data immediately
without waiting for the loop.

### Run with Docker

```bash
cp .env.example .env   # add GEMINI_API_KEY
docker-compose up --build
# Dashboard: http://localhost:8501
```

---

## Project Structure

```
agents/
  ingest_agent.py      Fetches prices, news, fund NAVs, RBI rates every 5 min
  analysis_agent.py    Sentiment + LLM Wiki updates + Gemini query answering
  storage_agent.py     SQLite persistence + data interface for the UI

core/
  settings.py          All config loaded from .env (single source of truth)
  models.py            SQLAlchemy ORM (snapshots, insights, trust tables, profiles)
  wiki.py              LLM Wiki: ingest_to_wiki, query_wiki, confidence scoring
  wiki_india.py        India wiki pipeline (wraps wiki.py with India-specific routing)
  wiki_ingest.py       Routes raw JSON files to the correct wiki pages via Gemini
  trust.py             Trust Layer: source registry, versioning, confidence
  fetchers.py          Data fetchers: FRED, Reddit, news RSS, VIX/Fear&Greed
  fetchers_india.py    Indian fetchers: AMFI NAV, RBI rates, NSE prices, India news
  sec_client.py        SEC EDGAR async client
  alpha_vantage_client.py
  finnhub_client.py
  schemas.py           RawPayload provenance envelope

data/
  wiki_india/          Primary Indian knowledge base (Nifty, MFs, RBI, tax concepts)
  wiki/                Global (US) knowledge base
  raw/                 All fetched JSON files with provenance metadata
  reference/
    companies.yaml         US company intelligence (17 tickers)
    companies_india.yaml   Indian company intelligence (NSE top-10)

ui/app.py              Streamlit dashboard (login, market tabs, advisor, charts, health)
main.py                Entry point -- starts all three agents
tests/                 184 unit tests, all green
docs/ARCHITECTURE.md   Full system design and decision log
AGENTS.md              Developer reference (run commands, directory guide)
```

---

## For Developers

```bash
# Install dev dependencies
pip install -r requirements-dev.txt && pre-commit install

# Run tests (must always pass before committing)
pytest tests/ -q

# Linting and type checking
ruff check . && mypy core agents ui

# One-shot data fetch (seeds the DB without starting the loop)
python scripts/run_data_fetch_once.py
```

See `docs/ARCHITECTURE.md` for the full system design and `PROJECT_TODO.md` for the
decision log and open work items.

---

> **Disclaimer:** FinSight AI is a research prototype. It does not constitute
> licensed financial advice. Always verify information independently and consult
> a qualified financial advisor before making investment decisions.
