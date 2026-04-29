# AGENTS.md — Developer & Agent Reference

## Project Summary

Multi-agent AI investment advisor for Indian retail investors, with a parallel global (US)
market track. Built on a free-tier-only stack (Gemini, yfinance, AMFI, RBI, SQLite) with
an LLM-maintained dual wiki, a Trust Layer for source provenance, and a UserProfile
personalisation layer for India-first advice.

---

## Key Directories

| Path | Purpose |
| --- | --- |
| `core/` | Domain logic: models, settings, trust layer, fetchers, wiki engines |
| `agents/` | Three long-running async agents: ingest, analysis, storage |
| `ui/` | Streamlit dashboard (`app.py`) — runs on port 8501 |
| `data/wiki_india/` | **Primary** knowledge base — Indian instruments, SIP, ELSS, NPS, RBI |
| `data/wiki/` | Secondary knowledge base — Global / US market pages |
| `tests/` | Pytest suite; all tests are offline (mock transports, SQLite `:memory:`) |

---

## Primary Wiki

- **India (primary):** `data/wiki_india/` — NSE stocks, mutual funds, RBI macro, tax, concepts
- **Global (secondary):** `data/wiki/` — US equities, FRED macro, SEC filings, concepts

Both wikis use identical code paths; `WIKI_DIR` is injected at call time.
The India wiki is the thesis deliverable; the global wiki is a parallel track for comparison.

---

## Before Every Commit

```bash
# Run the full test suite (must pass, no failures)
pytest tests/ -q

# Lint and type-check
ruff check . && mypy core agents ui
```

All three commands must exit cleanly before opening a PR.

---

## Test Count

**Baseline:** 92 tests + India-specific tests across `tests/`.
Tests never touch the live network — all HTTP calls use `httpx.MockTransport` or
`unittest.mock`. The SQLite test database is always `:memory:`.

---

## Linting & Type Checking

```bash
ruff check .          # fast linter (replaces flake8 + isort + pyupgrade)
mypy core agents ui   # strict type checking on the three main packages
```

Fix all `ruff` errors before committing. `mypy` errors in new code must also be resolved;
pre-existing ignores are tracked in `pyproject.toml`.

---

## Architecture Quick Reference

- **Three-agent pipeline:** Ingest → Analysis → Storage, communicating via `asyncio.Queue`
- **Trust Layer:** `core/trust.py` — `source_registry` + `knowledge_versions` SQLite tables
- **Personalisation:** `UserProfile` ORM model; injected into every India advisor Gemini prompt
- **Confidence scoring:** 0.30–1.00 computed from staleness, source diversity, recency
- **Dual wiki:** `data/wiki_india/` (primary) · `data/wiki/` (global) — independent TTL/lint cycles
- **UI tabs:** Dashboard · 🇮🇳 India Advisor · 🔍 Sources & History · System Health

Full design details: `docs/ARCHITECTURE.md`
