# Project TODO & Decision Log

> Living document. Cursor should consult this at the start of every new task and mark items
> `[x]` as they are completed. Each item has a short rationale so future-you (or a fresh
> Cursor session) understands *why* it matters.

Last audited: 2026-04-18. Audit snapshot:

| Test suite | Result |
| --- | --- |
| `tests/test_csv_ingest.py` | 2 passed |
| `tests/test_health.py` | 2 passed |
| `tests/test_ingest.py` | 3 passed |
| `tests/test_analysis.py` | **collection error** – imports `build_prompt` which no longer exists |

| Data-fetching smoke test | Result |
| --- | --- |
| `yfinance.Ticker.fast_info` (17 symbols) | **0 / 17 succeeded** — `yfinance==0.2.40` is broken against current Yahoo endpoints (`'currentTradingPeriod'` KeyError) |
| Yahoo RSS headlines (`feeds.finance.yahoo.com/rss/2.0/headline`) | **0 entries** — feed returns malformed XML (`bozo=1`) |
| Google News RSS (per-symbol) | **OK** — 20 articles / symbol |
| SEC EDGAR `companyfacts` (httpx client) | **OK** — 503 GAAP tags fetched for AAPL |
| SEC filings via `sec-edgar-downloader` lib | Untested, duplicates the SEC facts path |
| `fetch_vix_and_fear_greed` | **Empty output (86 bytes)** — VIX fetch uses yfinance (broken); CNN dataviz endpoint silently fails |
| FRED macro indicators | **Disabled** — no `FRED_API_KEY` in `.env` |
| Reddit sentiment | **Disabled** — no `REDDIT_CLIENT_ID/SECRET` in `.env` |
| SQLite persistence (`market_snapshots`, `news_articles`, `insights`) | **All tables empty (0 rows)** — the DB file exists but no agent run has ever successfully written |

Bottom line: the *data-fetching phase is ~30 % working*. Only SEC facts and Google News RSS
return real data; the two primary sources declared in the architecture (yfinance + Yahoo RSS)
both return nothing on current endpoints.

---

## P0 — Broken paths that block progress

- [ ] **Fix yfinance price ingestion.** `yfinance==0.2.40` returns `currentTradingPeriod`
      KeyError for every ticker. Upgrade to the latest `yfinance` (≥ 0.2.50), replace
      `ticker.fast_info.last_price` with `ticker.history(period='1d')['Close'].iloc[-1]` as a
      fallback, and add a retry/backoff around each symbol. *Why*: without this, zero price
      data lands in SQLite or the wiki.
- [ ] **Replace the dead Yahoo RSS feed.** `https://feeds.finance.yahoo.com/rss/2.0/headline`
      now returns an empty body. Swap the default in `core/settings.py` + `.env.example` to a
      working combination (e.g. Google News RSS per symbol, CNBC/Reuters RSS, SEEKING_ALPHA
      RSS). *Why*: it is the only news source configured by default.
- [ ] **Remove the `build_prompt` test to unbreak pytest collection.** `tests/test_analysis.py`
      still imports `build_prompt` from the v2 analysis agent; the v3 wiki agent deleted it.
      Either restore `build_prompt` as a thin helper (preferred, keeps prompt construction
      unit-testable) or rewrite the test against `ingest_to_wiki` / `query_wiki`.
- [ ] **Fix the duplicate `_write_wiki_file` / `_append_log` definitions in `core/wiki.py`.**
      Lines 67 and 74 both define `_write_wiki_file`; Python keeps only the async one, which
      silently returns an un-awaited coroutine when called synchronously inside
      `ingest_to_wiki`. Same issue at lines 81/89 for `_append_log`. Rename the async
      versions (e.g. `_awrite_wiki_file`, `_aappend_log`) and update `core/wiki_ingest.py`
      imports. *Why*: every wiki write currently leaks a coroutine — existing wiki pages
      were written by an older build, not by the current code.
- [ ] **Fix the `.split(',')`-on-list bug in `agents/analysis_agent.py:161`.**
      `getattr(settings, 'YFINANCE_SYMBOLS', 'AAPL,…').split(',')` raises `AttributeError`
      because `settings.YFINANCE_SYMBOLS` is already a list. Use the list directly. *Why*:
      this exception fires on every analysis cycle and short-circuits the entire extended
      fetcher block.
- [ ] **Fix the missing-`pd` bug in `fetch_earnings_calendar`.** `pd` is imported at the
      bottom of `core/fetchers.py` inside a try/except and referenced from inside the
      function body. Move `import pandas as pd` to the top (it is already a transitive
      dependency of yfinance).
