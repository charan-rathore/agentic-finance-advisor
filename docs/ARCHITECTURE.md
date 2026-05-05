# Architecture

> Multi-agent AI investment advisor for Indian retail investors ("Bharat"), with a
> parallel global (US) market track. Free-tier-only stack - zero operational cost.

## Core Principles

1. **India-first** - primary knowledge base is `data/wiki_india/`; Indian instruments,
   INR-denominated examples, SEBI/AMFI regulatory context, SIP-first advice.
2. **Dual-wiki, shared engine** - the same three-agent pipeline serves both an Indian
   wiki and a global wiki. Switching is a single setting; no code is duplicated.
3. **LLM Wiki over RAG** - Gemini compiles incoming data into persistent markdown pages
   that compound over time. Queries read pre-synthesised knowledge instead of searching
   raw vectors. No vector DB, no embedding model costs.
4. **Trust Layer** - every answer carries a confidence score (0.30-1.00) computed from
   observable signals (staleness, source diversity, recency). Every wiki write is
   version-tracked with its source URLs. Users can always see *why* to trust advice.
5. **Fail-safe fetching** - cadence tracking, per-source timeouts, content-hash dedup,
   graceful degradation when any API key is absent.
6. **Zero cost** - Gemini free tier (1 M tokens/day) + yfinance + RSS + AMFI NAV API +
   RBI rates + SQLite. No credit card required to run the prototype.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Data Flow - Dual Market                            │
└─────────────────────────────────────────────────────────────────────────────┘

  INDIAN DATA SOURCES          GLOBAL DATA SOURCES
  ─────────────────            ────────────────────
  NSE (.NS via yfinance) ──┐   yfinance (US) ──────┐
  AMFI NAV API ────────────┤   Alpha Vantage ───────┤
  RBI rates ───────────────┤   Finnhub ─────────────┤
  ET / LiveMint RSS ───────┤   FRED macro ──────────┤
  Google News (.NS) ───────┘   Google News (US) ─────┘
           │                              │
           ▼                              ▼
  ┌─── Ingest Agent ──────────────────────────────────────────┐
  │  • Fetches all sources on configurable cadences            │
  │  • Saves raw JSON to data/raw/ (provenance envelope)       │
  │  • Tracks fetch state in SQLite (prevents re-hammering)    │
  │  • Each source timeout-guarded (180 s ceiling)             │
  └─────────────────────────────────┬─────────────────────────┘
                                    │  raw_market_queue
                                    │  raw_news_queue
                                    ▼
  ┌─── Analysis Agent ────────────────────────────────────────┐
  │  • TextBlob sentiment on news headlines                    │
  │  • Routes to India wiki or Global wiki by market tag       │
  │  • Calls Gemini to update wiki pages from raw data         │
  │  • Confidence scoring on every query answer                │
  │  • Beginner / horizon / profile-aware routing              │
  │  • lint_wiki() every 6h - contradiction + staleness audit   │
  └─────────────────────────────────┬─────────────────────────┘
                                    │  insights_queue
                       ┌────────────┼────────────┐
                       ▼            ▼            ▼
              data/wiki_india/   data/wiki/   data/raw/
              (PRIMARY)          (global)     (all sources)

                                    │
                                    ▼
  ┌─── Storage Agent ─────────────────────────────────────────┐
  │  • SQLite ORM: market_snapshots, news_articles, insights   │
  │  • source_registry, knowledge_versions (Trust Layer)       │
  │  • user_profiles (personalisation)                         │
  │  • Query helpers for Streamlit UI                          │
  └─────────────────────────────────┬─────────────────────────┘
                                    │
                                    ▼
  ┌─── Streamlit UI (port 8501) ──────────────────────────────┐
  │  Market selector:  🇮🇳 Indian Market  |  🌐 Global Market  │
  │  Tabs: Dashboard · Ask Advisor · System Health · Sources   │
  │  Sidebar: Experience level · Investment horizon · Profile  │
  └───────────────────────────────────────────────────────────┘
