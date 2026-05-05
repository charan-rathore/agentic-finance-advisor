"""
india_advisor/app.py

Finsight India - A standalone AI investing companion for Indian retail investors.

This is a focused, product-ready version of the India Advisor that can be
deployed independently. It provides:
  - Conversational onboarding with income-aware SIP recommendations
  - AI-powered investment guidance in English and Hindi
  - Real-time NSE market data
  - Deterministic calculators (SIP, ELSS, Goals)
  - FAQ fast-path for common questions
  - Confidence scoring with source citations

To run: streamlit run india_advisor/app.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from agents.storage_agent import get_latest_prices  # noqa: E402
from core.calculators import (  # noqa: E402
    elss_tax_savings,
    emergency_fund_target,
    is_calculator_question,
    sip_future_value,
    sip_needed_for_goal,
)
from core.faq import faq_match  # noqa: E402
from core.fetchers_india import fetch_india_prices  # noqa: E402
from core.models import UserProfile, init_db  # noqa: E402
from core.nudges import generate_nudges  # noqa: E402
from core.settings import settings  # noqa: E402
from core.wiki import _compute_confidence  # noqa: E402
from core.wiki_india import (  # noqa: E402
    _iread,
    beginner_answer_india,
    detect_beginner_intent_india,
    query_india,
)

st.set_page_config(
    page_title="Finsight India - AI Investment Companion",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1100px;
}

/* Brand header */
.fi-brand {
    background: linear-gradient(135deg, #FF9933 0%, #FFFFFF 35%, #138808 100%);
    border-radius: 16px;
    padding: 1.3rem 1.8rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}
.fi-brand h1 {
    margin: 0;
    color: #1a1a2e;
    font-weight: 800;
    font-size: 1.8rem;
    letter-spacing: -0.5px;
}
.fi-brand p {
    margin: 0.3rem 0 0;
    color: #333;
    font-size: 0.92rem;
}

/* Stock cards */
.fi-stock-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 0.75rem;
    margin: 1rem 0;
}
.fi-stock-card {
    background: linear-gradient(145deg, #1e3a5f 0%, #16213e 100%);
    border-radius: 12px;
    padding: 0.85rem 0.9rem;
    text-align: center;
}
.fi-stock-symbol {
    color: #8892b0;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.fi-stock-price {
    color: #e6f1ff;
    font-size: 1.1rem;
    font-weight: 700;
    margin: 0.2rem 0;
}
.fi-stock-change {
    font-size: 0.8rem;
    font-weight: 600;
}
.fi-stock-change.up { color: #00d395; }
.fi-stock-change.down { color: #ff6b6b; }
.fi-stock-change.flat { color: #8892b0; }

/* Badges */
.fi-badge {
    display: inline-block;
    padding: 0.22rem 0.75rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 0.5rem;
    margin-bottom: 0.3rem;
}
.fi-badge-green { background: #d4edda; color: #155724; }
.fi-badge-orange { background: #fff3cd; color: #856404; }
.fi-badge-blue { background: #cce5ff; color: #004085; }
.fi-badge-purple { background: #e2d9f3; color: #5a3d7a; }

/* Profile DNA card */
.fi-dna {
    background: linear-gradient(135deg, #FF9933 0%, #fff 50%, #138808 100%);
    border-radius: 16px;
    padding: 1.5rem;
    margin: 1rem 0;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}
.fi-dna h3 {
    margin: 0 0 0.8rem;
    color: #1a1a2e;
    font-weight: 700;
    font-size: 1.2rem;
}
.fi-dna-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem 1.5rem;
}
.fi-dna-key {
    color: #555;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.fi-dna-val {
    color: #1a1a2e;
    font-weight: 600;
    font-size: 0.95rem;
}

/* Calculator cards */
.fi-calc {
    background: #fff;
    border: 1px solid #e5e5e5;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-top: 0.7rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.fi-calc h4 { margin: 0 0 0.5rem; color: #1e3a5f; font-weight: 700; }
.fi-calc-row { display: flex; justify-content: space-between; padding: 0.35rem 0; border-bottom: 1px dashed #eee; }
.fi-calc-row:last-child { border-bottom: none; }
.fi-calc-key { color: #666; font-size: 0.88rem; }
.fi-calc-val { color: #1a1a2e; font-weight: 600; }

/* Nudges */
.fi-nudge {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-left: 4px solid #138808;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.6rem;
}
.fi-nudge.warn { border-left-color: #fd7e14; }
.fi-nudge.tip { border-left-color: #007bff; }
.fi-nudge h4 { margin: 0 0 0.2rem; font-size: 0.92rem; font-weight: 600; color: #212529; }
.fi-nudge p { margin: 0; font-size: 0.85rem; color: #495057; }

.fi-caption { color: #6c757d; font-size: 0.82rem; }

[data-testid="stMetricValue"] {
    font-size: 1.05rem !important;
    white-space: nowrap !important;
}

@media (max-width: 768px) {
    .fi-dna-grid { grid-template-columns: 1fr; }
    .fi-stock-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)

# ── Brand Header ────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="fi-brand">
        <h1>Finsight India</h1>
        <p>Your AI-powered investment companion. Grounded in SEBI, AMFI & RBI data.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Database Session ────────────────────────────────────────────────────────


@st.cache_resource
def _get_engine():
    return init_db(settings.DATABASE_URL)


_engine = _get_engine()
_Session = sessionmaker(bind=_engine)


def _load_profile() -> UserProfile | None:
    with _Session() as s:
        return s.query(UserProfile).order_by(UserProfile.id.asc()).first()


def _save_profile(data: dict) -> None:
    with _Session() as s:
        s.add(UserProfile(**data))
        s.commit()


def _delete_profile() -> None:
    with _Session() as s:
        s.query(UserProfile).delete()
        s.commit()


def _profile_to_dict(p: UserProfile) -> dict:
    return {
        "name": p.name,
        "monthly_income": p.monthly_income,
        "monthly_sip_budget": p.monthly_sip_budget,
        "risk_tolerance": p.risk_tolerance,
        "tax_bracket_pct": p.tax_bracket_pct,
        "primary_goal": p.primary_goal,
        "horizon_pref": p.horizon_pref,
    }


# ── Data Loaders ────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_india_prices() -> list[dict]:
    return asyncio.run(fetch_india_prices())


# ── Onboarding Configuration ────────────────────────────────────────────────

_INCOME_BRACKETS = [
    "Below INR 25k",
    "INR 25k to 50k",
    "INR 50k to 1L",
    "INR 1L to 2L",
    "Above INR 2L",
]

_INCOME_TO_MAX_SIP = {
    "Below INR 25k": 10000,
    "INR 25k to 50k": 25000,
    "INR 50k to 1L": 50000,
    "INR 1L to 2L": 100000,
    "Above INR 2L": float("inf"),
}

_SIP_BRACKET_VALUES = {
    "Below INR 1k": 1000,
    "INR 1k to 2k": 2000,
    "INR 2k to 5k": 5000,
    "INR 5k to 10k": 10000,
    "INR 10k to 25k": 25000,
    "INR 25k to 50k": 50000,
    "Above INR 50k": float("inf"),
}

_SIP_BRACKETS_ALL = [
    "Below INR 1k",
    "INR 1k to 2k",
    "INR 2k to 5k",
    "INR 5k to 10k",
    "INR 10k to 25k",
    "INR 25k to 50k",
    "Above INR 50k",
]


def _get_sip_options_for_income(income_bracket: str) -> list[str]:
    max_sip = _INCOME_TO_MAX_SIP.get(income_bracket, float("inf"))
    return [
        sip for sip in _SIP_BRACKETS_ALL
        if _SIP_BRACKET_VALUES.get(sip, 0) <= max_sip
    ]


_GOALS = [
    "Build emergency fund",
    "Save tax (80C)",
    "Grow wealth (SIP)",
    "Retirement planning",
    "Child education",
    "Buy a house",
    "Just learning",
]

_RISK_OPTIONS = {
    "low": "Low - I prefer safety over returns",
    "medium": "Medium - I can handle normal market swings",
    "high": "High - I can stay calm during 30% drops",
}

_HORIZON_OPTIONS = {
    "short": "Short (1 year or less)",
    "intermediate": "Medium (2 to 5 years)",
    "long": "Long (5+ years)",
}


def _classify_dna(profile: dict) -> str:
    risk = profile.get("risk_tolerance")
    horizon = profile.get("horizon_pref")
    if risk == "low" or horizon == "short":
        return "Conservative starter"
    if risk == "high" and horizon == "long":
        return "Bold grower"
    return "Balanced builder"


# ── Helpers ────────────────────────────────────────────────────────────────


def _format_inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"INR {amount/10_000_000:.2f} Cr"
    if amount >= 100_000:
        return f"INR {amount/100_000:.2f} L"
    return f"INR {int(amount):,}"


def _format_price(price: float | None) -> str:
    if price is None:
        return "N/A"
    if price >= 10000:
        return f"{price/1000:.1f}K"
    elif price >= 1000:
        return f"{price:,.0f}"
    return f"{price:,.2f}"


def _confidence_badge_html(score: float) -> str:
    if score >= 0.75:
        cls, label = "fi-badge-green", "Grounded"
    elif score >= 0.5:
        cls, label = "fi-badge-orange", "Partial"
    else:
        cls, label = "fi-badge-purple", "Limited"
    return f'<span class="fi-badge {cls}">Confidence: {label}</span>'


def _confidence_for(consulted: list[str]) -> float:
    if not consulted:
        return 0.30
    loaded: dict[str, str] = {}
    for path in consulted:
        try:
            content = _iread(path)
            if content:
                loaded[path] = content
        except Exception:
            continue
    return _compute_confidence(consulted, page_contents=loaded)


# ── Calculator Card ────────────────────────────────────────────────────────


def _calculator_card(question: str, profile: dict | None) -> str | None:
    if not is_calculator_question(question):
        return None

    q = question.lower()
    rows: list[tuple[str, str]] = []
    title = "Quick Calculator"

    sip_amount = float((profile or {}).get("monthly_sip_budget_amount") or 5000)
    bracket = float((profile or {}).get("tax_bracket_pct") or 30)

    if "emergency" in q:
        title = "Emergency Fund Target"
        monthly_expenses = 30000.0
        ef_result = emergency_fund_target(monthly_expenses, months=6)
        rows = [
            ("Monthly essentials", _format_inr(monthly_expenses)),
            ("Target (6 months)", _format_inr(ef_result["target_amount"])),
            ("Suggested split", f"Savings: {_format_inr(ef_result['suggested_split']['savings_account'])}"),
        ]
    elif "elss" in q or "80c" in q or "tax" in q:
        title = "ELSS Tax Savings (Old Regime)"
        elss_result = elss_tax_savings(150000, bracket)
        rows = [
            ("Investment", _format_inr(elss_result["annual_invested"])),
            ("Tax bracket", f"{int(elss_result['tax_bracket_pct'])}%"),
            ("Tax saved", _format_inr(elss_result["tax_saved"])),
            ("Effective cost", _format_inr(elss_result["effective_cost"])),
        ]
    elif "goal" in q or "save" in q:
        title = "Goal SIP (12% return, 5 years)"
        goal_result = sip_needed_for_goal(1_000_000, 12.0, 5)
        rows = [
            ("Target", _format_inr(goal_result["target"])),
            ("Monthly SIP needed", _format_inr(goal_result["monthly_required"])),
            ("Total invested", _format_inr(goal_result["total_invested"])),
        ]
    else:
        title = "SIP Growth (12% return, 10 years)"
        sip_result = sip_future_value(sip_amount, 12.0, 10)
        rows = [
            ("Monthly SIP", _format_inr(sip_result["monthly"])),
            ("Total invested", _format_inr(sip_result["total_invested"])),
            ("Future value", _format_inr(sip_result["future_value"])),
        ]

    rows_html = "".join(
        f'<div class="fi-calc-row"><span class="fi-calc-key">{k}</span>'
        f'<span class="fi-calc-val">{v}</span></div>'
        for k, v in rows
    )
    return f'<div class="fi-calc"><h4>{title}</h4>{rows_html}</div>'


# ── Nudge Rendering ────────────────────────────────────────────────────────


def _render_nudges(profile_dict: dict | None, history: list[str]) -> None:
    nudges = generate_nudges(
        profile=profile_dict,
        recent_questions=history[-5:] if history else [],
        market={"nifty_change_pct": st.session_state.get("nifty_change_pct")},
    )
    for n in nudges:
        kind = "warn" if n["icon"] == "warn" else "tip" if n["icon"] == "tip" else ""
        st.markdown(
            f'<div class="fi-nudge {kind}">'
            f'<h4>{n["title"]}</h4><p>{n["body"]}</p></div>',
            unsafe_allow_html=True,
        )


# ── Onboarding Wizard ────────────────────────────────────────────────────────


def _render_onboarding() -> None:
    st.markdown("### Welcome to Finsight India")
    st.markdown(
        '<p class="fi-caption">Answer a few questions to personalize your experience.</p>',
        unsafe_allow_html=True,
    )

    if "ob_step" not in st.session_state:
        st.session_state.ob_step = 0
        st.session_state.ob_data = {}

    step = st.session_state.ob_step
    st.progress((step) / 5, text=f"Step {min(step + 1, 5)} of 5")

    data = st.session_state.ob_data

    if step == 0:
        with st.chat_message("assistant"):
            st.write("Hi! What should I call you?")
        name = st.text_input("Your name", placeholder="e.g. Priya")
        if st.button("Continue", type="primary", disabled=not name.strip()):
            data["name"] = name.strip()
            st.session_state.ob_step = 1
            st.rerun()

    elif step == 1:
        with st.chat_message("assistant"):
            st.write(f"Nice to meet you, {data.get('name', '')}! What's your monthly income range?")
        income = st.radio("Income range", options=_INCOME_BRACKETS, label_visibility="collapsed")
        if st.button("Continue", type="primary"):
            data["monthly_income"] = income
            st.session_state.ob_step = 2
            st.rerun()

    elif step == 2:
        with st.chat_message("assistant"):
            st.write("How much can you comfortably invest each month?")
        income_selected = data.get("monthly_income", "Above INR 2L")
        sip_options = _get_sip_options_for_income(income_selected)
        sip = st.radio("Investment budget", options=sip_options, label_visibility="collapsed")
        if st.button("Continue", type="primary"):
            data["monthly_sip_budget"] = sip
            st.session_state.ob_step = 3
            st.rerun()

    elif step == 3:
        with st.chat_message("assistant"):
            st.write("How comfortable are you with market fluctuations?")
        risk = st.radio(
            "Risk tolerance",
            options=list(_RISK_OPTIONS.keys()),
            format_func=lambda k: _RISK_OPTIONS[k],
            label_visibility="collapsed",
        )
        with st.chat_message("assistant"):
            st.write("And your investment horizon?")
        horizon = st.radio(
            "Time horizon",
            options=list(_HORIZON_OPTIONS.keys()),
            format_func=lambda k: _HORIZON_OPTIONS[k],
            label_visibility="collapsed",
        )
        if st.button("Continue", type="primary"):
            data["risk_tolerance"] = risk
            data["horizon_pref"] = horizon
            st.session_state.ob_step = 4
            st.rerun()

    elif step == 4:
        with st.chat_message("assistant"):
            st.write("Finally, what's your primary financial goal?")
        goal = st.selectbox("Primary goal", options=_GOALS, label_visibility="collapsed")
        bracket = st.selectbox(
            "Your tax bracket",
            options=[0.0, 5.0, 20.0, 30.0],
            index=3,
            format_func=lambda x: f"{int(x)}%",
            help="Used to personalize ELSS recommendations",
        )
        if st.button("Finish Setup", type="primary"):
            data["primary_goal"] = goal
            data["tax_bracket_pct"] = float(bracket or 30.0)
            st.session_state.ob_step = 5
            st.rerun()

    elif step == 5:
        dna = _classify_dna(data)
        st.markdown(
            f"""
            <div class="fi-dna">
                <h3>Your Investment Profile: {dna}</h3>
                <div class="fi-dna-grid">
                    <span class="fi-dna-key">Name</span>
                    <span class="fi-dna-val">{data.get('name','')}</span>
                    <span class="fi-dna-key">Income</span>
                    <span class="fi-dna-val">{data.get('monthly_income','')}</span>
                    <span class="fi-dna-key">SIP Budget</span>
                    <span class="fi-dna-val">{data.get('monthly_sip_budget','')}</span>
                    <span class="fi-dna-key">Risk Comfort</span>
                    <span class="fi-dna-val">{data.get('risk_tolerance','').title()}</span>
                    <span class="fi-dna-key">Horizon</span>
                    <span class="fi-dna-val">{_HORIZON_OPTIONS.get(data.get('horizon_pref',''),'')}</span>
                    <span class="fi-dna-key">Goal</span>
                    <span class="fi-dna-val">{data.get('primary_goal','')}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_a, col_b = st.columns([3, 1])
        if col_a.button("Start Using Finsight", type="primary"):
            _save_profile({
                "name": data["name"],
                "monthly_income": data["monthly_income"],
                "monthly_sip_budget": data["monthly_sip_budget"],
                "risk_tolerance": data["risk_tolerance"],
                "tax_bracket_pct": data["tax_bracket_pct"],
                "primary_goal": data["primary_goal"],
                "horizon_pref": data["horizon_pref"],
            })
            for key in ("ob_step", "ob_data"):
                st.session_state.pop(key, None)
            st.rerun()
        if col_b.button("Edit"):
            st.session_state.ob_step = 0
            st.rerun()


