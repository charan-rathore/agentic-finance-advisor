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

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import google.generativeai as genai
import yaml
from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.company_intelligence import get_enhanced_context_for_symbol
from core.settings import settings

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


def _write_wiki_file(
    path: "str | Path",
    content: str,
    engine: object = None,
    change_summary: str = "wiki update",
    source_urls: "list[str] | None" = None,
    source_types: "list[str] | None" = None,
    triggered_by: str = "ingest",
) -> None:
    """Write (overwrite) a wiki file and optionally record a version entry.

    Backward-compatible: all existing callers that pass only ``(path, content)``
    keep working because every new parameter defaults to a safe no-op value.

    When ``engine`` is provided (PR 3+), ``core.trust.record_wiki_version`` is
    called after the write to log what changed, how many words moved, and which
    source URLs drove the update. The lazy import avoids a circular dependency
    since ``core.trust`` imports ``core.models`` but not ``core.wiki``.

    Accepts either a relative string path (resolved against WIKI_DIR) or an
    absolute Path. Writes are synchronous — markdown files are tiny and this
    avoids the trap of returning an un-awaited coroutine from a sync call site.
    """
    p = _wiki_path(path) if isinstance(path, str) else Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    old_content = p.read_text(encoding="utf-8") if p.exists() else ""
    p.write_text(content, encoding="utf-8")

    rel = str(path) if isinstance(path, str) else str(p.relative_to(Path(settings.WIKI_DIR)))
    logger.debug(f"[Wiki] Wrote {rel} ({len(content)} chars)")

    if engine is not None:
        from core.trust import record_wiki_version

        record_wiki_version(
            engine=engine,
            page_name=rel,
            new_content=content,
            old_content=old_content,
            change_summary=change_summary,
            source_urls=source_urls or [],
            source_types=source_types or [],
            triggered_by=triggered_by,
        )


async def _awrite_wiki_file(
    path: "str | Path",
    content: str,
    engine: object = None,
    change_summary: str = "wiki update",
    source_urls: "list[str] | None" = None,
    source_types: "list[str] | None" = None,
    triggered_by: str = "ingest",
) -> None:
    """Async wrapper kept for wiki_ingest.py callers that live inside coroutines.

    Forwards all trust-layer args to ``_write_wiki_file`` so the async path
    gets the same versioning behaviour as the sync path once PR 4 wires it in.
    """
    _write_wiki_file(
        path,
        content,
        engine=engine,
        change_summary=change_summary,
        source_urls=source_urls,
        source_types=source_types,
        triggered_by=triggered_by,
    )


def _append_log(entry: str) -> None:
    """Append a timestamped entry to log.md (append-only operation journal)."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    log_path = _wiki_path("log.md")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n## [{timestamp}] {entry}\n")


async def _aappend_log(entry: str) -> None:
    """Async wrapper for use from inside coroutines."""
    _append_log(entry)


def list_wiki_pages() -> list[str]:
    """Return all .md file paths relative to wiki root."""
    root = Path(settings.WIKI_DIR)
    if not root.exists():
        return []
    return [str(p.relative_to(root)) for p in root.rglob("*.md")]


# ── Gemini call with retry ────────────────────────────────────────────────────
# (Imported by analysis_agent — also used here for wiki maintenance calls)

_gemini = None


def _get_gemini_model():
    """Lazy initialization of Gemini model."""
    global _gemini
    if _gemini is None:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini = genai.GenerativeModel(settings.GEMINI_MODEL)
    return _gemini


_stdlib_logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(settings.GEMINI_RETRY_MAX),
    wait=wait_exponential(multiplier=settings.GEMINI_RETRY_BACKOFF_BASE, min=2, max=60),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
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
        f"- [{a.get('source','')}] {a['headline']}: {a.get('body','')[:200]}" for a in articles[:20]
    )
    prices_text = "\n".join(
        f"- {p['symbol']}: ${p['price']:.2f} (vol: {p.get('volume','?')})" for p in prices
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
- End with `> Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}` with exact timestamp

WRITE THE COMPLETE PAGE NOW (markdown only, no preamble):"""

        page_content = await call_gemini(prompt)

        # Add YAML frontmatter
        frontmatter = {
            "symbol": symbol,
            "page_type": "stock_entity",
            "last_updated": datetime.now(UTC).isoformat(),
            "ttl_hours": 24,
            "data_sources": ["yfinance", "rss_news"],
            "confidence": "high",
            "stale": False,
        }

        frontmatter_text = "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\n"
        final_content = frontmatter_text + page_content

        _write_wiki_file(f"stocks/{symbol}.md", final_content)
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
End with `> Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}`