- [ ] **Stop Docker build from installing a removed dependency.** `Dockerfile` line 16 runs
      `from sentence_transformers import SentenceTransformer` — but `sentence-transformers`
      and `chromadb` are no longer in `requirements.txt` (v3 removed RAG). The image build
      currently fails. Delete that line and the `/app/data/chroma_db` mkdir.
- [ ] **Purge the `.DS_Store` files that leaked into git** (`./`, `api/`, `db/`, `data/`).
      Add a `git rm --cached` for each and rely on the existing `.gitignore` rule.

## P1 — Architectural redundancies (eliminate these next)

- [ ] **Collapse the two SEC implementations into one.** Keep `core/sec_client.py` (async
      httpx, hand-rolled rate limiting, writes into `data/raw/sec/`). Delete
      `fetch_sec_filings` from `core/fetchers.py` and drop `sec-edgar-downloader` from
      `requirements.txt`. *Why*: two code paths, two disk layouts
      (`data/raw/sec/` vs `./sec-edgar-filings/`), and `wiki_ingest.process_all_new_raw_files`
      only matches files named `sec_*` — meaning the 166 MB of `company_facts_*.json` the
      working client produces is *never ingested into the wiki*.
- [ ] **Teach `wiki_ingest` to route `company_facts_*.json`.** Add a
      `process_sec_company_facts` handler and register a prefix match in
      `process_all_new_raw_files`. *Why*: right now 161 MB of raw SEC data is invisible to
      the knowledge base.
- [ ] **Content-hash the raw SEC payloads to stop re-downloading identical files.** We
      already have 3 copies of AAPL `company_facts_0000320193_*.json` (~21 MB wasted),
      2 copies each for MSFT/GOOGL/AMZN/NVDA. Either compute an SHA-256 of the response body
      and short-circuit if it matches the latest file on disk, or name files by fiscal
      period instead of fetch timestamp.
- [ ] **Move extended fetchers out of `analysis_agent.run()`.** They currently run on every
      analysis cycle (10 minutes), which means a 7 MB SEC file is re-downloaded 144×/day
      per symbol. The correct place is `ingest_agent.run()` with its own cadence config
      (e.g. `SEC_FETCH_INTERVAL_HOURS=24`, `MACRO_FETCH_INTERVAL_HOURS=24`,
      `REDDIT_FETCH_INTERVAL_HOURS=6`). Each fetcher should read its last-success timestamp
      from a small state file or SQLite and skip if inside the interval.
- [ ] **Rationalise `_write_wiki_file`'s two signatures.** After renaming (P0) keep a single
      sync helper that accepts both `str` and `Path`; the async variant is only needed if
      we move to `aiofiles` for writes (markdown files are tiny — blocking IO is fine).
