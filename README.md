# Bharat Finance AI — AI-Native Investment Advisor for Indian Retail Investors

> **Thesis prototype** — Zupee "AI × Investments for Bharat" challenge.
> Built to help 100 million+ Indians invest and grow their money — simply, intelligently, and at zero cost.

---

## The Problem

Over 100 million Indians have smartphones, stable income, and the desire to invest — but most don't.
The barriers are not ambition. They are:

- **Complexity.** Financial apps assume you already know what SIP, ELSS, and LTCG mean.
- **Trust.** "Best mutual fund" lists change every month and nobody explains why.
- **Advice gap.** Human financial advisors serve HNIs. Retail investors get generic content.
- **Language.** Most quality financial guidance is in English, not Hindi or regional languages.

Existing apps give you data. None of them give you **understanding**.

---

## What This Builds

An AI advisor that does three things no existing app does simultaneously:

1. **Explains** — teaches the concepts you need *before* giving the recommendation,
   using language you actually understand (₹ not $, SIP not 401k, PPF not Roth IRA).

2. **Grounds every answer in live data** — Nifty 50 prices, mutual fund NAVs, RBI repo rate,
   company news — fetched continuously, synthesised into a persistent knowledge base.

3. **Tells you how much to trust the answer** — every response carries a confidence score
   (0.30–1.00) computed from observable signals: how fresh the data is, how many independent
   sources agree, whether any source is flagged as unreliable. No black box.

The result is not a chatbot that hallucinates. It is an advisor that compounds knowledge
every day and can show you exactly where every piece of advice came from.

---

## Who This Is For

**Primary:** Indian retail investor, ₹25K–₹1L/month income, has some savings, doesn't know where to start.

**Profile:** Uses UPI daily. Has a savings account. Has heard of SIP but never started one.
Wants to save tax under 80C but doesn't know if ELSS or PPF is better for their situation.
Would invest if someone explained it clearly and they could trust the advice.

**Secondary:** The same investor, 2 years later — now tracking their SIP portfolio,
optimising for LTCG efficiency, and asking nuanced questions about sector allocation.

---

## How It Works

The system has three specialised agents running in parallel:

```
┌─────────────────────────────────────────────────────────────┐
│                     Data Collection (every 5 min)           │
│                                                             │
│  NSE prices (yfinance)  ──┐                                 │
│  Mutual fund NAVs (AMFI)  ├──► Ingest Agent ──► data/raw/   │
│  RBI rates               ──┘                                │
│  Indian market news (RSS)                                   │
└─────────────────────────────────────┬───────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     Knowledge Compilation (continuous)      │
│                                                             │
│  Analysis Agent reads raw data → calls Gemini →            │
│  updates the Indian Knowledge Base (data/wiki_india/)       │
│                                                             │
│  data/wiki_india/                                           │
│  ├── overview.md          ← Nifty/Sensex + macro snapshot   │
│  ├── stocks/RELIANCE.md   ← price, news, fundamentals       │
│  ├── mutual_funds/        ← NAV, expense ratio, ratings     │
│  └── concepts/            ← SIP, PPF, ELSS, tax guide       │
└─────────────────────────────────────┬───────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     User Interaction (Streamlit UI)         │
│                                                             │
│  "I earn ₹50,000/month. Where should I invest ₹5,000?"     │
│                                                             │
│  → Detects: beginner + intermediate horizon + India market  │
│  → Reads: finance_basics_india.md + relevant fund pages     │
│  → Answers: SIP-first plan, specific fund suggestions,      │
│             tax saving (80C), confidence score              │
│                                                             │
│  Confidence: 0.87 | Sources: AMFI NAV, NSE price, RBI rate  │
└─────────────────────────────────────────────────────────────┘
```

**The knowledge base compounds.** Every good answer is filed back into the wiki as a
versioned insight. The more the system runs, the better and faster the answers become.

---

