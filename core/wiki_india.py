"""
core/wiki_india.py

Indian-market wiki pipeline — a parallel sibling to core/wiki.py.

Manages ``data/wiki_india/`` using the same LLM Wiki pattern (Karpathy pattern):
Gemini incrementally writes structured markdown pages; knowledge is compiled once
and read at query time.

Wiki layout:
  data/wiki_india/
    index.md          — catalog of all Indian wiki pages
    log.md            — append-only operation log
    overview.md       — rolling Indian market synthesis
    equities/
      RELIANCE.NS.md  — NSE entity page (price, news, risks)
      TCS.NS.md
      ...
    mutual_funds/
      Mirae_ELSS.md   — NAV history, category, risk profile
      ...
    macro/
      rbi_rates.md    — repo rate, CRR, SLR snapshot
      india_economy.md
    basics/
      finance_basics_india.md  — seed primer (committed to repo)
      tax_india.md             — tax guide (committed to repo)
    insights/
      YYYY-MM-DD_HH-MM.md     — filed query answers

Operations:
  ingest_india(prices, nav_records, rbi_rates, news_batches)
      LLM updates the Indian wiki from fresh fetcher data.
  query_india(question)
      LLM reads the Indian wiki index + relevant pages, answers with INR context.
  detect_beginner_intent_india(question)
      Rule-based detector for first-time Indian investor questions.
  beginner_answer_india(question)
      Onboarding answer backed by the Indian basics primer.
  india_wiki_health()
      Fast, LLM-free staleness snapshot of data/wiki_india/.

Design rules:
- Import ``call_gemini`` from core/wiki.py (one Gemini model, no duplication).
- All file I/O goes to INDIA_WIKI_DIR (settings.INDIA_WIKI_DIR).
- Every function is safe to call with no data — it degrades gracefully.
- No loops without a hard upper-bound iteration count.
- No network calls in this module — fetching is in core/fetchers_india.py.
"""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from loguru import logger

from core.settings import settings

# Reuse the Gemini model + retry wrapper from core/wiki.py
from core.wiki import _any_stale, _compute_confidence, call_gemini

# ── India wiki directory helpers ──────────────────────────────────────────────