- [ ] **Delete (or clearly archive) all v1/legacy stubs.** Their presence confuses Cursor
      every time it searches. Candidates:
      - `agents/base.py`, `agents/budget_agent.py`, `agents/expense_agent.py`,
        `agents/explanation_agent.py`, `agents/fraud_agent.py`, `agents/investment_agent.py`,
        `agents/news_agent.py`, `agents/orchestrator.py`, `agents/messaging.py`
      - `api/` (routes/*, schemas/*, deps.py)
      - `db/models/*`, `db/session.py`, `db/base.py` (v3 uses `core/models.py`)
      - `rag/vector_store.py`
      - `frontend/app.py` (superseded by `ui/app.py`)
      - `scripts/kafka_print_consumer.py`
      - `alembic/` + `alembic.ini` (no Postgres migrations in v3)
      - `app/main.py` (FastAPI stub) *or* promote it into a real HTTP API — pick one.
      Options: move them to `legacy/` with a top-level `LEGACY.md` explaining they are
      reference-only, or hard-delete. *Why*: 30+ one-line stubs generate noise in every
      grep/semantic search.
- [ ] **Pick one long-form plan doc and archive the rest.** `multi-agent-finance-cursor-plan-v2.md`
      (67 KB) + `v3.md` (82 KB) + `deep-research-report.md` (27 KB) are three overlapping
      design docs totalling 175 KB of prose. Pick v3 as canonical, move the others into
      `docs/archive/`. Add a short `ARCHITECTURE.md` (≤ 5 pages) that links out.
- [ ] **Drop `chroma_db` + `sentence-transformers` mentions across the repo.** `.gitignore`
      still ignores `data/chroma_db/`; `docker-compose.yml` still comments about
      "ChromaDB files"; Dockerfile downloads the embedding model (P0 already fixes one).
      Remove each leftover so new readers do not think RAG is in play.

## P2 — Data-fetching phase completeness

- [ ] **Document which data sources are *required* vs *optional*.** In `README.md` + inline
      comments, mark FRED, Reddit, SEC filings (full text), earnings calendar as OPTIONAL
      and verify the agent runs cleanly when they are absent.
- [ ] **Add provenance fields to every raw JSON payload.** Each file should carry
      `{source, fetched_at, url, request_hash, status}` — this is 80 % done; enforce it
      with a Pydantic model (`core/schemas.py`).
- [ ] **Persist fetch state in SQLite, not filesystem timestamps.** A `fetch_runs` table with
      `(source, key, last_attempt_at, last_success_at, last_content_hash, error)` gives us
      one source of truth for "when did we last try Reddit for AAPL?". Replace the ad-hoc
      `last_sec_fetch` local variable in `ingest_agent.run()`.
- [ ] **Cap `YFINANCE_SYMBOLS` against `COMPANY_INTELLIGENCE` coverage.** `.env` tracks 17
      tickers but `core/company_intelligence.py` only has profiles for 12. Either extend
      the dictionary to cover all 17 (TSM, AVGO, UNH, PG, HD) or load it from a YAML file
      in `data/reference/companies.yaml`. *Why*: missing entries fall through to the
      generic fallback and the LLM prompt loses the company-specific risk grounding.
- [ ] **Write missing unit tests for the data layer.** Minimum set:
      - `tests/test_sec_client.py` — mock httpx, assert CIK zero-padding, rate limiter
        enforces 100 ms gap, retry fires on 429.
      - `tests/test_fetchers.py` — mock Google News RSS, assert per-symbol JSON schema,
        assert empty-creds Reddit/FRED paths return `None` gracefully.
      - `tests/test_wiki_ingest.py` — write a fake SEC + macro file, assert routing,
        assert frontmatter is valid YAML, assert stale banner is added by `lint_wiki`.
      - `tests/test_wiki.py` — stub `call_gemini`, run `ingest_to_wiki`, assert the file
        is actually written to disk (catches the duplicate-def bug from P0).
- [ ] **Add a `scripts/run_data_fetch_once.py` one-shot harness** so we can test the full
      ingest pipeline without waiting 5 minutes between cycles. It should read the same
      settings, call every fetcher once, print a table of rows returned + bytes saved.

## P3 — Architecture / design questions to resolve (probe with the team before coding)

Each of these is intentionally phrased as a question because the "best" answer depends on
the user's future direction. Cursor should not silently pick one — flag the trade-off in the
commit message when a path is chosen.

1. **Is the wiki supposed to be the single source of truth, or a cache?** Right now it is
   *both* — SQLite stores raw snapshots and the wiki stores LLM-synthesised prose. If a
   wiki page disagrees with SQLite, which wins? Decide and write it into
   `ARCHITECTURE.md`. Alternative: make the wiki append-only (never overwrite), treat each
   ingest as a new timestamped snapshot, and run a periodic "compactor" to produce the
   human-readable view.
2. **Why rewrite every stock page on every 5-article batch?** The current prompt hands the
   whole page back to Gemini for rewriting even if nothing about the stock changed. That
   burns tokens and destroys the version history. Alternatives: (a) diff-based updates —
   ask Gemini only for the "What changed since last revision?" paragraph and append it;
   (b) only regenerate when sentiment class flips or price moves > X %.
3. **Do we still need SQLite at all?** If the wiki is canonical, SQLite is just a cache for
   the Streamlit UI. If we keep it, normalise — right now it has only three flat tables
   and no foreign keys (e.g. an `insight` does not link to the `market_snapshot` rows that
   justified it). Alternative: drop SQLite, read straight from raw JSON + wiki markdown in
   the UI.
4. **Why asyncio queues + single process, instead of a real broker?** For a personal project
   this is the right call, but the plan docs already mention Kafka. Decide now whether we
   will ever run the agents in separate containers — if yes, the queue abstraction in
   `core/queues.py` must become an interface, not a concrete `asyncio.Queue`.
5. **What is the unit of concurrency?** Currently there is one task per *agent*, but each
   agent does strictly sequential work inside (`for symbol in symbols: await fetch(...)`).
   That leaves all I/O latency on the table. Alternative: `asyncio.gather` each symbol's
   fetchers; rate-limit with a shared `asyncio.Semaphore`.
6. **Is Gemini 1.5-Flash still the right model?** `.env` currently hard-codes
   `gemini-2.5-flash`, while `README.md` and inline comments say `1.5-flash`. Either
   update everywhere to 2.5, or downgrade `.env` back to 1.5. Either way: one number,
   everywhere.
7. **Where does personalization live?** The README promises "personalized investment
   insights" but there is no user profile, no portfolio table, no holdings input. That is
   an entire feature surface — schedule it explicitly (portfolio ingest → watchlist →
   personalised `query_wiki` prompt).
8. **Is the LLM-Wiki actually easier to maintain than RAG?** Honest probe. Wiki gives
   compounding narrative; RAG gives source-anchored retrieval. We currently get neither:
   wiki pages have no verifiable citations back to the `news_articles` rows that produced
   them. Add a `[[AAPL-20260418-0930]]` wikilink per ingest that anchors the prose to the
   raw DB row.
9. **Is `sec-edgar-downloader` giving us anything `companyfacts` does not?** Facts cover
   XBRL line items (Revenue, Assets, EPS). Filings give risk-factor prose. If we want
   risk-factor prose, write a direct httpx fetcher for `/cgi-bin/browse-edgar?action=getcompany`
   and drop the heavy third-party dep.
10. **Does the Streamlit UI need to share a process with the agents?** Current
    `docker-compose.yml` runs them as two containers sharing a volume — good. But
    `ui/app.py` calls `from agents.storage_agent import get_latest_prices` which opens its
    own SQLAlchemy engine, racing with the agents. Move the read functions into
    `core/storage_queries.py` (no queue dependency) so the UI never imports an agent.

## P4 — Polish / hygiene

- [ ] **Unify config naming.** `RAW_DATA_DIR` and `DATA_RAW_DIR` are *both* defined in
      `core/settings.py` with the same default. Pick one (`RAW_DATA_DIR`) and delete the
      alias from the settings class and `.env.example`.
- [ ] **Unify SEC symbol list.** `SEC_COMPANY_TICKERS` and `YFINANCE_SYMBOLS` both exist —
      `ingest_agent.fetch_sec_data` uses `YFINANCE_SYMBOLS` anyway, so `SEC_COMPANY_TICKERS`
      is dead config. Delete it.
- [ ] **Rotate the Gemini API key.** `.env` checks a live key into a directory that is
      listed in `.gitignore` — OK for local but do verify `git log .env` is clean, and
      regenerate the key in AI Studio before pushing this repo anywhere public.
- [ ] **Add `mypy` and `ruff` to dev requirements**, plus a `pre-commit` config. One
      consistent style across `core/fetchers.py` (double-quoted f-strings + trailing
      commas) would have caught several of the P0 bugs.
- [ ] **Surface lint/health in the UI.** Streamlit should render `lint_wiki()` results so
      stale pages are obvious without opening log files.
- [ ] **Write an `AGENTS.md`** (root-level rules file that Cursor auto-loads) enumerating:
      "always read this file before editing the wiki pipeline"; "never add new Python
      dependencies without updating `requirements.txt`"; "the canonical plan is
      `docs/ARCHITECTURE.md`, not the v2/v3 plan docs".

---

## Progress snapshot (what *is* working today)

- [x] Async multi-agent skeleton: `main.py` launches 3 asyncio tasks with a shared queue bus.
- [x] Settings layer (`core/settings.py`) loads `.env` + environment, single source of truth.
- [x] SQLAlchemy ORM (`core/models.py`) creates `market_snapshots`, `news_articles`,
      `insights` tables on startup.
- [x] LLM-Wiki skeleton: `ingest_to_wiki`, `query_wiki`, `lint_wiki` with YAML frontmatter
      and TTL-based staleness (design is sound; implementation has the duplicate-function
      bug flagged in P0).
- [x] Working SEC EDGAR `companyfacts` client with rate limiting + retry.
- [x] Working Google News RSS fetcher (per symbol, 20 articles each).
- [x] TextBlob sentiment pipeline wired into the analysis agent.
- [x] Streamlit UI shell that reads from the three SQLite tables.
- [x] Docker + docker-compose scaffolding (post-fix: remove the `sentence_transformers`
      download step from the Dockerfile).

---

## How to use this document

1. Pick the *top unchecked* item in the highest-priority section you are authorised to
   touch.
2. Open the file referenced, make the change, re-run the relevant test (or add one).
3. Check the item off with `[x]` and append a one-line note under it explaining *what* was
   done and *why* that approach was chosen over the alternatives listed.
4. If a change invalidates another item on the list, update it in the same commit.