WRITE THE OVERVIEW NOW (markdown only):"""

    overview = await call_gemini(prompt)
    _write_wiki_file("overview.md", overview)

    # ── Step 3: Rebuild index.md catalog ─────────────────────────────────────
    all_pages = list_wiki_pages()
    index_lines = [
        "# Wiki Index\n",
        f"> {len(all_pages)} pages | "
        f"Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n\n",
    ]
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


# ── Confidence + staleness helpers (used by query_wiki) ──────────────────────


def _compute_confidence(
    consulted_pages: list[str],
    page_contents: "dict[str, str] | None" = None,
) -> float:
    """Compute an honest, explainable confidence score for a query response.

    Starts at 1.0 and applies three observable deductions:

    - **Stale penalty** (−0.15 per page): any page with ``stale: true`` in its
      YAML frontmatter was flagged by the lint cycle as out-of-date.
    - **Source-diversity penalty** (−0.20, applied once): if fewer than two
      distinct ``data_sources`` types appear across all consulted pages the
      answer rests on a single information type (e.g. only RSS news, no price
      or fundamentals data).
    - **Recency penalty** (−0.10, applied once): if every consulted page with
      a ``last_updated`` timestamp is older than 24 hours the whole knowledge
      context is stale by wall-clock time.

    Floor is 0.30 — even a maximally-penalised answer is not zero-confidence,
    it just signals that the user should verify the numbers independently.

    The ``page_contents`` arg is an optimisation: ``query_wiki`` already holds
    the raw content in memory, so we accept it here to avoid re-reading every
    page from disk. Falls back to ``_read_wiki_file`` when not supplied.
    """
    score = 1.0
    source_types_seen: set[str] = set()
    any_page_recent = False
    now = datetime.now(UTC)

    for page in consulted_pages:
        content = (page_contents or {}).get(page) or _read_wiki_file(page)
        if not content:
            continue

        fm: dict = {}
        if content.startswith("---"):
            try:
                fm = yaml.safe_load(content.split("---", 2)[1]) or {}
            except yaml.YAMLError:
                fm = {}

        if fm.get("stale") is True:
            score -= 0.15

        for st in fm.get("data_sources", []):
            source_types_seen.add(st)

        lu = fm.get("last_updated")
        if lu:
            try:
                if isinstance(lu, str):
                    lu_dt = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                else:
                    lu_dt = lu if lu.tzinfo else lu.replace(tzinfo=UTC)
                if (now - lu_dt).total_seconds() / 3600 <= 24:
                    any_page_recent = True
            except Exception:
                pass

    if len(source_types_seen) < 2:
        score -= 0.20

    if consulted_pages and not any_page_recent:
        score -= 0.10

    return round(max(score, 0.30), 2)


def _any_stale(
    consulted_pages: list[str],
    page_contents: "dict[str, str] | None" = None,
) -> str:
    """Return ``'yes'`` if any consulted page has ``stale: true`` in its
    YAML frontmatter, ``'no'`` otherwise.

    Accepts pre-loaded ``page_contents`` to avoid redundant disk reads when
    called from ``query_wiki`` (which already holds the content in memory).
    """
    for page in consulted_pages:
        content = (page_contents or {}).get(page) or _read_wiki_file(page)
        if content and content.startswith("---"):
            try:
                fm = yaml.safe_load(content.split("---", 2)[1]) or {}
                if fm.get("stale") is True:
                    return "yes"
            except yaml.YAMLError:
                pass
    return "no"


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
        line.strip()
        for line in routing_response.strip().splitlines()
        if line.strip() and line.strip().endswith(".md")
    ]

    # ── Step 2: Read those pages ─────────────────────────────────────────────
    # Keep loaded content in a dict so _compute_confidence / _any_stale can
    # reuse it without a second round of disk reads.
    pages_context = ""
    consulted: list[str] = []
    loaded: dict[str, str] = {}

    for path in relevant_paths[:5]:
        content = _read_wiki_file(path)
        if content:
            pages_context += f"\n\n### From `{path}`:\n{content}"
            consulted.append(path)
            loaded[path] = content

    # Always include overview for context
    if overview_content and "overview.md" not in consulted:
        pages_context = f"\n\n### From `overview.md`:\n{overview_content}" + pages_context
        consulted.insert(0, "overview.md")
        loaded["overview.md"] = overview_content

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
    # Good answers compound the knowledge base — they don't disappear into chat.
    # The structured frontmatter + confidence rubric make every filed insight
    # self-documenting: you can tell at a glance how much to trust it and why.
    import json as _json

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    utc_label = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    confidence = _compute_confidence(consulted, page_contents=loaded)

    insight_page = f"""---