```

---

## Three-Agent Pipeline

### Agent 1 - Ingest Agent (`agents/ingest_agent.py`)

**What it does:** Continuously fetches market data and news on configurable cadences.
Saves everything to `data/raw/` with a provenance envelope before any processing.

**Indian data sources:**
| Source | What it provides | Cadence | Key |
| --- | --- | --- | --- |
| yfinance `.NS` symbols | NSE price + volume | 5 min | None |
| AMFI NAV API (mfapi.in) | Mutual fund daily NAV | 24 h | None |
| RBI DBIE | Repo rate, CPI India, INR/USD | 24 h | None |
| Google News RSS (`.NS`) | Indian equity news | 5 min | None |
| Economic Times RSS | Market commentary | 5 min | None |

**Global data sources:**
| Source | What it provides | Cadence | Key |
| --- | --- | --- | --- |
| yfinance (US) | US equity price + volume | 5 min | None |
| SEC EDGAR | Company facts (XBRL) | 24 h | None |
| FRED | US macro (CPI, UNRATE, GDP) | 24 h | Free |
| Alpha Vantage | Quote + fundamentals | 12 h | Free |
| Finnhub | Real-time + company news | 6 h | Free |

**Resilience:**
- `FetchRun` SQLite table tracks last-success per source → survives restarts
- `_guarded(coro, timeout=180)` ensures one wedged API cannot stall the loop
- SHA-256 content hashing on SEC payloads prevents redundant 7 MB re-downloads
- All sources gracefully degrade when keys are absent

### Agent 2 - Analysis Agent (`agents/analysis_agent.py`)

**What it does:** Converts raw data into structured knowledge and answers user queries.

- **Wiki routing:** Reads `data/raw/`, calls Gemini, writes to the appropriate wiki
  (`data/wiki_india/` for Indian sources, `data/wiki/` for global)
- **Sentiment:** TextBlob on news headlines → bullish / bearish / neutral
- **Query routing:** Detects beginner intent, investment horizon, user profile → picks
  the right Gemini prompt and wiki subset to answer from
- **Confidence scoring:** `_compute_confidence()` computes a 0.30–1.00 score from
  staleness flags, source diversity, and recency - attached to every filed insight
- **Health audit:** `lint_wiki()` every 6 h - Gemini-powered contradiction detection

### Agent 3 - Storage Agent (`agents/storage_agent.py`)

**What it does:** Persists everything to SQLite and exposes clean query helpers for
the Streamlit UI. Keeps the UI free of direct SQLAlchemy / agent knowledge.

---

## Knowledge Base Architecture

### Dual Wiki Design

```
data/
├── wiki_india/                  ← PRIMARY (thesis deliverable)
│   ├── index.md                 # Catalog of all Indian knowledge pages
│   ├── log.md                   # Append-only operation log
│   ├── overview.md              # Nifty/Sensex + RBI macro synthesis
│   ├── stocks/
│   │   ├── RELIANCE.md          # Price + news + SEC-equivalent fundamentals
│   │   ├── TCS.md
│   │   └── HDFCBANK.md  ...
│   ├── mutual_funds/            # NEW category - no US equivalent
│   │   ├── nifty50_index.md     # NAV history + expense ratio + risk rating
│   │   ├── elss_top5.md
│   │   └── liquid_funds.md
│   ├── concepts/
│   │   ├── finance_basics_india.md  # SIP, PPF, ELSS, NPS - India onboarding primer
│   │   └── tax_india.md             # LTCG, STCG, 80C - critical for Indian advice
│   └── insights/
│       └── (timestamped answers, confidence-scored)
│
└── wiki/                        ← SECONDARY (global / US market)
    ├── index.md
    ├── overview.md
    ├── stocks/                  # AAPL, MSFT, GOOGL ...
    ├── concepts/
    │   └── finance_basics.md    # US primer (existing)
    └── insights/
```

**Why two directories, not one with tags?**
- Each wiki can be demoed independently - clean separation for the thesis pitch
- No risk of Indian SIP advice bleeding into US equity analysis or vice versa
- Both wikis use identical code paths - `WIKI_DIR` is injected at call time
- Operational: linting, health snapshots, and TTL staleness run independently

**Dual-wiki at runtime:** `core/wiki_india.py` always points `WIKI_DIR` at `data/wiki_india/`
while `core/wiki.py` targets `data/wiki/`; the Analysis Agent routes each ingested payload
to the correct wiki by inspecting the `market` tag on the raw data envelope - Indian sources
write to `data/wiki_india/`, global sources write to `data/wiki/`. The two wikis share no
pages and their lint/health cycles run independently, so a stale US macro page never
suppresses a fresh Indian SIP recommendation.

**UserProfile personalisation layer:** When a user completes the onboarding form in the
India Advisor tab, their `UserProfile` row (income range, SIP budget, risk tolerance,
tax bracket, primary goal, investment horizon) is injected directly into the Gemini prompt
at query time via `query_india(..., profile=profile_dict)`. This means every answer is
already filtered for the user's affordability and tax situation - the advisor will not
suggest ₹25k/month SIPs to someone whose budget is ₹2k/month, and it prioritises ELSS
for users in the 30 % tax bracket automatically. The profile is stored locally in SQLite
and is never sent to any external API beyond the Gemini prompt itself.

### Wiki Page Anatomy

Every page has a YAML frontmatter block that the Trust Layer reads:

```yaml
---
page_type: stock_entity        # stock_entity | mutual_fund | concept | insight | primer
symbol: RELIANCE                # omitted for non-stock pages
market: india                   # "india" | "global" - routes queries correctly
last_updated: 2026-04-25T10:00:00+00:00
ttl_hours: 24                  # staleness threshold
data_sources: [yfinance_ns, google_news] # used for confidence scoring
confidence: high               # self-assessed: high | medium | low
stale: false                   # set to true by lint_wiki() when TTL exceeded
---
```

### Trust Layer (source provenance + knowledge versioning)

```
SQLite tables added by PRs 1–3:

