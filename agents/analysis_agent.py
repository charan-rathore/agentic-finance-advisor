"""
agents/analysis_agent.py

Agent 2: Analysis (Sentiment + RAG + Gemini LLM)

Responsibility: consume raw data, enrich it with sentiment and retrieved
context, call Gemini to generate insights, put results on insights_queue.

Tools used:
  TextBlob      — sentiment analysis, free, runs offline, no API cost
  ChromaDB      — local vector database, free, runs on disk
  sentence-transformers/all-MiniLM-L6-v2
                — embedding model, free, ~80MB download once, then offline
  Gemini 1.5 Flash
                — LLM, FREE TIER (15 req/min, 1M tokens/day)
                  Key from: https://aistudio.google.com/ (no credit card)

Queues consumed:  raw_market_queue, raw_news_queue
Queues produced:  insights_queue
"""

import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone

import chromadb
import google.generativeai as genai
from chromadb.utils import embedding_functions
from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from textblob import TextBlob

from core.queues import insights_queue, raw_market_queue, raw_news_queue
from core.settings import settings

# ── Gemini setup ──────────────────────────────────────────────────────────────
genai.configure(api_key=settings.GEMINI_API_KEY)
_gemini = genai.GenerativeModel(settings.GEMINI_MODEL)

# ── ChromaDB setup ────────────────────────────────────────────────────────────
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
_chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
_news_collection = _chroma_client.get_or_create_collection(
    name="financial_news",
    embedding_function=_embed_fn,
    metadata={"hnsw:space": "cosine"},
)


def analyze_sentiment(text: str) -> tuple[str, float]:
    """
    Classify text sentiment using TextBlob.
    TextBlob is free, open-source, and runs completely offline.
    Returns (label, score) where score is -1.0 (negative) to +1.0 (positive).
    """
    score = TextBlob(text).sentiment.polarity
    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"
    return label, round(score, 4)


def embed_article(article: dict) -> None:
    """Store a news article in the local ChromaDB vector store."""
    doc_id = f"news_{abs(hash(article['headline']))}"
    text = article["headline"] + " " + article.get("body", "")
    _news_collection.upsert(
        documents=[text],
        metadatas=[
            {
                "headline": article["headline"][:200],
                "source": article.get("source", ""),
                "url": article.get("url", ""),
            }
        ],
        ids=[doc_id],
    )


def retrieve_context(query: str, n: int = 4) -> list[dict]:
    """
    Find the most relevant stored articles for a query.
    Returns a list of dicts with text, source, url, and similarity score.
    """
    count = _news_collection.count()
    if count == 0:
        return []

    results = _news_collection.query(
        query_texts=[query],
        n_results=min(n, count),
    )
    docs: list[dict] = []
    if results and results["documents"]:
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            docs.append(
                {
                    "text": text[:300],
                    "source": meta.get("source", "") if meta else "",
                    "url": meta.get("url", "") if meta else "",
                    "score": round(1 - dist, 3),
                }
            )
    return docs