# ── Answer Producer ────────────────────────────────────────────────────────


def _produce_answer(question: str, profile_dict: dict, hindi_mode: bool) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "answer": "",
        "sources": [],
        "confidence": 0.30,
        "fast_path": None,
        "calc_html": None,
    }

    hit = faq_match(question)
    if hit is not None and not hindi_mode:
        bundle["answer"] = hit.answer
        bundle["sources"] = [f"data/wiki_india/faq/{hit.slug}.md"]
        bundle["confidence"] = 0.85
        bundle["fast_path"] = "faq"

    bundle["calc_html"] = _calculator_card(question, profile_dict)

    if bundle["fast_path"] is None:
        try:
            if detect_beginner_intent_india(question):
                ans, sources = asyncio.run(
                    beginner_answer_india(question, profile=profile_dict, hindi=hindi_mode)
                )
            else:
                ans, sources = asyncio.run(
                    query_india(question, profile=profile_dict, hindi=hindi_mode)
                )
            bundle["answer"] = ans
            bundle["sources"] = sources
            bundle["confidence"] = _confidence_for(sources)
        except Exception as exc:
            bundle["answer"] = f"Sorry, I couldn't process that: {exc}"
            bundle["confidence"] = 0.0

    return bundle


def _render_assistant_message(bundle: dict[str, Any]) -> None:
    badge = _confidence_badge_html(bundle["confidence"])
    fast_badge = ""
    if bundle.get("fast_path") == "faq":
        fast_badge = '<span class="fi-badge fi-badge-blue">Instant Answer</span>'
    st.markdown(badge + fast_badge, unsafe_allow_html=True)
    if bundle.get("calc_html"):
        st.markdown(bundle["calc_html"], unsafe_allow_html=True)
    if bundle["answer"]:
        st.markdown(bundle["answer"])
    if bundle["sources"]:
        with st.expander(f"Sources ({len(bundle['sources'])})"):
            for s in bundle["sources"]:
                st.markdown(f"- `{s}`")


# ── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Finsight India")

    hindi_mode = st.toggle(
        "Reply in Hindi",
        value=False,
        help="Get responses in Devanagari script",
    )

    st.divider()
    st.caption(
        "AI-powered investment intelligence for Indian investors. "
        "Grounded in SEBI, AMFI & RBI data. Educational use only."
    )

    if _load_profile() is not None:
        st.divider()
        if st.button("Reset Profile"):
            _delete_profile()
            for k in list(st.session_state.keys()):
                if str(k).startswith("ob_") or str(k).endswith("_messages"):
                    del st.session_state[k]
            st.rerun()


# ── Main Flow ────────────────────────────────────────────────────────────────

profile_row = _load_profile()

if profile_row is None:
    _render_onboarding()
    st.stop()

profile_dict = _profile_to_dict(profile_row)
dna = _classify_dna(profile_dict)

# Profile badges
st.markdown(
    f'<span class="fi-badge fi-badge-blue">{profile_row.name} · {dna}</span> '
    f'<span class="fi-badge fi-badge-green">Goal: {profile_row.primary_goal}</span> '
    f'<span class="fi-badge fi-badge-purple">SIP: {profile_row.monthly_sip_budget}</span>',
    unsafe_allow_html=True,
)

# ── Market Overview ────────────────────────────────────────────────────────

