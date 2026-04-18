# Legacy modules (reference-only — DO NOT import from live code)

Everything under `legacy/` is carry-over from an earlier skeleton of this project
(v1 / pre-"v3 multi-agent" architecture). It is kept in tree so that historical
notes in `multi-agent-finance-cursor-plan-v2.md` / `v3.md` still resolve to
real files, but **no file in `core/`, `agents/`, `ui/`, `scripts/`, or `tests/`
should import from here**. The grep test is:

```bash
rg -n "from (legacy|agents\.(base|budget_agent|expense_agent|explanation_agent|fraud_agent|investment_agent|messaging|news_agent|orchestrator))\b"
```

That should return zero results against live code.

## What is here, and what replaced it

| Legacy path                         | Replaced by                                            | Why it's stubbed                                                           |
| ----------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------- |
| `legacy/agents/base.py`             | Plain async modules with a top-level `run()` coroutine | v2 dropped the `BaseAgent` class in favour of duck-typed async functions   |
| `legacy/agents/budget_agent.py`     | —                                                      | Out of scope for the investing advisor; budgeting was v1 personal-finance  |
| `legacy/agents/expense_agent.py`    | —                                                      | Same: v1 personal-finance surface, not part of v3                          |
| `legacy/agents/explanation_agent.py`| `agents/analysis_agent.py` + Gemini                    | LLM-authored narrative now lives inside the analysis agent                 |
| `legacy/agents/fraud_agent.py`      | —                                                      | Not a goal of v3                                                           |
| `legacy/agents/investment_agent.py` | `agents/analysis_agent.py`                             | Investment insight generation folded into the analysis agent               |
| `legacy/agents/messaging.py`        | `core/queues.py`                                       | Kafka was replaced with in-process `asyncio.Queue`                         |
| `legacy/agents/news_agent.py`       | `agents/ingest_agent.py`                               | News is now fetched alongside prices in a single ingest pass               |
| `legacy/agents/orchestrator.py`     | root `main.py`                                         | `asyncio.gather(ingest.run(), analysis.run(), storage.run())`              |
| `legacy/api/`                       | `app/main.py` (tiny health stub) + Streamlit UI        | FastAPI routing is not the primary UX; the v3 surface is the Streamlit app |
| `legacy/db/` (base, session, models)| `core/models.py`                                       | v3 uses a single SQLite file with 3 flat tables                            |
| `legacy/rag/vector_store.py`        | LLM-Wiki (`data/wiki/` + `core/wiki.py`)               | ChromaDB + sentence-transformers were removed in v3                        |
| `legacy/frontend/app.py`            | `ui/app.py`                                            | The dashboard moved to the new Streamlit entrypoint                        |
| `legacy/scripts/kafka_print_consumer.py` | —                                                 | There is no Kafka in v3                                                    |
| `legacy/alembic/` + `alembic.ini`   | —                                                      | SQLite schema is created in-place by `core.models.init_db`; no migrations  |

## Can I delete `legacy/` outright?

Yes — nothing in `core/`, `agents/{ingest,analysis,storage}_agent.py`,
`ui/app.py`, `main.py`, or the live tests depends on it. This folder exists so
that anyone reading the plan docs can still locate the files the docs refer to.
If you want to hard-delete, `rm -rf legacy/` is safe *provided* you are also
happy to let the plan-doc references go stale.