## What Makes This Different

| Feature | This project | Existing apps (Groww, Zerodha, ET Money) |
| --- | --- | --- |
| Explains *why* before recommending | ✅ | ❌ |
| Answers adapt to your income + goal + horizon | ✅ | ❌ |
| Shows confidence score on every answer | ✅ | ❌ |
| Knowledge compounds over time | ✅ | ❌ |
| Works in Hindi | ✅ (via Gemini) | Partial |
| Free to run | ✅ | N/A (B2C apps) |

The **moat** is the Trust Layer — a source provenance system that tracks every data
point used in every answer, computes an observable confidence score, and maintains
a full version history of the knowledge base. No competitor shows you *why* to trust
their advice. We show you the receipts.

---

## Tech Stack

| Component | Tool | Why |
| --- | --- | --- |
| Agents | Python `asyncio` | Three parallel agents, zero infrastructure |
| LLM | Google Gemini 1.5 Flash | Free tier, 1M tokens/day, excellent Hindi support |
| Knowledge Base | LLM Wiki (Karpathy pattern) | Persistent, compounding markdown — no vector DB |
| Indian market data | yfinance (`.NS` symbols) | NSE prices, free, no API key |
| Mutual fund NAVs | AMFI API (mfapi.in) | Free, updated daily, covers all SEBI-registered schemes |
| RBI macro | RBI DBIE | Repo rate, CPI India, INR/USD — free |
| News | feedparser (RSS) | Google News + ET + LiveMint, free, no key |
| Sentiment | TextBlob | Offline NLP, classifies news as bullish/bearish/neutral |
| Database | SQLite + SQLAlchemy | Zero-config file-based DB, migrates to Postgres easily |
| UI | Streamlit | Python-native dashboard, 10-minute setup |
| Trust Layer | Custom (`core/trust.py`) | Source registry + knowledge versioning + confidence scores |

**Total running cost: ₹0 / month.**

---

## Prototype Demo Flow

When you run the prototype, here is what a judge sees:

1. **Dashboard** — Live Nifty 50 + top NSE stocks + Sensex + RBI repo rate. Updated every 5 minutes.
2. **Ask the Advisor** — Type any question in English or Hindi:
   - *"How do I get started with investing ₹3,000 per month?"*
   - *"PPF vs ELSS — which is better for tax saving?"*
   - *"Is Reliance Industries a good stock to buy now?"*
3. **Answer with provenance** — Response includes the answer, confidence score (e.g. `0.82`),
   which wiki pages were consulted, and whether any source is stale.
4. **Sources & History** — Table of every data source the system has fetched from,
   with trust + reachability status. Per-page version history showing how the knowledge grew.