def _ipath(*parts: str) -> Path:
    """Return a Path inside data/wiki_india/, creating parent dirs as needed."""
    p = Path(settings.INDIA_WIKI_DIR).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _iread(rel_path: str) -> str:
    """Read an India wiki file; returns '' if it doesn't exist."""
    p = _ipath(rel_path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _iwrite(rel_path: str, content: str) -> None:
    """Write (overwrite) an India wiki file."""
    p = _ipath(rel_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    p.write_text(content, encoding="utf-8")
    logger.debug(f"[IndiaWiki] Wrote {rel_path} ({len(content)} chars, was {len(old)} chars)")


def _iappend_log(entry: str) -> None:
    """Append a timestamped line to data/wiki_india/log.md."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    log_path = _ipath("log.md")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n## [{timestamp}] {entry}\n")


def list_india_wiki_pages() -> list[str]:
    """All .md file paths relative to data/wiki_india/ root."""
    root = Path(settings.INDIA_WIKI_DIR)
    if not root.exists():
        return []
    return [str(p.relative_to(root)) for p in root.rglob("*.md")]


# ── Indian beginner intent detection ─────────────────────────────────────────

_INDIA_BEGINNER_TRIGGERS: tuple[str, ...] = (
    # General first-timer signals
    "how do i start investing",
    "where to invest",
    "how to invest in india",
    "best investment in india",
    "i'm new to investing",
    "im new to investing",
    "new to investing",
    "first time investor",
    "beginner investor",
    "just starting",
    "no idea about investing",
    "don't know about investing",
    # India-specific product questions
    "what is sip",
    "what is a sip",
    "how does sip work",
    "what is mutual fund",
    "what is a mutual fund",
    "what are mutual funds",
    "what is nav",
    "what is nifty",
    "what is nifty 50",
    "what is sensex",
    "what is elss",
    "what is ppf",
    "how to buy stocks in india",
    "how to invest in nifty",
    "what is a demat account",
    "how to open demat account",
    "what is sebi",
    "what is amfi",
    "where to invest 1000 rupees",
    "where to invest 5000 rupees",
    "where to invest 10000 rupees",
    "investing with small amount",
    "safe investment india",
    "best sip to start",
    "index fund for beginners",
    # Tax / 80c questions from beginners
    "how to save tax in india",
    "what is 80c",
    "elss tax saving",
    "how to get tax benefit",
)


def detect_beginner_intent_india(question: str) -> bool:
    """
    Return True if the question reads as a first-time Indian investor question.

    Purely offline, rule-based (no LLM call). Triggered by the UI before
    calling query_india so the right prompt template is chosen.
    """
    q = question.lower().strip()
    return any(trigger in q for trigger in _INDIA_BEGINNER_TRIGGERS)


# ── Investment horizon classification ─────────────────────────────────────────

_SHORT_TERM_SIGNALS: tuple[str, ...] = (
    "short term",
    "short-term",
    "6 month",
    "few months",
    "emergency",
    "liquid",
    "fd",
    "fixed deposit",
    "parking money",
    "need money soon",
    "next year",
    "within a year",
    "t-bill",
    "treasury bill",
    "overnight fund",
    "within 1 year",
    "less than a year",
)

_INTERMEDIATE_TERM_SIGNALS: tuple[str, ...] = (
    "3 year",
    "4 year",
    "5 year",
    "medium term",
    "medium-term",
    "sip",
    "systematic investment",
    "elss",
    "index fund",
    "tax saving",
    "80c",
    "save tax",
    "balanced fund",
    "hybrid fund",
    "2-3 year",
    "3-5 year",
    "few years",
    "couple of years",
)

_LONG_TERM_SIGNALS: tuple[str, ...] = (
    "long term",
    "long-term",
    "retirement",
    "10 year",
    "15 year",
    "20 year",
    "25 year",
    "30 year",
    "future",
    "wealth creation",
    "build wealth",
    "corpus",
    "nps",
    "ppf",
    "public provident fund",
    "children education",
    "child education",
    "marriage",
    "decade",
    "generations",
)

_SEBI_DISCLAIMER = (
    "⚠️ This is for educational purposes only. "
    "Please verify with a SEBI-registered investment advisor before investing."
)


# ── User profile context helper ───────────────────────────────────────────────


def _profile_block(profile: dict | None) -> str:
    """
    Render a USER PROFILE section suitable for injection into Gemini prompts.

    Returns an empty string when *profile* is ``None`` so every call site can
    unconditionally interpolate ``{_profile_block(profile)}`` without an extra
    ``if`` branch.
    """
    if not profile:
        return ""
    lines = [
        "\nUSER PROFILE (personalise the answer to these facts):",
        f"- Monthly income range : {profile.get('monthly_income', 'unknown')}",
        f"- Monthly SIP budget   : {profile.get('monthly_sip_budget', 'unknown')}",
        f"- Risk tolerance       : {profile.get('risk_tolerance', 'unknown')}",
        f"- Tax bracket          : {profile.get('tax_bracket_pct', 'unknown')}%",
        f"- Primary goal         : {profile.get('primary_goal', 'unknown')}",
        f"- Preferred horizon    : {profile.get('horizon_pref', 'unknown')}",
    ]
    return "\n".join(lines) + "\n"


def classify_investment_horizon(question: str) -> str:
    """
    Classify the investment time-horizon implied by *question*.

    Returns one of: ``"short"`` | ``"intermediate"`` | ``"long"`` | ``"unknown"``.

    Rules (all rule-based, no LLM):
    - Exactly one dominant bucket → return that bucket.
    - Multiple buckets or no match → ``"unknown"``.

    Horizon → product mapping:
    - ``short``        → FD / liquid funds / T-bills (≤ 1 year)
    - ``intermediate`` → SIP / ELSS / index funds (2–5 years)
    - ``long``         → NPS / PPF / long-term equity (5+ years)
    """
    q = question.lower()
    short = any(s in q for s in _SHORT_TERM_SIGNALS)
    intermediate = any(s in q for s in _INTERMEDIATE_TERM_SIGNALS)
    long_ = any(s in q for s in _LONG_TERM_SIGNALS)

    buckets_hit = sum([short, intermediate, long_])
    if buckets_hit != 1:
        return "unknown"
    if short:
        return "short"
    if intermediate:
        return "intermediate"
    return "long"


# ── Horizon-specific answer flows ────────────────────────────────────────────


async def short_term_india_answer(
    question: str, profile: dict | None = None, hindi: bool = False
) -> tuple[str, list[str]]:
    """
    Answer a short-horizon question (≤ 1 year) with FD / liquid / T-bill framing.

    Reads the basics primer and RBI macro page for context.
    Returns (answer_text, pages_consulted).
    """
    primer = _iread("basics/finance_basics_india.md")
    rbi_page = _iread("macro/rbi_rates.md")

    consulted: list[str] = []
    context_parts: list[str] = []
    if primer:
        consulted.append("basics/finance_basics_india.md")
        context_parts.append(f"### Finance Basics:\n{primer[:2000]}")
    if rbi_page:
        consulted.append("macro/rbi_rates.md")
        context_parts.append(f"### RBI Rates & Policy:\n{rbi_page[:1500]}")

    context = "\n\n".join(context_parts) or "(basics not loaded yet)"

    prompt = f"""You are a concise, friendly personal finance educator for Indian investors.
The user has a SHORT-TERM investment horizon (up to 1 year).
{_profile_block(profile)}
USER QUESTION: {question}

KNOWLEDGE BASE:
{context}

Answer in three focused sections:

## Suitable short-term instruments
Explain each in 2–3 plain sentences using ₹ amounts and current approximate rates:
- Fixed Deposits (FD) at major banks / small finance banks
- Liquid mutual funds (very low risk, same-day redemption)
- RBI Floating Rate Savings Bonds / T-bills (91-day, 182-day, 364-day)
If the RBI repo rate is mentioned in the knowledge base, explain how it affects FD rates.
Tailor ₹ examples to the user's SIP budget and income if the USER PROFILE is present.

## Instruments to AVOID for this horizon
2–3 bullet points on why equity / ELSS / long-duration debt are unsuitable for ≤ 1 year.

## Getting started (step by step)
A numbered checklist of 3–5 concrete steps. Use specific ₹ amounts.
Example: "Park ₹1 lakh in a liquid fund via Zerodha Coin; same-day withdrawal if needed."

Keep it under 400 words. Use ₹ for all amounts.

Finish with: "{_SEBI_DISCLAIMER}"

WRITE THE ANSWER NOW (markdown only):"""

    if hindi:
        prompt += "\n\nPlease respond entirely in Hindi (Devanagari script)."
    answer = await call_gemini(prompt)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    insight = (
        f"# Short-Term Insight: {question[:80]}\n\n{answer}\n\n"
        f"---\n*Sources: {', '.join(consulted)}*\n"
        f"*Flow: short_term_india_answer | Generated: {timestamp} UTC*\n"
        f"*{_SEBI_DISCLAIMER}*\n"
    )
    _iwrite(f"insights/short_{timestamp}.md", insight)
    _iappend_log(f"short_term | \"{question[:60]}\" | consulted: {', '.join(consulted)}")

    return answer, consulted


async def intermediate_india_answer(
    question: str, profile: dict | None = None, hindi: bool = False
) -> tuple[str, list[str]]:
    """
    Answer an intermediate-horizon question (2–5 years) with SIP / ELSS / index framing.

    Reads the basics primer, any ELSS / mutual fund pages, and the overview.
    Returns (answer_text, pages_consulted).
    """
    primer = _iread("basics/finance_basics_india.md")
    tax_guide = _iread("basics/tax_india.md")
    overview = _iread("overview.md")

    consulted: list[str] = []
    context_parts: list[str] = []
    if primer:
        consulted.append("basics/finance_basics_india.md")
        context_parts.append(f"### Finance Basics:\n{primer[:2000]}")
    if tax_guide:
        consulted.append("basics/tax_india.md")
        context_parts.append(f"### Tax Guide:\n{tax_guide[:1200]}")
    if overview:
        consulted.append("overview.md")
        context_parts.append(f"### Market Overview:\n{overview[:800]}")

    context = "\n\n".join(context_parts) or "(basics not loaded yet)"

    prompt = f"""You are a concise, friendly personal finance educator for Indian investors.
The user has an INTERMEDIATE investment horizon (roughly 2–5 years).
{_profile_block(profile)}
USER QUESTION: {question}

KNOWLEDGE BASE:
{context}

Answer in three focused sections:

## Suitable medium-term instruments
Explain each in 2–3 sentences with ₹ examples:
- SIP (Systematic Investment Plan) in Nifty 50 / Nifty Next 50 index funds
- ELSS (Equity Linked Savings Scheme) — tax benefit under Section 80C, 3-year lock-in
- Balanced / Hybrid funds for moderate risk tolerance
Explain what SIP is for someone who may not know it yet.
Tailor ₹ amounts to the user's SIP budget and tax bracket if the USER PROFILE is present.

## Tax efficiency tips
1–2 bullet points: ELSS saves up to ₹46,800/year in taxes (30% slab on ₹1.5L 80C limit).
Mention LTCG (Long-Term Capital Gains) tax on equity: 10% above ₹1 lakh/year.
If the user's tax bracket is in the profile, personalise the saving amount.

## Getting started (step by step)
A numbered checklist of 3–5 concrete steps. Example:
"Start a ₹2,000/month SIP in a Nifty 50 index fund via Kuvera or Zerodha Coin."
Cover: emergency fund first → 80C ELSS SIP → plain index SIP for remaining goal.

Keep it under 450 words. Use ₹ for all amounts.

Finish with: "{_SEBI_DISCLAIMER}"

WRITE THE ANSWER NOW (markdown only):"""

    if hindi:
        prompt += "\n\nPlease respond entirely in Hindi (Devanagari script)."
    answer = await call_gemini(prompt)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    insight = (
        f"# Intermediate-Term Insight: {question[:80]}\n\n{answer}\n\n"
        f"---\n*Sources: {', '.join(consulted)}*\n"
        f"*Flow: intermediate_india_answer | Generated: {timestamp} UTC*\n"
        f"*{_SEBI_DISCLAIMER}*\n"
    )
    _iwrite(f"insights/intermediate_{timestamp}.md", insight)
    _iappend_log(f"intermediate | \"{question[:60]}\" | consulted: {', '.join(consulted)}")

    return answer, consulted


async def long_term_india_answer(
    question: str, profile: dict | None = None, hindi: bool = False
) -> tuple[str, list[str]]:
    """
    Answer a long-horizon question (5+ years) with NPS / PPF / long-term equity framing.

    Reads the basics primer, tax guide, and market overview for context.
    Returns (answer_text, pages_consulted).
    """
    primer = _iread("basics/finance_basics_india.md")
    tax_guide = _iread("basics/tax_india.md")
    overview = _iread("overview.md")

    consulted: list[str] = []
    context_parts: list[str] = []
    if primer:
        consulted.append("basics/finance_basics_india.md")
        context_parts.append(f"### Finance Basics:\n{primer[:2000]}")
    if tax_guide:
        consulted.append("basics/tax_india.md")
        context_parts.append(f"### Tax Guide:\n{tax_guide[:1500]}")
    if overview:
        consulted.append("overview.md")
        context_parts.append(f"### Market Overview:\n{overview[:800]}")

    context = "\n\n".join(context_parts) or "(basics not loaded yet)"

    prompt = f"""You are a concise, friendly personal finance educator for Indian investors.
The user has a LONG-TERM investment horizon (5 years or more).
{_profile_block(profile)}
USER QUESTION: {question}

KNOWLEDGE BASE:
{context}

Answer in three focused sections:

## Power of long-term compounding in India
Explain compounding in 2–3 plain sentences with a realistic ₹ example.
Example: "₹5,000/month SIP in a Nifty 50 index fund over 20 years at 12% CAGR
could grow to approximately ₹50 lakh (historical average; past returns ≠ future returns)."
Use realistic numbers grounded in Indian market history; never guarantee returns.
Tailor the ₹ SIP amount to the user's monthly SIP budget if the USER PROFILE is present.

## Suitable long-term instruments
Explain each in 2–3 sentences:
- NPS (National Pension System) — tax deduction under 80CCD(1B), up to ₹50,000 extra
- PPF (Public Provident Fund) — government-backed, 15-year lock-in, tax-free on maturity
- Nifty 50 / Nifty Next 50 index funds via long-horizon SIP
- Direct equity (only for experienced investors — briefly note the risk)
Mention that diversification across NPS + PPF + equity SIP is the standard long-term stack.

## Getting started (step by step)
A numbered checklist of 4–6 concrete steps in order of priority:
1. Emergency fund (3–6 months expenses in liquid fund)
2. Term insurance (pure protection, not ULIP)
3. NPS Tier-I account (₹500/month minimum, additional 80CCD(1B) benefit)
4. PPF account at bank / post office (₹500–₹1.5L/year)
5. Nifty 50 index fund SIP for remaining investable surplus

Keep it under 500 words. Use ₹ for all amounts.

Finish with: "{_SEBI_DISCLAIMER}"

WRITE THE ANSWER NOW (markdown only):"""

    if hindi:
        prompt += "\n\nPlease respond entirely in Hindi (Devanagari script)."
    answer = await call_gemini(prompt)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    insight = (
        f"# Long-Term Insight: {question[:80]}\n\n{answer}\n\n"
        f"---\n*Sources: {', '.join(consulted)}*\n"
        f"*Flow: long_term_india_answer | Generated: {timestamp} UTC*\n"
        f"*{_SEBI_DISCLAIMER}*\n"
    )
    _iwrite(f"insights/long_{timestamp}.md", insight)
    _iappend_log(f"long_term | \"{question[:60]}\" | consulted: {', '.join(consulted)}")

    return answer, consulted


# ── Operation 1: Ingest → India wiki ─────────────────────────────────────────


async def ingest_india(
    prices: list[dict] | None = None,
    nav_records: list[dict] | None = None,
    rbi_rates: dict | None = None,
    news_batches: list[dict] | None = None,
) -> None:
    """
    Update the Indian wiki from fresh fetcher data.

    Four optional data streams — pass only what you have. Every stream is
    processed independently and failures in one don't abort others.

    Args:
        prices:       list of NSE price dicts from fetch_india_prices()
        nav_records:  list of AMFI NAV dicts from fetch_amfi_nav()
        rbi_rates:    dict from fetch_rbi_rates()
        news_batches: list of news batch dicts from fetch_india_news_rss()
    """
    prices = prices or []
    nav_records = nav_records or []
    news_batches = news_batches or []

    if not prices and not nav_records and not rbi_rates and not news_batches:
        logger.debug("[IndiaWiki] No data to ingest — skipping")
        return

    logger.info(
        f"[IndiaWiki] Ingest: {len(prices)} prices, {len(nav_records)} NAVs, "
        f"{len(news_batches)} news batches, rbi={rbi_rates is not None}"
    )

    # ── 1a. Update per-symbol equity pages ───────────────────────────────────
    # Build a news lookup by symbol (strips .NS for matching against news query)
    news_by_symbol: dict[str, list[dict]] = {}
    for batch in news_batches:
        sym = batch.get("symbol", "")
        news_by_symbol[sym] = batch.get("articles", [])[:10]

    for price_rec in prices[:8]:  # cap at 8 per cycle to respect rate limits
        symbol = price_rec.get("symbol", "")
        display = symbol.replace(".NS", "")
        existing = _iread(f"equities/{symbol}.md")

        # Match news by the display name (without .NS)
        articles = news_by_symbol.get(display, [])
        articles_text = (
            "\n".join(f"- {a.get('title', '')} [{a.get('source', '')}]" for a in articles)
            or "(no recent news available)"
        )

        prompt = f"""You are maintaining a financial knowledge base for Indian retail investors.
Update the NSE equity wiki page for {symbol}.

EXISTING PAGE (may be empty if first time):
{existing or '(new page — create it)'}

LIVE DATA:
Price (INR): ₹{price_rec.get('price_inr', 'N/A')}
Exchange: NSE
Fetched at: {price_rec.get('timestamp', '')}

Recent news headlines:
{articles_text}

INSTRUCTIONS:
- Write a complete markdown page for {symbol} aimed at Indian retail investors
- Use ₹ (INR) for all prices — never use $
- Include sections: ## Summary, ## Price Snapshot, ## News Highlights, ## Key Risks, ## Cross-References
- Risks must be India-specific (regulatory, RBI/SEBI policy, sectoral, currency)
- Cross-references use [[WikiLink]] style and should name Indian financial concepts
- Under 400 words. Be factual; never invent numbers
- End with `> Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}`

WRITE THE COMPLETE PAGE NOW (markdown only, no preamble):"""

        try:
            page_content = await call_gemini(prompt)
            frontmatter = {
                "symbol": symbol,
                "page_type": "india_equity",
                "market": "india",
                "exchange": "NSE",
                "last_updated": datetime.now(UTC).isoformat(),
                "ttl_hours": 1,
                "data_sources": ["yfinance_nse", "google_news_rss_india"],
                "stale": False,
            }
            full = (
                "---\n"
                + yaml.dump(frontmatter, default_flow_style=False)
                + "---\n\n"
                + page_content
            )
            _iwrite(f"equities/{symbol}.md", full)
            logger.info(f"[IndiaWiki] Updated equities/{symbol}.md")
        except Exception as e:
            logger.error(f"[IndiaWiki] Failed to update page for {symbol}: {e}")

    # ── 1b. Update mutual fund pages ─────────────────────────────────────────
    for nav in nav_records[:6]:
        fname = nav.get("friendly_name", "").replace(" ", "_")
        rel = f"mutual_funds/{fname}.md"
        existing = _iread(rel)

        prompt = f"""You are maintaining a financial knowledge base for Indian retail investors.
Update the mutual fund wiki page for {nav.get('scheme_name', fname)}.

EXISTING PAGE:
{existing or '(new page)'}

LIVE DATA:
Fund House: {nav.get('fund_house', '')}
Scheme Name: {nav.get('scheme_name', '')}
Category: {nav.get('scheme_category', '')}
Type: {nav.get('scheme_type', '')}
Current NAV: ₹{nav.get('nav', 'N/A')} (as of {nav.get('nav_date', '')})
ISIN (Growth): {nav.get('isin_growth', '')}
Friendly name: {nav.get('friendly_name', '')}

INSTRUCTIONS:
- Write a plain-language page explaining this fund to a first-time Indian investor
- Include: ## What This Fund Does, ## Who Should Invest, ## NAV Snapshot, ## Risk Profile, ## Key Considerations
- Mention SIP suitability, tax implications if ELSS, lock-in period if any
- All amounts in ₹ (INR). Under 350 words. Be factual; never invent returns
- End with `> Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}`

WRITE THE COMPLETE PAGE NOW (markdown only, no preamble):"""

        try:
            page_content = await call_gemini(prompt)
            frontmatter = {
                "scheme_code": nav.get("scheme_code"),
                "friendly_name": fname,
                "page_type": "india_mutual_fund",
                "market": "india",
                "last_updated": datetime.now(UTC).isoformat(),
                "ttl_hours": 24,
                "data_sources": ["amfi_mfapi"],
                "stale": False,
            }
            full = (
                "---\n"
                + yaml.dump(frontmatter, default_flow_style=False)
                + "---\n\n"
                + page_content
            )
            _iwrite(rel, full)
            logger.info(f"[IndiaWiki] Updated {rel}")
        except Exception as e:
            logger.error(f"[IndiaWiki] Failed to update MF page {fname}: {e}")

    # ── 1c. Update RBI macro page ─────────────────────────────────────────────
    if rbi_rates:
        existing = _iread("macro/rbi_rates.md")
        prompt = f"""You are maintaining a financial knowledge base for Indian retail investors.
Update the RBI policy rates wiki page.

EXISTING PAGE:
{existing or '(new page)'}

LIVE DATA:
Repo Rate: {rbi_rates.get('repo_rate_pct', 'N/A')}%
Reverse Repo Rate: {rbi_rates.get('reverse_repo_rate_pct', 'N/A')}%
CRR: {rbi_rates.get('crr_pct', 'N/A')}%
SLR: {rbi_rates.get('slr_pct', 'N/A')}%
Source: {rbi_rates.get('source', '')}
Fetched at: {rbi_rates.get('fetched_at', '')}

INSTRUCTIONS:
- Write a plain-language explanation of what these rates mean for an Indian retail investor
- Explain: how the repo rate affects home loan EMIs, FD rates, equity markets
- Explain: what CRR and SLR mean in layperson terms
- Include sections: ## Current Policy Rates, ## What This Means For You, ## Market Impact
- Under 350 words. Use ₹/% throughout. Be factual
- End with `> Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}`

WRITE THE COMPLETE PAGE NOW (markdown only, no preamble):"""

        try:
            page_content = await call_gemini(prompt)
            frontmatter = {
                "page_type": "india_macro",
                "market": "india",
                "topic": "rbi_rates",
                "last_updated": datetime.now(UTC).isoformat(),
                "ttl_hours": 24,
                "data_sources": [rbi_rates.get("source", "rbi")],
                "stale": False,
            }
            full = (
                "---\n"
                + yaml.dump(frontmatter, default_flow_style=False)
                + "---\n\n"
                + page_content
            )
            _iwrite("macro/rbi_rates.md", full)
            logger.info("[IndiaWiki] Updated macro/rbi_rates.md")
        except Exception as e:
            logger.error(f"[IndiaWiki] Failed to update RBI rates page: {e}")

    # ── 1d. Update market overview ────────────────────────────────────────────
    existing_overview = _iread("overview.md")
    prices_text = (
        "\n".join(f"- {p['symbol']}: ₹{p.get('price_inr', '?'):.2f}" for p in prices)
        or "(no price data)"
    )
    nav_text = (
        "\n".join(
            f"- {n.get('friendly_name', '')}: ₹{n.get('nav', '?'):.4f} ({n.get('nav_date', '')})"
            for n in nav_records
        )
        or "(no MF NAV data)"
    )

    try:
        overview_prompt = f"""You are maintaining an Indian financial knowledge base.
Update the Indian market overview page.

EXISTING OVERVIEW:
{existing_overview or '(new — create it)'}

TODAY'S DATA:
NSE Prices:
{prices_text}

Mutual Fund NAVs:
{nav_text}

RBI Repo Rate: {rbi_rates.get('repo_rate_pct', 'N/A') if rbi_rates else 'N/A'}%

Write a concise Indian market overview (under 300 words) covering:
## Indian Market Overview
## Key Themes
## NSE Stocks to Watch
## Macro Signals (RBI, inflation)
## Risk Signals

Use ₹ for amounts. Be factual. Reference specific prices. Use [[wikilink]] for cross-refs.
End with `> Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}`

WRITE THE OVERVIEW NOW (markdown only):"""

        overview = await call_gemini(overview_prompt)
        _iwrite("overview.md", overview)
        logger.info("[IndiaWiki] Updated overview.md")
    except Exception as e:
        logger.error(f"[IndiaWiki] Failed to update overview: {e}")

    # ── 1e. Rebuild index ─────────────────────────────────────────────────────
    all_pages = list_india_wiki_pages()
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# India Wiki Index\n\n",
        f"> {len(all_pages)} pages | Last updated: {ts}\n\n",
        "## Equity Pages (NSE)\n",
    ]
    for page in sorted(p for p in all_pages if p.startswith("equities/")):
        sym = page.replace("equities/", "").replace(".md", "")
        lines.append(f"- [[{sym}]] → `{page}`\n")
    lines.append("\n## Mutual Fund Pages\n")
    for page in sorted(p for p in all_pages if p.startswith("mutual_funds/")):
        lines.append(f"- `{page}`\n")
    lines.append("\n## Macro & Policy\n")
    for page in sorted(p for p in all_pages if p.startswith("macro/")):
        lines.append(f"- `{page}`\n")
    lines.append("\n## Basics & Education\n")
    for page in sorted(p for p in all_pages if p.startswith("basics/")):
        lines.append(f"- `{page}`\n")
    lines.append("\n## Insights Archive\n")
    for page in sorted(p for p in all_pages if p.startswith("insights/")):
        lines.append(f"- `{page}`\n")
    _iwrite("index.md", "".join(lines))

    _iappend_log(
        f"ingest | {len(prices)} prices, {len(nav_records)} NAVs, "
        f"rbi={'yes' if rbi_rates else 'no'}, news={len(news_batches)}"
    )
    logger.info("[IndiaWiki] Ingest complete.")


# ── Operation 2: Query the India wiki ────────────────────────────────────────


async def query_india(
    question: str, profile: dict | None = None, hindi: bool = False
) -> tuple[str, list[str]]:
    """
    Answer a question about Indian finance using the India wiki.

    Routing priority:
    1. ``beginner`` questions → ``beginner_answer_india`` (must be handled by the caller
       before reaching here, but ``query_india`` delegates gracefully if called directly).
    2. Detected horizon ``short`` → ``short_term_india_answer``
    3. Detected horizon ``intermediate`` → ``intermediate_india_answer``
    4. Detected horizon ``long`` → ``long_term_india_answer``
    5. ``unknown`` horizon → full LLM wiki-retrieval pipeline (original behaviour).

    Args:
        question: User's natural language question.
        profile:  Optional dict with keys matching ``UserProfile`` fields
                  (monthly_income, monthly_sip_budget, risk_tolerance,
                  tax_bracket_pct, primary_goal, horizon_pref). When present,
                  the profile context is injected into every Gemini prompt.

    Mirrors core/wiki.query_wiki but routes to data/wiki_india/ and
    uses Indian-context answer prompts (INR, SEBI, AMFI, SIP framing).

    Returns (answer_text, list_of_pages_consulted).
    Good answers are filed back into data/wiki_india/insights/.
    """
    # ── Horizon-based fast-path routing ──────────────────────────────────────
    # Let the stored horizon_pref override question-level signals when present
    # so the user's explicit preference wins.
    horizon_from_profile = (profile or {}).get("horizon_pref", "")
    horizon = (
        horizon_from_profile if horizon_from_profile else classify_investment_horizon(question)
    )

    if horizon == "short":
        return await short_term_india_answer(question, profile=profile, hindi=hindi)
    if horizon == "intermediate":
        return await intermediate_india_answer(question, profile=profile, hindi=hindi)
    if horizon == "long":
        return await long_term_india_answer(question, profile=profile, hindi=hindi)

    # ── Full wiki-retrieval pipeline for unknown horizon ──────────────────────
    index_content = _iread("index.md")
    overview_content = _iread("overview.md")

    if not index_content:
        return (
            "The India wiki is still being built — wait for the first ingest cycle. "
            "In the meantime, check the basics pages at data/wiki_india/basics/.",
            [],
        )

    # ── Step 1: Route to relevant pages ──────────────────────────────────────
    routing_prompt = f"""You are an Indian financial wiki assistant.
A user asked: "{question}"

India wiki index:
{index_content}

List the 3–5 most relevant page paths for answering this question.
Reply with ONLY a newline-separated list of file paths ending in .md.
No other text."""

    routing_response = await call_gemini(routing_prompt)
    relevant_paths = [
        line.strip()
        for line in routing_response.strip().splitlines()
        if line.strip() and line.strip().endswith(".md")
    ]

    # ── Step 2: Read those pages ──────────────────────────────────────────────
    pages_context = ""
    consulted: list[str] = []
    loaded: dict[str, str] = {}

    for path in relevant_paths[:5]:
        content = _iread(path)
        if content:
            pages_context += f"\n\n### From `{path}`:\n{content}"
            consulted.append(path)
            loaded[path] = content

    if overview_content and "overview.md" not in consulted:
        pages_context = f"\n\n### From `overview.md`:\n{overview_content}" + pages_context
        consulted.insert(0, "overview.md")
        loaded["overview.md"] = overview_content

    # Always include basics primer for education-heavy queries
    basics_path = "basics/finance_basics_india.md"
    if basics_path not in consulted:
        basics = _iread(basics_path)
        if basics:
            pages_context += f"\n\n### From `{basics_path}` (always-on primer):\n{basics[:2000]}"
            consulted.append(basics_path)
            loaded[basics_path] = basics

    # ── Step 3: Generate the answer ───────────────────────────────────────────
    answer_prompt = f"""You are a concise, friendly personal finance AI advisor focused on India.
Answer the question below using ONLY the wiki content provided.
{_profile_block(profile)}
QUESTION: {question}
INVESTMENT HORIZON DETECTED: {horizon}

INDIA WIKI CONTENT:
{pages_context}

Instructions:
- Use ₹ (INR) for all amounts — never use $ or USD
- Reference SEBI, AMFI, NSE/BSE, and RBI where relevant
- Mention SIP as the default starting mechanism for equity investments
- Ask the user about their investment timeline before making specific recommendations
- Keep answers to 3–4 paragraphs; be specific, cite data from the wiki
- Do not invent numbers. Always phrase historical returns as historical averages
- If a USER PROFILE is present above, personalise ₹ amounts to the stated SIP budget
- End with: "{_SEBI_DISCLAIMER}"

YOUR RESPONSE:"""

    if hindi:
        answer_prompt += "\n\nPlease respond entirely in Hindi (Devanagari script)."
    answer = await call_gemini(answer_prompt)

    # ── Step 4: File the insight ──────────────────────────────────────────────
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    utc_label = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    confidence = _compute_confidence(consulted, page_contents=loaded)

    insight_page = f"""---
page_type: india_insight
market: india
generated_at: {utc_label}
question: "{question[:120].replace('"', "'")}"
pages_consulted: {_json.dumps(consulted)}
confidence_score: {confidence}
investment_horizon: {horizon}
---

# India Insight: {question[:80]}

## Answer
{answer}

## Reasoning
*Derived from {len(consulted)} India wiki page(s): {", ".join(f"`{p}`" for p in consulted)}.*
*Confidence: {confidence:.2f} | Horizon: {horizon}*

## Sources Consulted
{chr(10).join(f"- `{p}`" for p in consulted)}

## Trust Signals
- Pages consulted: {len(consulted)}
- Confidence score: {confidence:.2f}
- Any stale pages: {_any_stale(consulted, page_contents=loaded)}
- Generated: {utc_label}

---
*⚠️ Educational only. Verify with a SEBI-registered advisor.*
"""

    _iwrite(f"insights/{timestamp}.md", insight_page)
    _iappend_log(
        f"query | \"{question[:60]}\" | consulted: {', '.join(consulted)} | "
        f"confidence: {confidence:.2f} | horizon: {horizon}"
    )

    return answer, consulted


# ── Operation 2b: Indian beginner onboarding ──────────────────────────────────


async def beginner_answer_india(question: str) -> tuple[str, list[str]]:
    """
    Answer a first-time investor question using the Indian basics primer.

    Always reads finance_basics_india.md and tax_india.md as context so the
    answer is grounded in Indian products, regulation, and currency.

    Returns (answer_text, pages_consulted).
    """
    primer = _iread("basics/finance_basics_india.md")
    tax_guide = _iread("basics/tax_india.md")
    overview = _iread("overview.md")

    consulted: list[str] = []
    if primer:
        consulted.append("basics/finance_basics_india.md")
    if tax_guide:
        consulted.append("basics/tax_india.md")
    if overview:
        consulted.append("overview.md")

    context_blocks = "\n\n".join(
        [
            f"### Finance Basics:\n{primer[:2500]}" if primer else "",
            f"### Tax Guide:\n{tax_guide[:1500]}" if tax_guide else "",
            f"### Current Market Overview:\n{overview[:1000]}" if overview else "",
        ]
    )

    prompt = f"""You are a patient, friendly financial educator for first-time Indian investors.
The user is completely new to investing and needs clarity, not jargon.

USER QUESTION: {question}

KNOWLEDGE BASE:
{context_blocks or '(basics not loaded yet)'}

Write the answer in THREE sections:

## 1. The concepts you need to know first
Pick 3–5 concepts from the knowledge base that the user needs to understand
their question. Explain each in 2–3 plain sentences. Use relatable Indian
examples (chai analogy for compounding, "EMI for wealth" for SIP, etc.).
Define every financial term the first time you use it.

## 2. Your action plan (step by step)
Give a concrete numbered checklist. Be specific:
"Start a ₹500/month SIP in a Nifty 50 index fund via Zerodha Coin or Kuvera."
Always cover in order: emergency fund → insurance → 80C savings → equity SIP.
Anchor amounts in ₹. Never suggest stocks to a beginner — always index funds.

## 3. What the current Indian market looks like
Only if the overview has real data, cite 1–2 specific numbers (e.g. repo rate,
Nifty level). If the wiki is still warming up, say so and keep advice structural.

Finish with: "⚠️ This is for educational purposes only. Consult a SEBI-registered
investment advisor before making financial decisions."

Style:
- Maximum 500 words
- Use ₹ for amounts
- No bullet-point walls
- Warm, encouraging tone

WRITE THE ANSWER NOW (markdown only):"""

    answer = await call_gemini(prompt)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
    insight_page = (
        f"# India Beginner Session: {question[:80]}\n\n{answer}\n\n"
        f"---\n*Sources: {', '.join(consulted)}*\n"
        f"*Flow: beginner_answer_india*\n*Generated: {timestamp} UTC*\n"
        f"*⚠️ Educational only.*\n"
    )
    _iwrite(f"insights/beginner_{timestamp}.md", insight_page)
    _iappend_log(f"beginner | \"{question[:60]}\" | consulted: {', '.join(consulted)}")

    return answer, consulted


# ── Operation 3: Fast health snapshot ────────────────────────────────────────


def india_wiki_health() -> dict:
    """
    Fast, LLM-free staleness snapshot of data/wiki_india/.

    Mirrors core/wiki.wiki_health_snapshot() — same return shape so the UI
    can render both with the same component.

    Returns:
        {
            "checked_at": ISO-8601,
            "total_pages": int,
            "fresh": [...],
            "stale": [...],
            "missing_frontmatter": [...],
            "by_type": {...},
        }
    """
    wiki_root = Path(settings.INDIA_WIKI_DIR)
    now = datetime.now(UTC)
    snapshot: dict = {
        "checked_at": now.isoformat(),
        "total_pages": 0,
        "fresh": [],
        "stale": [],
        "missing_frontmatter": [],
        "by_type": {},
    }

    if not wiki_root.exists():
        return snapshot

    for md_file in wiki_root.rglob("*.md"):
        rel_path = str(md_file.relative_to(wiki_root))
        # Skip auto-generated insight and log files
        if rel_path.startswith("insights/") or rel_path == "log.md":
            continue

        snapshot["total_pages"] += 1

        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[IndiaWikiHealth] Could not read {rel_path}: {e}")
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
                lu = datetime.fromisoformat(str(last_updated_str).replace("Z", "+00:00"))
                if lu.tzinfo is None:
                    lu = lu.replace(tzinfo=UTC)
                age_hours = (now - lu).total_seconds() / 3600.0
            except Exception:
                age_hours = None

        if age_hours is None:
            snapshot["missing_frontmatter"].append(rel_path)
            continue

        entry = {
            "path": rel_path,
            "page_type": page_type,
            "age_hours": round(age_hours, 2),
            "ttl_hours": ttl_hours,
        }
        if age_hours > ttl_hours:
            entry["overdue_hours"] = round(age_hours - ttl_hours, 2)
            snapshot["stale"].append(entry)
        else:
            snapshot["fresh"].append(entry)

    return snapshot