st.subheader("Market Overview")

try:
    india_prices = _load_india_prices()
    if india_prices:
        usable_pcts = [r["change_pct"] for r in india_prices if r.get("change_pct") is not None]
        any_live = any(r.get("data_label") == "Live" for r in india_prices)

        if usable_pcts:
            avg_pct = sum(usable_pcts) / len(usable_pcts)
            st.session_state["nifty_change_pct"] = avg_pct

            if not any_live:
                st.info("Markets closed. Showing last available prices.")
            elif avg_pct > 0.25:
                st.success(f"Markets up {avg_pct:+.2f}% on average")
            elif avg_pct < -0.25:
                st.warning(f"Markets down {avg_pct:+.2f}% on average")
            else:
                st.info(f"Markets flat ({avg_pct:+.2f}%)")

        cols = st.columns(5)
        for i, r in enumerate(india_prices[:10]):
            col = cols[i % 5]
            symbol = r["symbol"].replace(".NS", "")
            price = r.get("price_inr")
            pct = r.get("change_pct")

            with col:
                st.metric(
                    label=symbol,
                    value=f"INR {_format_price(price)}",
                    delta=f"{pct:+.2f}%" if pct else None,
                    help=f"Full: INR {price:,.2f}" if price else "N/A",
                )
    else:
        st.info("Market data loading...")