source_registry
  url (unique) | domain | source_name | source_type | is_trusted | is_reachable
  http_status | first_fetched_at | last_fetched_at | fetch_count

knowledge_versions
  page_name | version | changed_at | change_summary | source_urls (JSON)
  source_types (JSON) | word_count_before | word_count_after | triggered_by
```

Every wiki write calls `record_wiki_version()` → the version history of any page
is queryable. The Streamlit "Sources & History" page (PR 5) visualises this.

### Confidence Score Rubric

Every `query_wiki` answer is filed as a structured insight page with a computed
confidence score, documented publicly so it can be explained in the thesis pitch:

| Signal | Deduction |
| --- | --- |
| Any consulted page has `stale: true` | −0.15 per page |
| Fewer than 2 distinct `data_sources` types across consulted pages | −0.20 |
| All consulted pages have `last_updated` > 24 h ago | −0.10 |
| **Floor** | **0.30** |

A score of 1.00 means: all pages are fresh, from diverse sources, and none are stale.
A score of 0.30 means: the answer is a best-effort guess - verify independently.

---

## SQLite Schema

```
market_snapshots   symbol | price | volume | captured_at
news_articles      headline | url | body | source | ingested_at
insights           user_query | insight_text | sentiment_summary | sources | generated_at
fetch_runs         source | key | last_attempt_at | last_success_at | last_error
source_registry    (Trust Layer - see above)
knowledge_versions (Trust Layer - see above)
user_profiles      name | monthly_income | monthly_sip_budget | risk_tolerance
                   tax_bracket_pct | primary_goal | horizon_pref | created_at
```

---

## Query Routing Logic

```
User question
      │
      ├─ Market selector (UI) ─────────────────────────────────┐
      │                                                         │
      ▼                                                         ▼
  Indian wiki flow                                       Global wiki flow
      │                                                         │
      ├─ detect_beginner_intent() ── yes ──► beginner_india_answer()
      │
      ├─ classify_investment_horizon()
      │     ├─ "short"        ──► short_term_india_answer()   [FD/liquid/T-bill]
      │     ├─ "intermediate" ──► intermediate_india_answer() [SIP/ELSS/index]
      │     └─ "long"         ──► long_term_india_answer()    [NPS/PPF/equity]
      │
      └─ profile_aware_query_india_wiki(question, user_profile)
            └─ inject: income, SIP budget, risk, goal, horizon into Gemini prompt
```

---

## Key Design Decisions

### Why dual wiki, not a single database?

Markdown files are human-readable, git-trackable, and diff-able. A DBA can understand
a wiki page; they cannot read an embedding vector. When the thesis panel asks "where
did this answer come from?", you can open the markdown file and show them.

### Why SIP-first for Indian retail?

SIP (Systematic Investment Plan) has 7.9 Cr active accounts in India (AMFI, March 2026).
It is the dominant retail investment product for the ₹10K-₹1L/month income segment -
exactly the TAM the problem statement targets. Starting the advisor with SIP education
meets users where they already are.

### Why LLM Wiki over RAG for India?

Indian financial regulation changes frequently (SEBI circulars, budget tax changes,
RBI policy). A wiki that Gemini actively maintains and corrects is more reliable than
a vector index that silently serves stale embeddings. The TTL + staleness detection
system ensures users always see when information is outdated.

### Why confidence scores matter more for Indian retail users?

An Indian retail user investing ₹5,000/month on a ₹40,000 income cannot afford to
act on bad advice the way a US investor with a diversified portfolio can. The Trust
Layer's confidence score + "any stale pages" flag gives users an honest signal of
how much to trust the current answer - and the rubric is documented publicly so it
survives scrutiny.

### Migration Readiness

| Component | Current | When to upgrade |
| --- | --- | --- |
| Queue | `asyncio.Queue` | → Redis/SQS when multi-container |
| Database | SQLite | → PostgreSQL when multi-user |
| LLM | Gemini 1.5 Flash | → Gemini 2.5 / GPT-4o when scaling |
| Language | English | → Hindi via Gemini prompt directive today |

---

**Historical note:** This architecture evolved through three versions:
- v1: Complex microservices (Kafka, ChromaDB, FastAPI) - over-engineered for a prototype
- v2: Simplified async single process - better, but US-only
- v3: LLM Wiki + Trust Layer + dual-market - current

Previous plan documents: `docs/archive/`