@retry(
    stop=stop_after_attempt(settings.GEMINI_RETRY_MAX),
    wait=wait_exponential(
        multiplier=settings.GEMINI_RETRY_BACKOFF_BASE,
        min=2,
        max=60,
    ),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _call_gemini_sync(prompt: str) -> str:
    """
    Call Gemini 1.5 Flash (free tier) with automatic retry on rate limits.
    tenacity retries up to GEMINI_RETRY_MAX times with exponential backoff.
    """
    response = _gemini.generate_content(prompt)
    return response.text


async def call_gemini(prompt: str) -> str:
    """Async wrapper — runs the sync Gemini call in a thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_gemini_sync, prompt)


def build_prompt(
    query: str,
    market_data: list[dict],
    sentiment_items: list[dict],
    rag_docs: list[dict],
) -> str:
    """Assemble the Gemini prompt from all available signals."""
    market_text = (
        "\n".join(f"  {d['symbol']}: ${d['price']:.2f}" for d in market_data[:10])
        or "  No market data available yet."
    )

    sentiment_text = (
        "\n".join(
            f"  [{s['label'].upper()} {s['score']:+.2f}] {s['headline'][:100]}"
            for s in sentiment_items[:6]
        )
        or "  No sentiment data available yet."
    )

    context_text = (
        "\n".join(
            f"  (relevance {d['score']:.2f}) {d['text'][:200]}" for d in rag_docs[:3]
        )
        or "  No retrieved context available yet."
    )

    return f"""You are a concise, data-driven personal finance AI assistant.
Answer the question below using ONLY the data provided. Do not invent data.

QUESTION: {query}

CURRENT STOCK PRICES:
{market_text}

RECENT NEWS WITH SENTIMENT:
{sentiment_text}

RELEVANT CONTEXT FROM KNOWLEDGE BASE:
{context_text}

Instructions:
- Answer in 3–4 paragraphs maximum
- Reference specific data points (prices, sentiment scores) where relevant
- Be balanced — do not over-promise returns
- End with a one-sentence risk disclaimer
- This is for educational purposes only

YOUR RESPONSE:"""


async def run() -> None:
    """
    Main analysis loop. Drains both input queues, then every
    ANALYSIS_INTERVAL_SECONDS generates a Gemini insight from accumulated data.
    """
    logger.info("[Analysis Agent] Starting...")

    market_buffer: deque = deque(maxlen=50)
    news_buffer: deque = deque(maxlen=100)
    sentiment_buffer: deque = deque(maxlen=100)

    last_analysis: float = 0.0

    while True:
        drained_market = 0
        while not raw_market_queue.empty():
            item = await raw_market_queue.get()
            market_buffer.append(item)
            drained_market += 1
        if drained_market:
            logger.info(f"[Analysis Agent] Drained {drained_market} market items")

        drained_news = 0
        while not raw_news_queue.empty():
            article = await raw_news_queue.get()
            news_buffer.append(article)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, embed_article, article)

            label, score = analyze_sentiment(
                article["headline"] + " " + article.get("body", "")
            )
            sentiment_buffer.append(
                {
                    "headline": article["headline"],
                    "label": label,
                    "score": score,
                }
            )
            drained_news += 1

        if drained_news:
            logger.info(f"[Analysis Agent] Processed {drained_news} news articles")

        now = time.time()
        if now - last_analysis < settings.ANALYSIS_INTERVAL_SECONDS:
            await asyncio.sleep(10)
            continue

        if not market_buffer and not news_buffer:
            logger.info("[Analysis Agent] No data yet, waiting for ingest agent...")
            await asyncio.sleep(30)
            continue

        logger.info("[Analysis Agent] Running Gemini analysis...")

        query = (
            "Based on the current stock prices and recent financial news, "
            "what is the overall market outlook and are there any notable "
            "opportunities or risks for a retail investor to be aware of?"
        )

        rag_docs = await asyncio.get_event_loop().run_in_executor(
            None, retrieve_context, query
        )

        prompt = build_prompt(
            query,
            list(market_buffer),
            list(sentiment_buffer),
            rag_docs,
        )

        try:
            insight_text = await call_gemini(prompt)
            logger.info(f"[Analysis Agent] Insight generated ({len(insight_text)} chars)")
        except Exception as e:
            logger.error(f"[Analysis Agent] Gemini failed after retries: {e}")
            last_analysis = now
            continue

        pos = sum(1 for s in sentiment_buffer if s["label"] == "positive")
        neg = sum(1 for s in sentiment_buffer if s["label"] == "negative")
        neu = sum(1 for s in sentiment_buffer if s["label"] == "neutral")
        sentiment_summary = f"{pos} positive, {neg} negative, {neu} neutral headlines"

        insight_msg = {
            "user_query": query,
            "insight_text": insight_text,
            "sentiment_summary": sentiment_summary,
            "sources": json.dumps([d.get("url", "") for d in rag_docs if d.get("url")]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await insights_queue.put(insight_msg)
        logger.info("[Analysis Agent] Insight put on insights_queue")
        last_analysis = now
