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
| --- | --- |
| **Ingest Agent** | Fetches stock prices (yfinance) and news (RSS/feedparser) on a schedule |
| **Analysis Agent** | Sentiment analysis (TextBlob) + RAG retrieval (ChromaDB) + Gemini LLM |
| **Storage Agent** | Persists insights to SQLite; serves data to the UI |

## Tech Stack

| Layer | Tool | Why |
| --- | --- | --- |
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
python3 -m venv .venv && source .venv/activate
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

## Legacy folders

Directories such as `api/`, `db/models/` (old ORM), `frontend/`, `rag/`, and `alembic/versions/` are kept from an earlier skeleton; their Python modules are stubbed with `DEPRECATED in v2` notes pointing to the v2 layout above. See `multi-agent-finance-cursor-plan-v2.md`.
