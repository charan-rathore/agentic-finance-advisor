"""
core/wiki.py

LLM Wiki Knowledge Base — Karpathy Pattern (April 2026)

This module manages a persistent, compounding markdown wiki under data/wiki/.
Instead of re-embedding raw text (RAG), Gemini incrementally writes and maintains
structured wiki pages. Knowledge is compiled once, updated on every ingest, and
read at query time — eliminating redundant re-derivation.

Wiki layout:
  data/wiki/
    index.md         — catalog of all pages (LLM reads this first on any query)
    log.md           — append-only operation log (ingest, query, lint events)
    overview.md      — rolling synthesis: overall market picture, key themes
    stocks/
      AAPL.md        — entity page: price history, news summary, sentiment trend
      MSFT.md
      ...
    concepts/
      tech_sector.md — concept page: cross-stock theme synthesis
      market_risk.md
      ...
    insights/
      YYYY-MM-DD_HH-MM.md  — filed insights (good answers compound the wiki)

Operations:
  ingest_to_wiki(articles, prices) — LLM updates wiki from new data
  query_wiki(question)             — LLM reads index + relevant pages, answers
  lint_wiki()                      — LLM health-checks wiki for contradictions/orphans
"""

import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

from core.settings import settings
from core.company_intelligence import get_enhanced_context_for_symbol


# ── Wiki directory helpers ────────────────────────────────────────────────────

