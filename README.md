# Multi-agent AI personal finance advisor

Production-oriented skeleton for a **multi-agent** platform: budgeting, expense analysis, savings heuristics, investment education, fraud-style alerts, news sentiment hooks, RAG-backed explanations, CSV uploads, PostgreSQL persistence, Kafka events, Redis (cache/pub-sub ready), ChromaDB vectors, **Gemini** via Google AI Studio, **FastAPI** backend, and **Streamlit** dashboard.

## Layout

| Path | Role |
|------|------|
| `app/` | FastAPI application factory and ASGI entry |
| `api/` | Routers, dependencies, request/response schemas |
| `agents/` | Agent base types, orchestrator, Kafka publisher |
| `core/` | Settings (`pydantic-settings`), logging, Gemini helper |
| `db/` | SQLAlchemy models and session |
| `rag/` | ChromaDB vector helpers |
| `services/` | CSV ingestion and other app services |
| `frontend/` | Streamlit UI |
| `scripts/` | Dev utilities (e.g. Kafka debug consumer) |
| `tests/` | Pytest suite |
| `alembic/` | Database migrations |
| `data/raw`, `data/processed` | Local file drops (gitignored contents) |

## Prerequisites

- Python **3.9+** locally (Dockerfile uses **3.12**)
- Docker Desktop (or compatible engine) for compose stack
- [Google AI Studio](https://aistudio.google.com/) API key (optional for stubs)

## Quick start (local Python)

```bash
cd /path/to/starter-project
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set GEMINI_API_KEY if you use Gemini
```

Start infrastructure (Postgres, Redis, Kafka, Chroma) — from the same directory:

```bash
docker compose up -d postgres redis zookeeper kafka chroma
```

Run migrations:

```bash
alembic upgrade head
```

Run API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run Streamlit (second terminal, venv active):

```bash
streamlit run frontend/app.py
```

Open `http://localhost:8501` and `http://localhost:8000/docs`.

## Quick start (all services in Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: `http://localhost:8000`
- Streamlit: `http://localhost:8501` (preconfigured with `FASTAPI_BASE_URL=http://api:8000`)

Apply migrations inside the API container:

```bash
docker compose exec api alembic upgrade head
```

## Configuration

All settings are environment-driven; see `.env.example`. Key variables:

- `DATABASE_URL` — SQLAlchemy URL (default uses `psycopg2`)
- `REDIS_URL` — Redis for caching or Celery-style workloads
- `KAFKA_BOOTSTRAP_SERVERS` — `localhost:9092` on host, `kafka:29092` from the `api` container
- `CHROMA_HOST` / `CHROMA_PORT` — `localhost` + `8001` on host; `chroma` + `8000` inside Docker
- `GEMINI_API_KEY` / `GEMINI_MODEL` — Gemini access

## Kafka notes

- Topics default to `agent.events` and `finance.transactions` (see `.env.example`).
- If the broker is down, the API **logs and continues** (suitable for local dev).
- Debug consumer: `PYTHONPATH=. python scripts/kafka_print_consumer.py agent.events`

## Testing

```bash
source .venv/bin/activate
pytest
```

## GitHub remote

The repository is initialized locally. After you create an empty repo on GitHub:

```bash
git remote add origin https://github.com/<YOUR_USER>/<YOUR_REPO>.git
git branch -M main
git push -u origin main
```

Replace the URL with your SSH or HTTPS remote.

## Docker image

The `Dockerfile` installs dependencies and runs `uvicorn` by default. Override the command for workers, Streamlit, or one-off jobs (see `docker compose` services).

## Next implementation steps

1. Kafka **consumer worker** that calls `services.csv_ingest` and writes `TransactionRecord` rows.
2. **Gemini + RAG** in `FinancialExplanationAgent` using `rag.vector_store.query_similar`.
3. **Redis** caching for aggregated dashboards.
4. **Auth** (JWT / OAuth) and real `user_external_id` mapping.
5. **Fraud** scoring model and **news** API integration in respective agents.

## License

Add a `LICENSE` file for your organization; this template does not ship a default license.