except Exception as exc:
    st.warning(f"Market data unavailable: {type(exc).__name__}")

st.divider()

# ── Chat Interface ────────────────────────────────────────────────────────

st.subheader("Ask Finsight")

if "india_messages" not in st.session_state:
    st.session_state.india_messages = []

history = [m["content"] for m in st.session_state.india_messages if m["role"] == "user"]
_render_nudges(profile_dict, history)

if not st.session_state.india_messages:
    st.markdown('<p class="fi-caption">Try one of these:</p>', unsafe_allow_html=True)
    chip_cols = st.columns(2)
    chips = [
        "I earn INR 50k a month, where should I start?",
        "ELSS vs PPF - which is better for me?",
        "How much emergency fund do I need?",
        "Market gir gaya, SIP band karu?",
    ]
    chip_clicked = None
    for i, chip in enumerate(chips):
        if chip_cols[i % 2].button(chip, key=f"chip_{i}", use_container_width=True):
            chip_clicked = chip
    if chip_clicked:
        st.session_state.pending_question = chip_clicked
        st.rerun()

for m in st.session_state.india_messages:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
        else:
            _render_assistant_message(m)

pending = st.session_state.pop("pending_question", None)
user_q = pending or st.chat_input("Ask about SIP, ELSS, mutual funds, tax saving...")