5. **System Health** — Which wiki pages are fresh vs. stale, how much raw data has been
   collected, when the last knowledge audit ran.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Free Gemini API key from [aistudio.google.com](https://aistudio.google.com/) — no credit card needed

### Run locally

```bash
git clone <repo>
cd starter-project

python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download TextBlob sentiment data (one-time)
python -m textblob.download_corpora

cp .env.example .env
# Open .env and add your GEMINI_API_KEY
# All other keys are optional — the system runs without them

python main.py          # starts all three agents (terminal 1)
streamlit run ui/app.py # opens dashboard at http://localhost:8501 (terminal 2)
```

First answers appear after ~10 minutes (one full data fetch + wiki update cycle).

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
├── ingest_agent.py      # Fetches prices, news, mutual fund NAVs, RBI rates
├── analysis_agent.py    # Sentiment + LLM Wiki updates + Gemini query answering
└── storage_agent.py     # SQLite persistence + data interface for UI

core/
├── settings.py          # All config from .env (single source of truth)
├── models.py            # SQLAlchemy ORM (market snapshots, insights, trust tables)
├── wiki.py              # LLM Wiki: ingest_to_wiki, query_wiki, confidence scoring
├── wiki_ingest.py       # Routes raw JSON files → appropriate wiki pages via Gemini
├── trust.py             # Trust Layer: source registry, knowledge versioning, confidence
├── fetchers.py          # Data fetchers: FRED, Reddit, news RSS, sentiment
├── fetchers_india.py    # Indian fetchers: AMFI NAV, RBI rates (new)
├── sec_client.py        # SEC EDGAR async client (US market)
├── alpha_vantage_client.py
├── finnhub_client.py
└── schemas.py           # RawPayload provenance envelope

data/
├── wiki_india/          # PRIMARY — Indian knowledge base (Nifty, MFs, RBI, tax)
├── wiki/                # SECONDARY — Global (US) knowledge base
├── raw/                 # All fetched JSON files with provenance metadata
│   ├── india/           # Indian raw data (AMFI, RBI, NSE news)
│   ├── sec/             # SEC EDGAR company facts
│   ├── finnhub/
│   └── alpha_vantage/
└── reference/
    ├── companies.yaml        # US company intelligence (17 tickers)
    └── companies_india.yaml  # Indian company intelligence (NSE top-10) (new)

ui/app.py               # Streamlit dashboard (market selector, advisor, health, sources)
main.py                 # Entry point — starts all three agents
tests/                  # 92 unit tests; all green
docs/ARCHITECTURE.md    # Full system design
```

---

## Pitch at a Glance

**What is the product?**
An AI investment advisor that teaches Indian retail investors what they need to know,
grounds every answer in live market data, and tells them how much to trust each answer.

**TAM:**
100M+ Indians with ₹500+/month investable surplus. Active SIP folios: 7.9 Cr and growing
at 20% YoY (AMFI, March 2026). Digital-first users already comfortable with UPI.

**Ease of adoption:**
Zero setup for users — open a browser, answer 5 profile questions, start asking.
SIP-first onboarding meets users where they already are. Hindi support removes the
language barrier. Confidence scores remove the trust barrier.

**Monetisation (power users):**
- **Free:** Basic SIP advice, market overview, tax guide, Q&A (up to 10 queries/day)
- **Premium ₹99/month:** Portfolio tracking, personalised SIP optimisation,
  goal-based projections (wedding / education / retirement), priority data refresh,
  LTCG/STCG tax impact calculator

**Moat:**
The knowledge base compounds — it gets smarter every day the system runs, unlike a
static chatbot. The Trust Layer (confidence scores + source provenance + version history)
is a structural differentiator: no competitor explains *why* to trust their advice.
Data network effect: the more users ask, the more insights are filed back into the wiki.

**12-month risks and mitigations:**
| Risk | Mitigation |
| --- | --- |
| SEBI compliance — unlicensed financial advice | "Educational only" disclaimer on every answer; confidence rubric makes limitations explicit |
| AMFI / RBI API reliability | Fetch-state tracking + graceful degradation + fallback to cached wiki pages |
| Gemini rate limits at scale | 1M tokens/day free tier; per-query caching of wiki reads; upgrade path to paid tier |
| User data privacy | All data local (SQLite file); no PII sent to LLM beyond what user explicitly types |
| Hindi accuracy | Gemini native multilingual; answers reviewed for financial terminology accuracy |

---

## For Developers

- **Dev setup:** `pip install -r requirements-dev.txt && pre-commit install`
- **Tests:** `pytest` — 92 tests, all green. Never merge if this number drops.
- **Linting:** `ruff check .` + `ruff format --check .` + `mypy core agents ui`
- **One-shot data fetch:** `python scripts/run_data_fetch_once.py`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Decisions log:** `PROJECT_TODO.md`
- **Legacy modules:** `legacy/` — archived v1/v2 code with explanations

> **Disclaimer:** This is a prototype built for educational and thesis purposes.
> It does not constitute SEBI-registered financial advice. Always consult a licensed
> financial advisor before making investment decisions.
