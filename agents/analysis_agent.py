"""
agents/analysis_agent.py

Agent 2: Analysis (Sentiment + LLM Wiki Knowledge Base + Gemini LLM)

Responsibility: consume raw data from queues, maintain the LLM Wiki knowledge
base, generate insights by querying the wiki, put results on insights_queue.

This agent replaces the old RAG (ChromaDB) pattern with the LLM Wiki pattern
(Karpathy, April 2026). Instead of embedding chunks and searching vectors at
query time, Gemini incrementally compiles incoming data into a persistent,
interlinked markdown wiki under data/wiki/. Queries read pre-compiled pages.

Tools used:
  TextBlob      — sentiment analysis, free, offline
  core/wiki.py  — LLM Wiki knowledge base (plain markdown files, Gemini writes them)
  Gemini 1.5 Flash — FREE TIER (15 req/min, 1M tokens/day)

Queues consumed:  raw_market_queue, raw_news_queue
Queues produced:  insights_queue
"""

import asyncio
import json
import time
from collections import deque
from datetime import UTC, datetime

from loguru import logger
from textblob import TextBlob

from core.fetchers import fetch_google_news_rss
from core.queues import insights_queue, raw_india_queue, raw_market_queue, raw_news_queue
from core.settings import settings
from core.wiki import ingest_to_wiki, lint_wiki, query_wiki
from core.wiki_india import ingest_india
from core.wiki_ingest import process_all_new_raw_files

# ── Sentiment ─────────────────────────────────────────────────────────────────


def analyze_sentiment(text: str) -> tuple[str, float]:
    """
    TextBlob sentiment: free, offline, no API.
    Returns (label, score) where score is -1.0 to +1.0.
    """
    score = TextBlob(text).sentiment.polarity
    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"
    return label, round(score, 4)


# ── Prompt builder (kept for unit tests and ad-hoc Gemini calls) ──────────────


def build_prompt(
    question: str,
    prices: list[dict],
    articles: list[dict],
    sentiment_rows: list[dict],
) -> str:
    """
    Build a Gemini prompt that bundles a user question with the latest context.

    v2 used this as the primary analysis path. v3 prefers `query_wiki` because
    the wiki already contains pre-synthesised context, but this helper is kept
    for two reasons: (1) unit tests assert it embeds the question and a
    `CURRENT STOCK PRICES:` section; (2) it gives us a direct-context fallback
    when the wiki is empty (very first run, or after a wipe).
    """
    price_lines = (
        "\n".join(
            f"- {p.get('symbol','?')}: ${p.get('price','?')} (vol: {p.get('volume','?')})"
            for p in prices
        )
        or "(no recent prices)"
    )

    headline_lines = (
        "\n".join(f"- [{a.get('source','')}] {a.get('headline','')}" for a in articles[:20])
        or "(no recent articles)"
    )

    sentiment_lines = (
        "\n".join(
            f"- {s.get('sentiment_label','?')} ({s.get('sentiment_score','?')}): "
            f"{s.get('headline','')}"
            for s in sentiment_rows[:20]
        )
        or "(no sentiment yet)"
    )

    return (
        "You are a concise, data-driven personal finance AI assistant.\n"
        "Answer the user's question using ONLY the context below. Cite specific\n"
        "prices, headlines or sentiment signals you rely on. End with a one-line\n"
        "risk disclaimer.\n\n"
        f"USER QUESTION: {question}\n\n"
        f"CURRENT STOCK PRICES:\n{price_lines}\n\n"
        f"RECENT HEADLINES:\n{headline_lines}\n\n"
        f"SENTIMENT SIGNAL:\n{sentiment_lines}\n\n"
        "YOUR RESPONSE:"
    )


# ── Main agent loop ───────────────────────────────────────────────────────────