page_type: insight
generated_at: {utc_label}
question: "{question[:120].replace('"', "'")}"
pages_consulted: {_json.dumps(consulted)}
confidence_score: {confidence}
confidence_rubric: "stale_penalty=-0.15/page, source_diversity_penalty=-0.20, recency_penalty=-0.10, floor=0.30"
---

# Insight: {question[:80]}

## Answer
{answer}

## Reasoning
*This insight was derived from {len(consulted)} wiki page(s): {", ".join(f"`{p}`" for p in consulted)}.*
*Confidence score: {confidence:.2f} — see frontmatter for rubric.*

## Sources Consulted
{chr(10).join(f"- `{p}`" for p in consulted)}

## Trust Signals
- Pages consulted: {len(consulted)}
- Confidence score: {confidence:.2f}
- Generated: {utc_label}
- Any stale pages in context: {_any_stale(consulted, page_contents=loaded)}

---
*Last updated: {utc_label}*
"""

    _write_wiki_file(f"insights/{timestamp}.md", insight_page)
    _append_log(
        f"query | \"{question[:60]}...\" | consulted: {', '.join(consulted)} | confidence: {confidence:.2f}"
    )

    return answer, consulted


# ── Operation 2b: Beginner onboarding ─────────────────────────────────────────

_BEGINNER_TRIGGERS = (
    "how do i get started",
    "how do i start",
    "where do i invest",
    "where should i invest",
    "i'm new to",
    "im new to",
    "new to investing",
    "new to finance",
    "beginner",
    "don't know anything about",
    "dont know anything about",
    "know nothing about finance",
    "know nothing about investing",
    "explain the basics",
    "teach me",
    "first time investing",
    "first time investor",
    "what is a stock",
    "what is a bond",
    "what is an etf",
    "what is a mutual fund",
    "what is an index fund",
    "what is a share",
    "what are stocks",
    "what are bonds",
    "what are etfs",
    "how does the stock market work",
    "how do stocks work",
    "should i invest",
    "completely new",
    "just starting out",
)


def detect_beginner_intent(question: str) -> bool:
    """
    Cheap rule-based intent detector. We deliberately keep this offline-free so
    it always runs, and only trip on phrases that unambiguously indicate a user
    who wants onboarding rather than a specific market-data answer.

    The UI also exposes an explicit "I'm new to investing" toggle, which
    short-circuits this detection and forces the beginner flow regardless of
    wording — this function is the auto-detect fallback for free-form chat.
    """
    q = question.lower().strip()
    return any(trigger in q for trigger in _BEGINNER_TRIGGERS)


async def beginner_answer(question: str) -> tuple[str, list[str]]:
    """
    Answer a question aimed at a complete financial novice.

    The response must first teach the concepts the user needs in order to
    understand the eventual advice, then (and only then) layer in whatever
    the live wiki currently knows about the market. Intuition before numbers.

    Returns (answer_text, list_of_pages_consulted) — same shape as query_wiki
    so callers can swap the two flows transparently.
    """
    primer = _read_wiki_file("concepts/finance_basics.md")
    if not primer:
        logger.warning("[Wiki] finance_basics primer missing; answer will be weaker")
    overview = _read_wiki_file("overview.md")

    consulted: list[str] = []
    if primer:
        consulted.append("concepts/finance_basics.md")
    if overview:
        consulted.append("overview.md")

    # Optionally pull 1–2 stock pages if the user already named specific tickers,
    # so the example we close with is grounded in real current data.
    import re as _re

    ticker_mentions = [
        t for t in _re.findall(r"\b[A-Z]{1,5}\b", question) if t in settings.YFINANCE_SYMBOLS
    ][:2]
    ticker_snippets = ""
    for ticker in ticker_mentions:
        page = _read_wiki_file(f"stocks/{ticker}.md")
        if page:
            ticker_snippets += f"\n\n### From `stocks/{ticker}.md`:\n{page[:1500]}"
            consulted.append(f"stocks/{ticker}.md")

    prompt = rf"""You are a patient financial educator talking to someone who has