if user_q:
    st.session_state.india_messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)
    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            bundle = _produce_answer(user_q, profile_dict, hindi_mode)
        _render_assistant_message(bundle)
    st.session_state.india_messages.append({"role": "assistant", **bundle})

# ── Quick Tools ────────────────────────────────────────────────────────────

with st.expander("Quick Calculators"):
    tcol1, tcol2 = st.columns(2)

    with tcol1:
        st.markdown("**SIP Calculator**")
        sip_amt = st.number_input("Monthly SIP (INR)", min_value=500, value=5000, step=500)
        sip_yrs = st.slider("Years", 1, 30, 10)
        sip_ret = st.slider("Expected Return (%)", 6.0, 18.0, 12.0, 0.5)
        sip_res = sip_future_value(float(sip_amt), float(sip_ret), int(sip_yrs))
        st.metric("Future Value", _format_inr(sip_res["future_value"]))
        st.caption(f"Total invested: {_format_inr(sip_res['total_invested'])}")

    with tcol2:
        st.markdown("**ELSS Tax Savings**")
        elss_amt = st.number_input("Annual Investment", min_value=0, max_value=300000, value=150000, step=10000)
        elss_bracket = st.select_slider("Tax Bracket", options=[0, 5, 10, 15, 20, 25, 30], value=30)
        elss_res = elss_tax_savings(float(elss_amt), float(elss_bracket))
        st.metric("Tax Saved", _format_inr(elss_res["tax_saved"]))
        st.caption(f"Deduction: {_format_inr(elss_res['deduction'])}")

# ── Footer ────────────────────────────────────────────────────────────────

st.markdown(
    f'<p class="fi-caption" style="text-align:center;margin-top:2rem;">'
    f"Finsight India is for educational purposes only. Not financial advice. "
    f"Consult a SEBI-registered advisor. {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
    f"</p>",
    unsafe_allow_html=True,
)