def _wiki_path(*parts: str) -> Path:
    """Return a Path inside the wiki directory, creating parent dirs as needed."""
    p = Path(settings.WIKI_DIR).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_wiki_file(rel_path: str) -> str:
    """Read a wiki file. Returns empty string if the file doesn't exist yet."""
    p = _wiki_path(rel_path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _write_wiki_file(rel_path: str, content: str) -> None:
    """Write (overwrite) a wiki file."""
    p = _wiki_path(rel_path)
    p.write_text(content, encoding="utf-8")
    logger.debug(f"[Wiki] Wrote {rel_path} ({len(content)} chars)")


def _append_log(entry: str) -> None:
    """Append a timestamped entry to log.md (append-only operation journal)."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log_path = _wiki_path("log.md")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n## [{timestamp}] {entry}\n")


def list_wiki_pages() -> list[str]:
    """Return all .md file paths relative to wiki root."""
    root = Path(settings.WIKI_DIR)
    if not root.exists():
        return []
    return [str(p.relative_to(root)) for p in root.rglob("*.md")]


# ── Gemini call with retry ────────────────────────────────────────────────────
# (Imported by analysis_agent — also used here for wiki maintenance calls)

import google.generativeai as genai

_gemini = None

def _get_gemini_model():
    """Lazy initialization of Gemini model."""
    global _gemini
    if _gemini is None:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini = genai.GenerativeModel(settings.GEMINI_MODEL)
    return _gemini


@retry(
    stop=stop_after_attempt(settings.GEMINI_RETRY_MAX),
    wait=wait_exponential(multiplier=settings.GEMINI_RETRY_BACKOFF_BASE, min=2, max=60),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _call_gemini_sync(prompt: str) -> str:
    return _get_gemini_model().generate_content(prompt).text


async def call_gemini(prompt: str) -> str:
    """Async wrapper for the sync Gemini call."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_gemini_sync, prompt)


# ── Operation 1: Ingest → Wiki update ────────────────────────────────────────

async def ingest_to_wiki(articles: list[dict], prices: list[dict]) -> None:
    """
    Core wiki operation: LLM reads new articles/prices and updates wiki pages.

    For each symbol mentioned in the batch, Gemini updates that symbol's entity page.
    It also updates the overview.md synthesis and the index.md catalog.
    A log entry records what happened.

    This is the 'compile once' step — knowledge is structured here so that
    query_wiki() can read pre-synthesized pages instead of raw chunks.
    """
    if not articles and not prices:
        return

    logger.info(f"[Wiki] Ingesting {len(articles)} articles, {len(prices)} prices...")

    # ── Step 1: Update per-symbol entity pages ────────────────────────────────
    # Group articles by mentioned symbols
    symbols = [p["symbol"] for p in prices]
    articles_text = "\n".join(
        f"- [{a.get('source','')}] {a['headline']}: {a.get('body','')[:200]}"
        for a in articles[:20]
    )
    prices_text = "\n".join(
        f"- {p['symbol']}: ${p['price']:.2f} (vol: {p.get('volume','?')})"
        for p in prices
    )

    for symbol in symbols[:5]:  # cap at 5 per cycle to respect rate limits
        existing_page = _read_wiki_file(f"stocks/{symbol}.md")
        company_context = get_enhanced_context_for_symbol(symbol)
        
        prompt = f"""You are maintaining a financial knowledge base wiki.
Update the wiki page for stock symbol {symbol}.

EXISTING PAGE CONTENT (may be empty if this is the first time):
{existing_page or '(new page — create it)'}

NEW DATA TO INTEGRATE:
Current prices (with timestamps):
{prices_text}

Recent news articles:
{articles_text}

{company_context}

CRITICAL INSTRUCTIONS:
- Write a complete updated markdown page for {symbol}
- Include sections: ## Summary, ## Recent Price Action, ## News & Sentiment, ## Key Risks, ## Cross-References
- PRICE ACCURACY: Only use exact prices from NEW DATA above with proper timestamps. If no current price data, state "Price data pending next market update"
- RISK ANALYSIS: Always include specific, material risks for this company based on known industry/company context (litigation, competition, regulatory, market risks)
- CROSS-REFERENCES: Use sophisticated financial concepts like [[Sector Rotation]], [[Dividend Aristocrats]], [[Patent Cliff Risk]], [[Litigation Exposure]] rather than generic terms
- FACTUAL GROUNDING: Do NOT invent specific numbers. Use phrases like "recent trading near" or "approximately" for estimates
- Keep under 400 words but be substantive
- End with `> Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}` with exact timestamp

WRITE THE COMPLETE PAGE NOW (markdown only, no preamble):"""

        page_content = await call_gemini(prompt)
        _write_wiki_file(f"stocks/{symbol}.md", page_content)
        logger.info(f"[Wiki] Updated stocks/{symbol}.md")

    # ── Step 2: Update overview synthesis ────────────────────────────────────
    existing_overview = _read_wiki_file("overview.md")
    prompt = f"""You are maintaining a financial knowledge base wiki.
Update the market overview synthesis page.

EXISTING OVERVIEW:
{existing_overview or '(new — create it)'}

NEW DATA THIS CYCLE:
Prices: {prices_text}
Articles: {articles_text}

Write a concise updated overview (under 300 words) covering:
## Market Overview
## Key Themes This Cycle
## Stocks to Watch
## Risk Signals

Be factual, cite specific prices/headlines. Use [[wikilink]] to reference stock pages.
End with `> Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`

WRITE THE OVERVIEW NOW (markdown only):"""

    overview = await call_gemini(prompt)
    _write_wiki_file("overview.md", overview)

    # ── Step 3: Rebuild index.md catalog ─────────────────────────────────────
    all_pages = list_wiki_pages()
    index_lines = ["# Wiki Index\n", f"> {len(all_pages)} pages | "
                   f"Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"]
    index_lines.append("## Stock Pages\n")
    for page in sorted(p for p in all_pages if p.startswith("stocks/")):
        symbol = page.replace("stocks/", "").replace(".md", "")
        index_lines.append(f"- [[{symbol}]] → `{page}`\n")
    index_lines.append("\n## Concept Pages\n")
    for page in sorted(p for p in all_pages if p.startswith("concepts/")):
        index_lines.append(f"- `{page}`\n")
    index_lines.append("\n## Insights Archive\n")
    for page in sorted(p for p in all_pages if p.startswith("insights/")):
        index_lines.append(f"- `{page}`\n")
    _write_wiki_file("index.md", "".join(index_lines))

    # ── Step 4: Log the ingest event ─────────────────────────────────────────
    _append_log(
        f"ingest | {len(articles)} articles, {len(prices)} prices | "
        f"updated: {', '.join(symbols[:5])}"
    )
    logger.info("[Wiki] Ingest complete.")


# ── Operation 2: Query the wiki ───────────────────────────────────────────────

async def query_wiki(question: str) -> tuple[str, list[str]]:
    """
    Answer a question using the wiki.

    The LLM reads index.md first (the catalog), identifies relevant pages,
    reads those pages, then synthesizes an answer. This mirrors how a human
    would use a good wiki — check the index, read the relevant entries, answer.

    Returns (answer_text, list_of_pages_consulted).

    Good answers are automatically filed back into the wiki as insights/ pages,
    so your explorations compound the knowledge base just like ingested data does.
    """
    index_content = _read_wiki_file("index.md")
    overview_content = _read_wiki_file("overview.md")

    if not index_content:
        return (
            "The wiki is still being built — no pages available yet. "
            "Wait for the first ingest cycle to complete.",
            [],
        )

    # ── Step 1: LLM reads index to find relevant pages ────────────────────────
    routing_prompt = f"""You are a financial wiki assistant.
A user has asked: "{question}"

Here is the wiki index (catalog of all pages):
{index_content}

List the 3-5 most relevant page paths to read for answering this question.
Reply with ONLY a newline-separated list of file paths (e.g. stocks/AAPL.md).
No other text."""

    routing_response = await call_gemini(routing_prompt)
    relevant_paths = [
        line.strip() for line in routing_response.strip().splitlines()
        if line.strip() and line.strip().endswith(".md")
    ]

    # ── Step 2: Read those pages ─────────────────────────────────────────────
    pages_context = ""
    consulted = []
    for path in relevant_paths[:5]:
        content = _read_wiki_file(path)
        if content:
            pages_context += f"\n\n### From `{path}`:\n{content}"
            consulted.append(path)

    # Always include overview for context
    if overview_content and "overview.md" not in consulted:
        pages_context = f"\n\n### From `overview.md`:\n{overview_content}" + pages_context
        consulted.insert(0, "overview.md")

    # ── Step 3: Generate the answer from pre-compiled wiki content ────────────
    answer_prompt = f"""You are a concise, data-driven personal finance AI assistant.
Answer the question below using ONLY the wiki content provided.
Do not invent data. Be specific — cite prices, dates, and headlines from the wiki.

QUESTION: {question}

WIKI CONTENT:
{pages_context}

Instructions:
- Answer in 3–4 paragraphs maximum
- Reference specific data points from the wiki (prices, sentiment, trends)
- Be balanced — do not over-promise returns
- End with a one-sentence risk disclaimer
- This is for educational purposes only

YOUR RESPONSE:"""

    answer = await call_gemini(answer_prompt)

    # ── Step 4: File the insight back into the wiki ───────────────────────────
    # Good answers compound the knowledge base — they don't disappear into chat
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    insight_page = f"# Insight: {question[:80]}\n\n{answer}\n\n" \
                   f"---\n*Sources consulted: {', '.join(consulted)}*\n" \
                   f"*Generated: {timestamp} UTC*\n"
    _write_wiki_file(f"insights/{timestamp}.md", insight_page)
    _append_log(f"query | \"{question[:60]}...\" | consulted: {', '.join(consulted)}")

    return answer, consulted


# ── Operation 3: Lint the wiki ────────────────────────────────────────────────

async def lint_wiki() -> str:
    """
    Periodic wiki health-check. Gemini reviews the wiki for:
    - Contradictions between pages (e.g. conflicting price narratives)
    - Stale claims superseded by newer data
    - Orphan pages with no inbound links
    - Important entities without their own page
    - Missing cross-references

    Returns a summary of the lint report, also filed as a wiki page.
    This keeps the wiki healthy as it grows and is a great story for interviews:
    'The system self-audits its own knowledge base periodically.'
    """
    index_content = _read_wiki_file("index.md")
    log_tail = _read_wiki_file("log.md")[-2000:]  # last ~2000 chars of log

    prompt = f"""You are auditing a financial knowledge base wiki.

WIKI INDEX:
{index_content}

RECENT LOG (last operations):
{log_tail}

Perform a health check and report:
1. **Potential contradictions** — pages that may conflict with each other
2. **Stale pages** — pages likely to have outdated info (older than 1 day)
3. **Orphan pages** — pages with no inbound links from other pages
4. **Missing pages** — important entities/concepts mentioned but lacking their own page
5. **Suggested next ingests** — what data would most improve the wiki right now?

Be specific. Reference page names. Keep the report under 300 words.

LINT REPORT:"""

    report = await call_gemini(prompt)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    _write_wiki_file(f"insights/lint_{timestamp}.md", f"# Wiki Lint Report\n\n{report}\n")
    _append_log(f"lint | health-check complete")
    logger.info("[Wiki] Lint complete.")
    return report