told you they know nothing about finance. Your single most important job is to
make them feel capable, not overwhelmed.

USER QUESTION: {question}

PRIMER (always teach the vocabulary here before giving advice):
{primer or '(no primer available)'}

CURRENT MARKET OVERVIEW (use only to ground examples, not as advice):
{overview or '(no live overview yet)'}
{ticker_snippets}

Write the answer in THREE clearly labelled sections, in this order:

## 1. Start with the concepts
Pick the 3-5 concepts from the primer that this specific user needs to
understand their question. Explain each in 2-3 sentences of plain English and,
where possible, a concrete tiny example with real numbers. Use analogies
(owning a slice of a pizza, the snowball of compounding, etc.) rather than
jargon. Define every term the first time you use it.

## 2. A step-by-step starter plan
Give an ordered, numbered checklist tailored to what they asked. Be
concrete: "open a Roth IRA at Fidelity or Vanguard and set up a \$200/month
automatic transfer into VTI" is better than "consider retirement accounts".
Anchor dollar amounts to sensible defaults if the user did not specify.
Always cover, in order: emergency fund, high-interest debt, 401(k) match,
Roth IRA, taxable brokerage, individual stocks.

## 3. How today's market fits in
ONLY if the overview or stock snippets above contain real data, reference
one or two *specific* data points to ground the plan (e.g. "today's Fed
target rate is X, which means HYSAs are paying around Y"). If there is no
current data, say so honestly ("the live market wiki is still warming up")
and keep the advice purely structural.

Finish with a one-sentence disclaimer that this is educational only.

Style rules:
- No bullet-point walls of jargon.
- Maximum 500 words total.
- Prefer "we" and "you" over passive voice.
- Never recommend a specific individual stock as a starting investment —
  always default to broad index funds for a beginner.
- Never promise returns; always phrase historical averages as historical.

WRITE THE ANSWER NOW (markdown only):"""

    answer = await call_gemini(prompt)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    insight_page = (
        f"# Beginner Session: {question[:80]}\n\n{answer}\n\n"
        f"---\n*Sources consulted: {', '.join(consulted)}*\n"
        f"*Flow: beginner_answer*\n*Generated: {timestamp} UTC*\n"
    )
    _write_wiki_file(f"insights/beginner_{timestamp}.md", insight_page)
    _append_log(f"beginner_query | \"{question[:60]}...\" | consulted: {', '.join(consulted)}")

    return answer, consulted


# ── Fast, local health snapshot (no Gemini) ───────────────────────────────────


def wiki_health_snapshot() -> dict:
    """
    Synchronous, LLM-free health check of the wiki.

    Walks `data/wiki/**/*.md`, parses YAML frontmatter, and classifies each page
    as `fresh`, `stale`, or `missing_frontmatter` based on the page's own
    `ttl_hours` vs now - `last_updated`. This is cheap enough to call on every
    UI render — it does not touch Gemini, does not rewrite any files, and does
    not attempt contradiction detection.

    Returns:
        {
            "checked_at":         ISO-8601 UTC timestamp of this snapshot,
            "total_pages":        int,
            "fresh":              [{path, symbol, page_type, age_hours, ttl_hours}, ...],
            "stale":              [{path, symbol, page_type, age_hours, ttl_hours, overdue_hours}, ...],
            "missing_frontmatter": [path, ...],
            "by_type":            {"stock": n, "concept": n, "insight": n, ...},
            "latest_lint_report": Optional[{path, generated_at_iso, stale_count, contradiction_count}],
        }

    For the audit trail version that *writes* stale banners into pages and
    calls Gemini for contradiction detection, use `lint_wiki()` instead.
    """
    wiki_root = Path(settings.WIKI_DIR)
    now = datetime.now(UTC)
    snapshot: dict[str, object] = {
        "checked_at": now.isoformat(),
        "total_pages": 0,
        "fresh": [],
        "stale": [],
        "missing_frontmatter": [],
        "by_type": {},
        "latest_lint_report": None,
    }

    if not wiki_root.exists():
        return snapshot

    for md_file in wiki_root.rglob("*.md"):
        rel_path = str(md_file.relative_to(wiki_root))
        # Don't lint our own auto-generated lint reports / logs — they'd always
        # look "stale" because nothing sets a TTL on them.
        if rel_path.startswith("insights/lint_") or rel_path == "log.md":
            continue

        snapshot["total_pages"] += 1

        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[WikiHealth] Could not read {rel_path}: {e}")
            continue

        frontmatter: dict | None = None
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1])
                except yaml.YAMLError:
                    frontmatter = None

        if not isinstance(frontmatter, dict):
            snapshot["missing_frontmatter"].append(rel_path)
            continue

        page_type = frontmatter.get("page_type", "unknown")
        snapshot["by_type"][page_type] = snapshot["by_type"].get(page_type, 0) + 1

        last_updated_str = frontmatter.get("last_updated")
        ttl_hours = float(frontmatter.get("ttl_hours", 24))

        age_hours: float | None = None
        if last_updated_str:
            try:
                last_updated = datetime.fromisoformat(str(last_updated_str).replace("Z", "+00:00"))
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=UTC)
                age_hours = (now - last_updated).total_seconds() / 3600.0
            except Exception:
                age_hours = None

        if age_hours is None:
            snapshot["missing_frontmatter"].append(rel_path)
            continue

        entry = {
            "path": rel_path,
            "symbol": frontmatter.get("symbol"),
            "page_type": page_type,
            "age_hours": round(age_hours, 2),
            "ttl_hours": ttl_hours,
        }
        if age_hours > ttl_hours:
            entry["overdue_hours"] = round(age_hours - ttl_hours, 2)
            snapshot["stale"].append(entry)
        else:
            snapshot["fresh"].append(entry)

    # Surface the most recent `lint_*.md` report so the UI can show the last
    # full Gemini-based audit at a glance.
    insights_dir = wiki_root / "insights"
    if insights_dir.exists():
        reports = sorted(
            insights_dir.glob("lint_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if reports:
            latest = reports[0]
            try:
                body = latest.read_text(encoding="utf-8")
            except Exception:
                body = ""
            stale_count = body.count("- ") if "### Stale Pages:" in body else 0
            # Cheap heuristic: we wrote the report so we know its exact shape.
            # Pull the two summary numbers out of the first few lines.
            import re as _re

            m_stale = _re.search(r"\*\*Stale pages\*\*:\s*(\d+)", body)
            m_contra = _re.search(r"## Contradiction Detection\s*\n([\s\S]*?)(?=\n##|\Z)", body)
            contradiction_count = 0
            if m_contra:
                contradiction_count = sum(
                    1 for line in m_contra.group(1).splitlines() if "**Contradiction**" in line
                )
            snapshot["latest_lint_report"] = {
                "path": str(latest.relative_to(wiki_root)),
                "generated_at_iso": datetime.fromtimestamp(
                    latest.stat().st_mtime, tz=UTC
                ).isoformat(),
                "stale_count": int(m_stale.group(1)) if m_stale else stale_count,
                "contradiction_count": contradiction_count,
            }

    return snapshot


def raw_data_snapshot() -> dict:
    """
    Summarise `data/raw/` by source. Complements `wiki_health_snapshot()` by
    showing how fresh the *inputs* to the wiki are, not just the outputs.

    Returns:
        {
            "checked_at": iso,
            "sources": {
                "sec":           {"file_count": n, "latest_iso": iso | None, "total_mb": float},
                "alpha_vantage": {...},
                "finnhub":       {...},
                "googlenews":    {...},
                "macro":         {...},
                "market_sentiment": {...},
            },
        }
    """
    raw_root = Path(settings.RAW_DATA_DIR)
    now = datetime.now(UTC)
    out = {"checked_at": now.isoformat(), "sources": {}}

    if not raw_root.exists():
        return out

    def _scan(paths: list[Path]) -> dict:
        if not paths:
            return {"file_count": 0, "latest_iso": None, "total_mb": 0.0}
        total = sum(p.stat().st_size for p in paths)
        latest = max(p.stat().st_mtime for p in paths)
        return {
            "file_count": len(paths),
            "latest_iso": datetime.fromtimestamp(latest, tz=UTC).isoformat(),
            "total_mb": round(total / 1_000_000, 2),
        }

    # SEC lives in data/raw/sec/; the rest are flat files in data/raw/ named by
    # prefix convention.
    sec_dir = raw_root / "sec"
    out["sources"]["sec"] = _scan(
        list(sec_dir.glob("company_facts_*.json")) if sec_dir.exists() else []
    )

    # Alpha Vantage + Finnhub now live in their own subdirs (see core/*_client.py).
    for sub in ("alpha_vantage", "finnhub"):
        d = raw_root / sub
        out["sources"][sub] = _scan(list(d.glob("*.json")) if d.exists() else [])

    # Flat-file prefixes.
    for label, prefix in (
        ("googlenews", "googlenews_"),
        ("macro", "macro_indicators_"),
        ("market_sentiment", "market_sentiment_"),
        ("reddit", "reddit_"),
    ):
        out["sources"][label] = _scan(list(raw_root.glob(f"{prefix}*.json")))

    return out


# ── Operation 3: Lint the wiki ────────────────────────────────────────────────


async def lint_wiki() -> dict:
    """
    Improved wiki health-check with tiered TTL decay and YAML frontmatter support.

    Walks all .md files, checks YAML frontmatter for staleness based on TTL,
    marks stale files, detects contradictions, and returns structured results.

    Returns dict: {"stale_pages": [...], "contradictions": [...], "needs_refresh": [...]}
    """
    logger.info("[Wiki] Starting comprehensive lint with TTL decay...")

    wiki_root = Path(settings.WIKI_DIR)
    if not wiki_root.exists():
        return {"stale_pages": [], "contradictions": [], "needs_refresh": []}

    current_time = datetime.now(UTC)
    stale_pages = []
    needs_refresh = []
    page_summaries = []

    # Walk all markdown files
    for md_file in wiki_root.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            rel_path = str(md_file.relative_to(wiki_root))

            # Parse YAML frontmatter
            frontmatter = None
            page_content = content

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        frontmatter = yaml.safe_load(parts[1])
                        page_content = parts[2].strip()
                    except yaml.YAMLError as e:
                        logger.warning(f"[Lint] Invalid YAML in {rel_path}: {e}")

            if not frontmatter:
                # No frontmatter - assume stale
                stale_pages.append(rel_path)
                needs_refresh.append(rel_path)
                continue

            # Check staleness based on TTL
            last_updated_str = frontmatter.get("last_updated")
            ttl_hours = frontmatter.get("ttl_hours", 24)

            if last_updated_str:
                try:
                    last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
                    age_hours = (current_time - last_updated).total_seconds() / 3600

                    if age_hours > ttl_hours:
                        # Mark as stale
                        stale_pages.append(rel_path)

                        # Add stale warning to content if not already present
                        if "⚠️ STALE" not in page_content:
                            stale_banner = f"> ⚠️ STALE — last updated {age_hours:.1f} hours ago\n\n"
                            page_content = stale_banner + page_content

                        # Update frontmatter to mark as stale
                        frontmatter["stale"] = True

                        # Write updated content
                        updated_frontmatter = (
                            "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\n"
                        )
                        updated_content = updated_frontmatter + page_content
                        md_file.write_text(updated_content, encoding="utf-8")

                        # Add to needs refresh for targeted re-fetch
                        symbol = frontmatter.get("symbol")
                        if symbol:
                            needs_refresh.append(symbol)
                        else:
                            needs_refresh.append(rel_path)

                        logger.debug(
                            f"[Lint] Marked {rel_path} as stale ({age_hours:.1f}h old, TTL: {ttl_hours}h)"
                        )

                except (ValueError, TypeError) as e:
                    logger.warning(f"[Lint] Invalid timestamp in {rel_path}: {e}")
                    stale_pages.append(rel_path)

            # Collect page summary for contradiction detection
            page_summaries.append(
                {
                    "path": rel_path,
                    "symbol": frontmatter.get("symbol"),
                    "page_type": frontmatter.get("page_type"),
                    "content_preview": page_content[:500],
                    "stale": frontmatter.get("stale", False),
                }
            )

        except Exception as e:
            logger.error(f"[Lint] Error processing {md_file}: {e}")
            continue

    # Contradiction detection using Gemini
    contradictions = []
    if len(page_summaries) > 1:
        try:
            summaries_text = "\n".join(
                [
                    f"**{p['path']}** ({p.get('page_type', 'unknown')}) - {p['content_preview'][:200]}..."
                    for p in page_summaries[:20]  # Limit to avoid token overflow
                ]
            )

            contradiction_prompt = f"""Review these wiki page summaries for contradictions.

WIKI PAGE SUMMARIES:
{summaries_text}

Identify any pages that contradict each other. For each contradiction found:
1. Name the two conflicting pages
2. Describe the specific conflict
3. Suggest which information is likely more reliable

Format as:
- **Contradiction**: page1.md vs page2.md - [description of conflict]

If no contradictions found, respond with "No contradictions detected."

CONTRADICTION ANALYSIS:"""

            contradiction_response = await call_gemini(contradiction_prompt)

            # Parse contradictions from response
            for line in contradiction_response.split("\n"):
                if "**Contradiction**:" in line:
                    contradictions.append(line.strip())

        except Exception as e:
            logger.error(f"[Lint] Error in contradiction detection: {e}")

    # Generate lint report
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")

    report_content = f"""# Wiki Lint Report

**Generated**: {current_time.strftime('%Y-%m-%d %H:%M UTC')}

## Staleness Analysis
- **Total pages checked**: {len(page_summaries)}
- **Stale pages**: {len(stale_pages)}
- **Pages needing refresh**: {len(set(needs_refresh))}

### Stale Pages:
{chr(10).join(f'- {page}' for page in stale_pages) if stale_pages else '- None'}

## Contradiction Detection
{chr(10).join(contradictions) if contradictions else '- No contradictions detected'}

## Refresh Recommendations
The following symbols/pages should be refreshed with new data:
{chr(10).join(f'- {item}' for item in set(needs_refresh)) if needs_refresh else '- None'}

---
*Automated lint report generated by wiki health-check system*
"""

    # Save lint report
    _write_wiki_file(f"insights/lint_{timestamp}.md", report_content)
    _append_log(f"lint | {len(stale_pages)} stale, {len(contradictions)} contradictions")

    logger.info(
        f"[Wiki] Lint complete: {len(stale_pages)} stale pages, {len(contradictions)} contradictions"
    )

    return {
        "stale_pages": stale_pages,
        "contradictions": contradictions,
        "needs_refresh": list(set(needs_refresh)),
    }