async def run() -> None:
    """
    Main analysis loop.

    Every ANALYSIS_INTERVAL_SECONDS:
      1. Drain queues and run sentiment on news
      2. Batch-ingest new data into the LLM Wiki (Gemini updates wiki pages)
      3. Query the wiki with a market outlook question
      4. Put the insight on insights_queue for storage agent

    Every WIKI_LINT_INTERVAL_HOURS:
      5. Run wiki lint (Gemini health-checks the knowledge base)
    """
    logger.info("[Analysis Agent] Starting (LLM Wiki mode)...")

    market_buffer: deque = deque(maxlen=50)
    news_buffer: deque = deque(maxlen=100)
    sentiment_buffer: deque = deque(maxlen=100)

    # ── India buffers — accumulate across cycles, flushed into ingest_india() ─
    india_prices_buf: list[dict] = []
    india_nav_buf: list[dict] = []
    india_rbi_buf: dict | None = None
    india_news_buf: list[dict] = []

    last_analysis: float = 0.0
    last_lint: float = 0.0
    lint_interval_seconds = float(getattr(settings, "WIKI_LINT_INTERVAL_HOURS", 6)) * 3600
    ingest_batch_size = int(getattr(settings, "WIKI_INGEST_EVERY_N_ARTICLES", 5))

    while True:
        # ── Drain market queue ────────────────────────────────────────────────
        while not raw_market_queue.empty():
            item = await raw_market_queue.get()
            market_buffer.append(item)

        # ── Drain news queue + sentiment ──────────────────────────────────────
        new_articles: list[dict] = []
        while not raw_news_queue.empty():
            article = await raw_news_queue.get()
            news_buffer.append(article)
            label, score = analyze_sentiment(article["headline"] + " " + article.get("body", ""))
            enriched = {**article, "sentiment_label": label, "sentiment_score": score}
            sentiment_buffer.append(enriched)
            new_articles.append(enriched)

        # ── Drain India queue into local buffers ──────────────────────────────
        while not raw_india_queue.empty():
            msg = await raw_india_queue.get()
            msg_type = msg.get("type", "")
            if msg_type == "india_cycle":
                india_prices_buf.extend(msg.get("prices", []))
                india_news_buf.extend(msg.get("news_batches", []))
            elif msg_type == "india_nav":
                india_nav_buf.extend(msg.get("nav_records", []))
            elif msg_type == "india_rbi":
                # Always keep the most recent RBI snapshot
                india_rbi_buf = msg.get("rbi_rates")

        # ── Flush India buffers into wiki when we have any data ───────────────
        if india_prices_buf or india_nav_buf or india_rbi_buf or india_news_buf:
            logger.info(
                f"[Analysis Agent] Triggering India wiki ingest "
                f"({len(india_prices_buf)} prices, {len(india_nav_buf)} NAVs, "
                f"rbi={'yes' if india_rbi_buf else 'no'}, "
                f"{len(india_news_buf)} news batches)..."
            )
            try:
                await ingest_india(
                    prices=list(india_prices_buf),
                    nav_records=list(india_nav_buf),
                    rbi_rates=india_rbi_buf,
                    news_batches=list(india_news_buf),
                )
                # Clear buffers only after a successful ingest
                india_prices_buf.clear()
                india_nav_buf.clear()
                india_rbi_buf = None
                india_news_buf.clear()
            except Exception as e:
                logger.error(f"[Analysis Agent] India wiki ingest failed: {e}")
                # Do NOT clear buffers — retry on next cycle

        # ── Ingest batch into wiki when we have enough new articles ───────────
        if len(new_articles) >= ingest_batch_size:
            logger.info(
                f"[Analysis Agent] Triggering wiki ingest "
                f"({len(new_articles)} articles, {len(market_buffer)} prices)..."
            )
            await ingest_to_wiki(new_articles, list(market_buffer))

        # ── Check if it's time for a Gemini insight query ─────────────────────
        now = time.time()
        if now - last_analysis < settings.ANALYSIS_INTERVAL_SECONDS:
            await asyncio.sleep(10)
            continue

        if not market_buffer and not news_buffer:
            logger.info("[Analysis Agent] No data yet, waiting for ingest agent...")
            await asyncio.sleep(30)
            continue

        # Ensure wiki is up to date before querying
        if new_articles:
            await ingest_to_wiki(new_articles, list(market_buffer))

        logger.info("[Analysis Agent] Querying wiki for market insight...")

        question = (
            "Based on the current stock prices and recent financial news, "
            "what is the overall market outlook and are there any notable "
            "opportunities or risks for a retail investor to be aware of?"
        )

        insight_text, pages_consulted = await query_wiki(question)

        # Build sentiment summary for storage
        pos = sum(1 for s in sentiment_buffer if s.get("sentiment_label") == "positive")
        neg = sum(1 for s in sentiment_buffer if s.get("sentiment_label") == "negative")
        neu = sum(1 for s in sentiment_buffer if s.get("sentiment_label") == "neutral")
        sentiment_summary = f"{pos} positive, {neg} negative, {neu} neutral headlines"

        insight_msg = {
            "user_query": question,
            "insight_text": insight_text,
            "sentiment_summary": sentiment_summary,
            "sources": json.dumps(pages_consulted),  # wiki pages consulted
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await insights_queue.put(insight_msg)
        logger.info(f"[Analysis Agent] Insight generated from {len(pages_consulted)} wiki pages")
        last_analysis = now

        # ── Process whatever the ingest agent already fetched ──────────────────
        # Extended fetchers (SEC, macro, Alpha Vantage, Finnhub, Reddit, earnings,
        # market sentiment) live on the ingest agent with per-source cadences now
        # — running them on every 10-minute analysis cycle re-downloaded 7 MB SEC
        # blobs 144×/day. Here we just scan data/raw/ and feed new payloads into
        # the wiki.
        try:
            processed_count = await process_all_new_raw_files()
            logger.info(f"[Analysis Agent] Processed {processed_count} new raw data files")
        except Exception as e:
            logger.error(f"[Analysis Agent] Error processing raw files into wiki: {e}")

        # ── Periodic wiki lint ────────────────────────────────────────────────
        if now - last_lint > lint_interval_seconds:
            logger.info("[Analysis Agent] Running wiki lint...")
            lint_results = await lint_wiki()

            # Check for symbols that need refresh
            needs_refresh = lint_results.get("needs_refresh", [])
            if needs_refresh:
                logger.info(f"[Analysis Agent] Refreshing stale data for: {needs_refresh}")
                # Trigger targeted refresh for stale symbols
                stale_symbols = [
                    item for item in needs_refresh if len(item) <= 5 and item.isupper()
                ]
                if stale_symbols:
                    await fetch_google_news_rss(stale_symbols)
                    await process_all_new_raw_files()

            last_lint = now

        await asyncio.sleep(10)
