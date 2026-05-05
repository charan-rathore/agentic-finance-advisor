"""
app/main.py

FastAPI backend serving the React frontend.
Exposes REST endpoints for: profile, chat, market data, calculators, health.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from agents.storage_agent import (  # noqa: E402
    get_latest_prices,
    get_recent_headlines,
    get_recent_insights,
)
from core.calculators import (  # noqa: E402
    elss_tax_savings,
    emergency_fund_target,
    is_calculator_question,
    lumpsum_vs_sip,
    sip_future_value,
    sip_needed_for_goal,
    step_up_sip,
)
from core.faq import faq_match  # noqa: E402
from core.fetchers import fetch_google_news_rss, fetch_vix_and_fear_greed  # noqa: E402
from core.fetchers_india import (  # noqa: E402
    fetch_amfi_nav,
    fetch_india_news_rss,
    fetch_india_prices,
    fetch_rbi_rates,
)
from core.models import UserProfile, init_db  # noqa: E402
from core.nudges import generate_nudges  # noqa: E402
from core.settings import settings  # noqa: E402
from core.trust import get_all_sources, get_page_version_history  # noqa: E402
from core.wiki import (  # noqa: E402
    _compute_confidence,
    beginner_answer,
    detect_beginner_intent,
    lint_wiki,
    query_wiki,
    raw_data_snapshot,
    wiki_health_snapshot,
)
from core.wiki_india import (  # noqa: E402
    _iread,
    beginner_answer_india,
    detect_beginner_intent_india,
    query_india,
)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Finsight API",
        version="2.0.0",
        description="AI Investment Intelligence API for Indian retail investors.",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "capacitor://localhost",   # Android APK (Capacitor)
            "http://localhost",        # iOS WKWebView
            "*",                       # Render preview / APK sideload
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return application


app = create_app()

_engine = init_db(settings.DATABASE_URL)
_Session = sessionmaker(bind=_engine)


# ── Pydantic models ────────────────────────────────────────────────────────


class ProfileCreate(BaseModel):
    name: str
    monthly_income: str
    monthly_sip_budget: str
    risk_tolerance: str
    tax_bracket_pct: float
    primary_goal: str
    horizon_pref: str


class ChatRequest(BaseModel):
    question: str
    hindi: bool = False
    market: str = "india"


class SIPCalcRequest(BaseModel):
    monthly: float
    annual_return_pct: float
    years: int


class GoalCalcRequest(BaseModel):
    target: float
    annual_return_pct: float
    years: int


class ELSSCalcRequest(BaseModel):
    annual_invested: float
    tax_bracket_pct: float


class EmergencyCalcRequest(BaseModel):
    monthly_expenses: float
    months: int = 6


class StepUpSIPRequest(BaseModel):
    base_monthly: float
    annual_step_up_pct: float
    annual_return_pct: float
    years: int


class LumpsumVsSIPRequest(BaseModel):
    amount: float
    annual_return_pct: float
    years: int


# ── Health endpoints ───────────────────────────────────────────────────────


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


# ── Profile endpoints ──────────────────────────────────────────────────────


@app.get("/api/profile")
def get_profile() -> dict[str, Any]:
    with _Session() as s:
        p = s.query(UserProfile).order_by(UserProfile.id.asc()).first()
    if p is None:
        return {"profile": None}
    return {
        "profile": {
            "id": p.id,
            "name": p.name,
            "monthly_income": p.monthly_income,
            "monthly_sip_budget": p.monthly_sip_budget,
            "risk_tolerance": p.risk_tolerance,
            "tax_bracket_pct": p.tax_bracket_pct,
            "primary_goal": p.primary_goal,
            "horizon_pref": p.horizon_pref,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
    }


@app.post("/api/profile")
def create_profile(data: ProfileCreate) -> dict[str, Any]:
    with _Session() as s:
        s.query(UserProfile).delete()
        profile = UserProfile(**data.model_dump())
        s.add(profile)
        s.commit()
        s.refresh(profile)
        return {
            "profile": {
                "id": profile.id,
                "name": profile.name,
                "monthly_income": profile.monthly_income,
                "monthly_sip_budget": profile.monthly_sip_budget,
                "risk_tolerance": profile.risk_tolerance,
                "tax_bracket_pct": profile.tax_bracket_pct,
                "primary_goal": profile.primary_goal,
                "horizon_pref": profile.horizon_pref,
            }
        }


@app.delete("/api/profile")
def delete_profile() -> dict[str, str]:
    with _Session() as s:
        s.query(UserProfile).delete()
        s.commit()
    return {"status": "deleted"}


# ── Market data endpoints ──────────────────────────────────────────────────


@app.get("/api/market/india/prices")
def india_prices() -> dict[str, Any]:
    try:
        prices = asyncio.run(fetch_india_prices())
        return {"prices": prices}
    except Exception as exc:
        return {"prices": [], "error": str(exc)}


@app.get("/api/market/india/nav")
def india_nav() -> dict[str, Any]:
    try:
        nav = asyncio.run(fetch_amfi_nav())
        return {"nav": nav}
    except Exception as exc:
        return {"nav": [], "error": str(exc)}


@app.get("/api/market/india/rbi")
def india_rbi() -> dict[str, Any]:
    try:
        rates = asyncio.run(fetch_rbi_rates())
        return {"rates": rates}
    except Exception as exc:
        return {"rates": {}, "error": str(exc)}


@app.get("/api/market/global/prices")
def global_prices() -> dict[str, Any]:
    prices = get_latest_prices()
    return {"prices": prices}


@app.get("/api/market/global/headlines")
def global_headlines() -> dict[str, Any]:
    headlines = get_recent_headlines(limit=15)
    return {"headlines": headlines}


@app.get("/api/market/global/insights")
def global_insights() -> dict[str, Any]:
    insights = get_recent_insights(limit=10)
    return {"insights": insights}


@app.get("/api/market/global/news")
def global_news_feed() -> dict[str, Any]:
    """Fetch live global market news from multiple RSS sources."""
    import feedparser

    feeds = [
        ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US", "Yahoo Finance"),
        ("https://news.google.com/rss/search?q=stock+market+US&hl=en-US&gl=US&ceid=US:en", "Google News"),
        ("https://news.google.com/rss/search?q=S%26P+500+Nasdaq&hl=en-US&gl=US&ceid=US:en", "Google News"),
        ("https://news.google.com/rss/search?q=global+economy+markets&hl=en-US&gl=US&ceid=US:en", "Google News"),
        ("https://news.google.com/rss/search?q=Federal+Reserve+interest+rates&hl=en-US&gl=US&ceid=US:en", "Google News"),
    ]

    articles: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    for feed_url, default_source in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                source = (entry.get("source") or {}).get("title", default_source) if entry.get("source") else default_source
                articles.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": source,
                    "summary": (entry.get("summary", "") or "")[:300],
                })
        except Exception:
            continue

    articles.sort(key=lambda a: a.get("published", ""), reverse=True)
    return {"articles": articles[:40], "fetched_at": datetime.now(UTC).isoformat()}


@app.get("/api/market/india/news")
def india_news_feed() -> dict[str, Any]:
    """Fetch live India market news from RSS."""
    import feedparser

    feeds = [
        ("https://news.google.com/rss/search?q=Nifty+50+Sensex+stock+market&hl=en-IN&gl=IN&ceid=IN:en", "Google News India"),
        ("https://news.google.com/rss/search?q=Indian+stock+market+NSE+BSE&hl=en-IN&gl=IN&ceid=IN:en", "Google News India"),
        ("https://news.google.com/rss/search?q=RBI+interest+rate+India+economy&hl=en-IN&gl=IN&ceid=IN:en", "Google News India"),
        ("https://news.google.com/rss/search?q=mutual+funds+SIP+India&hl=en-IN&gl=IN&ceid=IN:en", "Google News India"),
    ]

    articles: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    for feed_url, default_source in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                source = (entry.get("source") or {}).get("title", default_source) if entry.get("source") else default_source
                articles.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": source,
                    "summary": (entry.get("summary", "") or "")[:300],
                })
        except Exception:
            continue

    articles.sort(key=lambda a: a.get("published", ""), reverse=True)
    return {"articles": articles[:30], "fetched_at": datetime.now(UTC).isoformat()}


@app.get("/api/market/global/sentiment")
def global_sentiment() -> dict[str, Any]:
    """Fetch VIX and Fear & Greed Index."""
    try:
        result = asyncio.run(fetch_vix_and_fear_greed())
        if result is not None:
            import json as _json
            data = _json.loads(result.read_text(encoding="utf-8"))
            return {"sentiment": data}
    except Exception:
        pass
    return {"sentiment": None}


# ── Chat / AI advisor endpoint ─────────────────────────────────────────────


def _get_profile_dict() -> dict | None:
    with _Session() as s:
        p = s.query(UserProfile).order_by(UserProfile.id.asc()).first()
    if p is None:
        return None
    return {
        "name": p.name,
        "monthly_income": p.monthly_income,
        "monthly_sip_budget": p.monthly_sip_budget,
        "risk_tolerance": p.risk_tolerance,
        "tax_bracket_pct": p.tax_bracket_pct,
        "primary_goal": p.primary_goal,
        "horizon_pref": p.horizon_pref,
    }


def _confidence_for(consulted: list[str], market: str = "india") -> float:
    if not consulted:
        return 0.30
    loaded: dict[str, str] = {}
    for path in consulted:
        try:
            if market == "india":
                content = _iread(path)
            else:
                from core.wiki import _read_wiki_file
                content = _read_wiki_file(path)
            if content:
                loaded[path] = content
        except Exception:
            continue
    return _compute_confidence(consulted, page_contents=loaded)


def _try_demo_cache(question: str) -> dict[str, Any] | None:
    if os.environ.get("DEMO_REPLAY_MODE") != "1":
        return None
    import re as _re
    slug = _re.sub(r"[^a-z0-9]+", "_", question.lower()).strip("_")[:60]
    path = ROOT_DIR / "data" / "demo_cache" / f"{slug}.md"
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    body = parts[2].strip()
    sources: list[str] = []
    import re as _re2
    for line in parts[1].splitlines():
        m = _re2.match(r"\s*-\s*(.+)\s*$", line)
        if m:
            sources.append(m.group(1).strip())
    return {
        "answer": body,
        "sources": sources,
        "confidence": 0.85,
        "fast_path": "demo_cache",
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    profile_dict = _get_profile_dict()
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    cached = _try_demo_cache(question)
    if cached is not None:
        return cached

    calc_result = None
    if is_calculator_question(question):
        calc_result = _auto_calculate(question, profile_dict)

    if req.market == "india":
        hit = faq_match(question)
        if hit is not None and not req.hindi:
            return {
                "answer": hit.answer,
                "sources": [f"data/wiki_india/faq/{hit.slug}.md"],
                "confidence": 0.85,
                "fast_path": "faq",
                "calculator": calc_result,
            }

        try:
            if detect_beginner_intent_india(question):
                ans, sources = asyncio.run(
                    beginner_answer_india(question, profile=profile_dict, hindi=req.hindi)
                )
            else:
                ans, sources = asyncio.run(
                    query_india(question, profile=profile_dict, hindi=req.hindi)
                )
            confidence = _confidence_for(sources, market="india")
            return {
                "answer": ans,
                "sources": sources,
                "confidence": confidence,
                "fast_path": None,
                "calculator": calc_result,
            }
        except Exception as exc:
            return {
                "answer": f"The advisor could not produce an answer: {exc}. Try a simpler phrasing.",
                "sources": [],
                "confidence": 0.0,
                "fast_path": None,
                "calculator": calc_result,
                "error": str(exc),
            }
    else:
        try:
            if detect_beginner_intent(question):
                ans, sources = asyncio.run(beginner_answer(question))
            else:
                ans, sources = asyncio.run(query_wiki(question))
            confidence = _confidence_for(sources, market="us")
            return {
                "answer": ans,
                "sources": sources,
                "confidence": confidence,
                "fast_path": None,
                "calculator": calc_result,
            }
        except Exception as exc:
            return {
                "answer": f"The global advisor failed: {exc}.",
                "sources": [],
                "confidence": 0.0,
                "fast_path": None,
                "calculator": calc_result,
                "error": str(exc),
            }


def _auto_calculate(question: str, profile: dict | None) -> dict | None:
    q = question.lower()
    sip_amount = float((profile or {}).get("monthly_sip_budget_amount") or 5000)
    bracket = float((profile or {}).get("tax_bracket_pct") or 30)

    if "emergency" in q:
        return {"type": "emergency_fund", "result": emergency_fund_target(30000.0, months=6)}
    elif "elss" in q or "80c" in q or "tax sav" in q:
        return {"type": "elss", "result": elss_tax_savings(150000, bracket)}
    elif "goal" in q or "i want to save" in q or "i want to accumulate" in q:
        return {"type": "goal_sip", "result": sip_needed_for_goal(1_000_000, 12.0, 5)}
    else:
        return {"type": "sip_future_value", "result": sip_future_value(sip_amount, 12.0, 10)}


# ── Calculator endpoints ───────────────────────────────────────────────────


@app.post("/api/calc/sip")
def calc_sip(req: SIPCalcRequest) -> dict[str, Any]:
    return sip_future_value(req.monthly, req.annual_return_pct, req.years)


@app.post("/api/calc/goal")
def calc_goal(req: GoalCalcRequest) -> dict[str, Any]:
    return sip_needed_for_goal(req.target, req.annual_return_pct, req.years)


@app.post("/api/calc/elss")
def calc_elss(req: ELSSCalcRequest) -> dict[str, Any]:
    return elss_tax_savings(req.annual_invested, req.tax_bracket_pct)


@app.post("/api/calc/emergency")
def calc_emergency(req: EmergencyCalcRequest) -> dict[str, Any]:
    return emergency_fund_target(req.monthly_expenses, req.months)


@app.post("/api/calc/step-up-sip")
def calc_step_up(req: StepUpSIPRequest) -> dict[str, Any]:
    return step_up_sip(req.base_monthly, req.annual_step_up_pct, req.annual_return_pct, req.years)


@app.post("/api/calc/lumpsum-vs-sip")
def calc_lumpsum_vs_sip(req: LumpsumVsSIPRequest) -> dict[str, Any]:
    return lumpsum_vs_sip(req.amount, req.annual_return_pct, req.years)


# ── Nudges endpoint ────────────────────────────────────────────────────────


@app.post("/api/nudges")
def get_nudges(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    profile_dict = _get_profile_dict()
    nudges = generate_nudges(
        profile=profile_dict,
        recent_questions=body.get("recent_questions", []),
        market=body.get("market"),
    )
    return {"nudges": nudges}


# ── Trust / Sources endpoints ──────────────────────────────────────────────


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    rows = get_all_sources(_engine)
    return {"sources": rows}


@app.get("/api/wiki/history/{page_name:path}")
def wiki_history(page_name: str) -> dict[str, Any]:
    history = get_page_version_history(_engine, page_name)
    return {"history": history}


# ── System health endpoint ─────────────────────────────────────────────────


@app.get("/api/system/health")
def system_health() -> dict[str, Any]:
    snapshot = wiki_health_snapshot()
    raw_snap = raw_data_snapshot()
    return {
        "wiki": {
            "total_pages": snapshot["total_pages"],
            "fresh_count": len(snapshot["fresh"]),
            "stale_count": len(snapshot["stale"]),
            "missing_frontmatter": len(snapshot["missing_frontmatter"]),
            "by_type": snapshot.get("by_type", {}),
            "stale": snapshot["stale"][:20],
            "fresh": snapshot["fresh"][:20],
            "latest_lint_report": snapshot.get("latest_lint_report"),
        },
        "raw_data": raw_snap,
    }


@app.post("/api/system/lint")
def run_lint() -> dict[str, Any]:
    try:
        result = asyncio.run(lint_wiki())
        return {
            "status": "ok",
            "stale_count": len(result["stale_pages"]),
            "contradiction_count": len(result["contradictions"]),
            "needs_refresh": len(result["needs_refresh"]),
            "contradictions": result["contradictions"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Serve React static files in production ─────────────────────────────────

frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
