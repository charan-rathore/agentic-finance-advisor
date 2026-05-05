"""
ui/app.py

Streamlit dashboard for Paisa Pal / Niveshak AI.

Features in this build:
* Conversational onboarding wizard (gates the app until UserProfile is created)
* Streamlit chat input with persisted message history per market
* FAQ fast-path (data/wiki_india/faq/) served without any LLM call
* Calculator card auto-detect for SIP / goal / ELSS / emergency-fund intents
* Confidence badge (Grounded / Partial / Limited) instead of raw float
* Behavioural nudge bar above the chat
* Custom CSS for a clean, professional look (Inter font, India palette)
* Tabs: India Advisor (default), Global Markets, Sources & History, System Health

To run locally:  streamlit run ui/app.py
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

# Streamlit must run as a top-level script, so sys.path setup precedes the
# project imports below. Ruff's E402 rule does not fit that pattern.
from sqlalchemy.orm import sessionmaker  # noqa: E402

from agents.storage_agent import (  # noqa: E402
    get_latest_prices,
    get_recent_headlines,
    get_recent_insights,
)
from core.calculators import (  # noqa: E402
    elss_tax_savings,
    emergency_fund_target,
    is_calculator_question,
    sip_future_value,
    sip_needed_for_goal,
)
from core.faq import faq_match  # noqa: E402
from core.fetchers_india import (  # noqa: E402
    fetch_amfi_nav,
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

st.set_page_config(
    page_title="Finsight - AI Investment Intelligence",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for a professional, minimal look ──────────────────────────────

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* Global tweaks */
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2.5rem;
    max-width: 1280px;
}

/* Brand header banner - Modern gradient */
.fs-brand {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%);
    border-radius: 16px;
    padding: 1.2rem 1.6rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(30,58,95,0.15);
    position: relative;
    overflow: hidden;
}
.fs-brand::before {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 200px;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05));
}
.fs-brand h1 {
    margin: 0;
    color: #ffffff;
    font-weight: 800;
    font-size: 1.65rem;
    letter-spacing: -0.5px;
}
.fs-brand p {
    margin: 0.3rem 0 0;
    color: rgba(255,255,255,0.85);
    font-size: 0.92rem;
}

/* Stock card styling - Full visibility */
.fs-stock-card {
    background: linear-gradient(145deg, #1a1a2e 0%, #16213e 100%);
    border-radius: 12px;
    padding: 0.9rem 1rem;
    text-align: center;
    min-width: 140px;
}
.fs-stock-symbol {
    color: #8892b0;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.3rem;
}
.fs-stock-price {
    color: #e6f1ff;
    font-size: 1.15rem;
    font-weight: 700;
    white-space: nowrap;
}
.fs-stock-change {
    font-size: 0.85rem;
    font-weight: 600;
    margin-top: 0.2rem;
}
.fs-stock-change.positive { color: #00d395; }
.fs-stock-change.negative { color: #ff6b6b; }
.fs-stock-change.neutral { color: #8892b0; }

/* Confidence and trust badges */
.fs-badge {
    display: inline-block;
    padding: 0.22rem 0.75rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 0.5rem;
    margin-bottom: 0.3rem;
}
.fs-badge-green { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.fs-badge-amber { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
.fs-badge-red   { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
.fs-badge-blue  { background: #cce5ff; color: #004085; border: 1px solid #b8daff; }
.fs-badge-purple { background: #e2d9f3; color: #5a3d7a; border: 1px solid #d4c4e3; }

/* Nudge cards */
.fs-nudge {
    background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
    border: 1px solid #e9ecef;
    border-left: 4px solid #28a745;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.7rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.fs-nudge.warn { border-left-color: #fd7e14; }
.fs-nudge.tip  { border-left-color: #007bff; }
.fs-nudge h4 {
    margin: 0 0 0.3rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: #212529;
}
.fs-nudge p {
    margin: 0;
    font-size: 0.87rem;
    color: #495057;
    line-height: 1.5;
}

/* Calculator result card */
.fs-calc {
    background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
    border: 1px solid #dee2e6;
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
    margin-top: 0.7rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.fs-calc h4 { margin-top: 0; font-size: 1.05rem; font-weight: 700; color: #1e3a5f; }
.fs-calc-row { display: flex; justify-content: space-between; padding: 0.4rem 0; border-bottom: 1px dashed #e9ecef; }
.fs-calc-row:last-child { border-bottom: none; }
.fs-calc-key { color: #6c757d; font-size: 0.88rem; }
.fs-calc-val { color: #212529; font-weight: 600; font-size: 0.95rem; }

/* Investment DNA card */
.fs-dna {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
    border-radius: 16px;
    padding: 1.5rem 1.8rem;
    margin: 1rem 0;
    box-shadow: 0 6px 24px rgba(30,58,95,0.2);
    color: #ffffff;
}
.fs-dna h3 { margin: 0 0 0.6rem; color: #ffffff; font-weight: 700; font-size: 1.25rem; }
.fs-dna .fs-dna-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem 1.5rem; margin-top: 0.7rem; }
.fs-dna .fs-dna-key { color: rgba(255,255,255,0.7); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; }
.fs-dna .fs-dna-val { color: #ffffff; font-weight: 600; font-size: 1rem; }

/* Market overview grid */
.fs-market-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.8rem;
    margin: 1rem 0;
}

/* Subtler captions */
.fs-caption { color: #6c757d; font-size: 0.83rem; }

/* Question chips */
.fs-chip {
    background: linear-gradient(135deg, #e9ecef 0%, #f8f9fa 100%);
    border: 1px solid #dee2e6;
    border-radius: 20px;
    padding: 0.5rem 1rem;
    font-size: 0.88rem;
    color: #495057;
    cursor: pointer;
    transition: all 0.2s ease;
}
.fs-chip:hover {
    background: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
    color: #ffffff;
    border-color: #007bff;
}

/* Reduce streamlit defaults */
[data-testid="stDataFrame"] { font-size: 0.88rem; }
.stTabs [data-baseweb="tab"] { font-weight: 600; }

/* Hide Streamlit metric label overflow */
[data-testid="stMetricValue"] {
    font-size: 1rem !important;
    white-space: nowrap !important;
    overflow: visible !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
}

/* Responsive */
@media (max-width: 768px) {
    .fs-dna .fs-dna-grid { grid-template-columns: 1fr; }
    .fs-market-grid { grid-template-columns: repeat(2, 1fr); }
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    .fs-brand h1 { font-size: 1.35rem; }
}

/* Legacy class mappings for backward compatibility */
.pp-badge { display: inline-block; padding: 0.22rem 0.75rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; margin-right: 0.5rem; margin-bottom: 0.3rem; }
.pp-badge-green { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.pp-badge-amber { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
.pp-badge-red   { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
.pp-badge-blue  { background: #cce5ff; color: #004085; border: 1px solid #b8daff; }
.pp-nudge { background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); border: 1px solid #e9ecef; border-left: 4px solid #28a745; border-radius: 10px; padding: 0.9rem 1.1rem; margin-bottom: 0.7rem; }
.pp-nudge.warn { border-left-color: #fd7e14; }
.pp-nudge.tip  { border-left-color: #007bff; }
.pp-nudge h4 { margin: 0 0 0.3rem; font-size: 0.95rem; font-weight: 600; color: #212529; }
.pp-nudge p { margin: 0; font-size: 0.87rem; color: #495057; line-height: 1.5; }
.pp-calc { background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); border: 1px solid #dee2e6; border-radius: 12px; padding: 1.1rem 1.3rem; margin-top: 0.7rem; }
.pp-calc h4 { margin-top: 0; font-size: 1.05rem; font-weight: 700; color: #1e3a5f; }
.pp-calc-row { display: flex; justify-content: space-between; padding: 0.4rem 0; border-bottom: 1px dashed #e9ecef; }
.pp-calc-row:last-child { border-bottom: none; }
.pp-calc-key { color: #6c757d; font-size: 0.88rem; }
.pp-calc-val { color: #212529; font-weight: 600; font-size: 0.95rem; }
.pp-dna { background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); border-radius: 16px; padding: 1.5rem 1.8rem; margin: 1rem 0; box-shadow: 0 6px 24px rgba(30,58,95,0.2); color: #ffffff; border: none; }
.pp-dna h3 { margin: 0 0 0.6rem; color: #ffffff; font-weight: 700; font-size: 1.25rem; }
.pp-dna .pp-dna-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem 1.5rem; margin-top: 0.7rem; }
.pp-dna .pp-dna-key { color: rgba(255,255,255,0.7); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; }
.pp-dna .pp-dna-val { color: #ffffff; font-weight: 600; font-size: 1rem; }
.pp-caption { color: #6c757d; font-size: 0.83rem; }
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)

# ── Brand header ────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="fs-brand">
        <h1>Finsight</h1>
        <p>AI-powered investment intelligence. Grounded in SEBI, AMFI & RBI data. Educational use only.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── DB session ──────────────────────────────────────────────────────────────


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


# ── India market loaders (cached) ───────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_india_prices() -> list[dict]:
    return asyncio.run(fetch_india_prices())


@st.cache_data(ttl=3600)
def _load_amfi_nav() -> list[dict]:
    return asyncio.run(fetch_amfi_nav())


@st.cache_data(ttl=3600)
def _load_rbi_rates() -> dict:
    return asyncio.run(fetch_rbi_rates())


# ── Confidence badge ────────────────────────────────────────────────────────


def _confidence_badge_html(score: float) -> str:
    if score >= 0.75:
        cls, label = "pp-badge-green", "Grounded"
    elif score >= 0.5:
        cls, label = "pp-badge-amber", "Partial"
    else:
        cls, label = "pp-badge-red", "Limited"
    return (
        f'<span class="pp-badge {cls}" title="Confidence score: {score:.2f}">'
        f"Confidence: {label}</span>"
    )


def _confidence_for(consulted: list[str], market: str = "india") -> float:
    """Compute a confidence score by re-reading the consulted pages."""
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


# ── Nudge rendering ─────────────────────────────────────────────────────────


def _render_nudges(profile_dict: dict | None, history: list[str]) -> None:
    nudges = generate_nudges(
        profile=profile_dict,
        recent_questions=history[-5:] if history else [],
        market={"nifty_change_pct": st.session_state.get("nifty_change_pct")},
    )
    for n in nudges:
        kind = "warn" if n["icon"] == "warn" else "tip" if n["icon"] == "tip" else ""
        st.markdown(
            f'<div class="pp-nudge {kind}">'
            f'<h4>{n["title"]}</h4><p>{n["body"]}</p>'
            f"</div>",
            unsafe_allow_html=True,
        )


# ── Calculator card ─────────────────────────────────────────────────────────


def _format_inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"INR {amount/10_000_000:.2f} crore"
    if amount >= 100_000:
        return f"INR {amount/100_000:.2f} lakh"
    return f"INR {int(amount):,}"


def _calculator_card(question: str, profile: dict | None) -> str | None:
    """Auto-detect calculator intent, return an HTML card or None."""
    if not is_calculator_question(question):
        return None

    q = question.lower()
    rows: list[tuple[str, str]] = []
    title = "Quick calculator"

    sip_amount = float((profile or {}).get("monthly_sip_budget_amount") or 5000)
    bracket = float((profile or {}).get("tax_bracket_pct") or 30)

    if "emergency" in q:
        title = "Emergency fund target"
        # Heuristic: assume monthly_expenses ~ 60% of income placeholder
        monthly_expenses = 30000.0
        ef_result = emergency_fund_target(monthly_expenses, months=6)
        rows = [
            ("Monthly essentials assumed", _format_inr(monthly_expenses)),
            ("Target (6 months cover)", _format_inr(ef_result["target_amount"])),
            (
                "Suggested split",
                f"Savings {_format_inr(ef_result['suggested_split']['savings_account'])}, "
                f"Liquid fund {_format_inr(ef_result['suggested_split']['liquid_fund'])}, "
                f"Short-term FD {_format_inr(ef_result['suggested_split']['short_term_fd'])}",
            ),
        ]
    elif "elss" in q or "80c" in q or "tax sav" in q or "tax bach" in q:
        title = "ELSS tax saving (80C, old regime)"
        elss_result = elss_tax_savings(150000, bracket)
        rows = [
            ("Investment", _format_inr(elss_result["annual_invested"])),
            ("Tax bracket", f"{int(elss_result['tax_bracket_pct'])}%"),
            ("Eligible deduction", _format_inr(elss_result["deduction"])),
            ("Tax saved", _format_inr(elss_result["tax_saved"])),
            ("Effective cost", _format_inr(elss_result["effective_cost"])),
        ]
    elif "goal" in q or "i want to save" in q or "i want to accumulate" in q:
        title = "Goal SIP (assumes 12 percent return, 5 years)"
        goal_result = sip_needed_for_goal(1_000_000, 12.0, 5)
        rows = [
            ("Target", _format_inr(goal_result["target"])),
            ("Horizon", f"{goal_result['years']} years"),
            ("Monthly SIP needed", _format_inr(goal_result["monthly_required"])),
            ("Total invested", _format_inr(goal_result["total_invested"])),
            ("Estimated returns", _format_inr(goal_result["estimated_returns"])),
        ]
    else:
        title = "SIP future value (assumes 12 percent return, 10 years)"
        sip_result = sip_future_value(sip_amount, 12.0, 10)
        rows = [
            ("Monthly SIP", _format_inr(sip_result["monthly"])),
            ("Horizon", f"{sip_result['years']} years"),
            ("Total invested", _format_inr(sip_result["total_invested"])),
            ("Estimated returns", _format_inr(sip_result["estimated_returns"])),
            ("Future value", _format_inr(sip_result["future_value"])),
        ]

    rows_html = "".join(
        f'<div class="pp-calc-row">'
        f'<span class="pp-calc-key">{k}</span>'
        f'<span class="pp-calc-val">{v}</span></div>'
        for k, v in rows
    )
    return (
        f'<div class="pp-calc"><h4>{title}</h4>{rows_html}'
        f'<p class="pp-caption" style="margin-top:0.5rem">Numbers are illustrative. '
        f"Actual returns vary with the market.</p></div>"
    )


# ── Onboarding wizard ────────────────────────────────────────────────────────

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
    """Return SIP options that make sense for the given income bracket."""
    max_sip = _INCOME_TO_MAX_SIP.get(income_bracket, float("inf"))
    return [
        sip for sip in _SIP_BRACKETS_ALL
        if _SIP_BRACKET_VALUES.get(sip, 0) <= max_sip
    ]
_GOALS = [
    "Build emergency fund",
    "Save tax (80C)",
    "Grow wealth (SIP)",
    "Retirement / NPS",
    "Child education",
    "Buy a house",
    "Just learning",
]
_RISK_OPTIONS = {
    "low": "Low. I prefer safety over higher returns.",
    "medium": "Medium. I can stomach normal market swings.",
    "high": "High. I can hold through 30% drawdowns without panic.",
}
_HORIZON_OPTIONS = {
    "short": "Short (1 year or less)",
    "intermediate": "Medium (2 to 5 years)",
    "long": "Long (5 plus years)",
}


def _profile_label(value: str, options: dict[str, str]) -> str:
    return options.get(value, value)


def _classify_dna(profile: dict) -> str:
    risk = profile.get("risk_tolerance")
    horizon = profile.get("horizon_pref")
    if risk == "low" or horizon == "short":
        return "Conservative starter"
    if risk == "high" and horizon == "long":
        return "Bold grower"
    return "Balanced builder"


def _render_onboarding() -> None:
    """Conversational onboarding wizard. Saves profile and reruns when done."""
    st.markdown("### Welcome to Finsight")
    st.markdown(
        '<p class="fs-caption">Answer five quick questions so we can '
        "personalise your investment insights. Takes about a minute.</p>",
        unsafe_allow_html=True,
    )

    if "ob_step" not in st.session_state:
        st.session_state.ob_step = 0
        st.session_state.ob_data = {}

    step = st.session_state.ob_step
    progress_pct = (step) / 5
    st.progress(progress_pct, text=f"Step {min(step + 1, 5)} of 5")

    data = st.session_state.ob_data

    # Render previously answered prompts
    if data.get("name"):
        with st.chat_message("assistant"):
            st.write(f"Got it. Hello, {data['name']}.")
    if data.get("monthly_income"):
        with st.chat_message("assistant"):
            st.write(f"Income range noted: {data['monthly_income']}.")
    if data.get("monthly_sip_budget"):
        with st.chat_message("assistant"):
            st.write(f"Comfortable monthly investment: {data['monthly_sip_budget']}.")
    if data.get("risk_tolerance"):
        with st.chat_message("assistant"):
            st.write(
                f"Risk comfort: {_profile_label(data['risk_tolerance'], _RISK_OPTIONS)}"
            )
    if data.get("horizon_pref"):
        with st.chat_message("assistant"):
            st.write(
                f"Time horizon: {_profile_label(data['horizon_pref'], _HORIZON_OPTIONS)}"
            )

    # Step prompts
    if step == 0:
        with st.chat_message("assistant"):
            st.write("First, what should I call you?")
        name = st.text_input("Your name", value="", placeholder="e.g. Priya")
        if st.button("Continue", type="primary", disabled=not name.strip()):
            data["name"] = name.strip()
            st.session_state.ob_step = 1
            st.rerun()

    elif step == 1:
        with st.chat_message("assistant"):
            st.write("Roughly, what is your monthly take-home income?")
        income = st.radio(
            "Monthly income range",
            options=_INCOME_BRACKETS,
            label_visibility="collapsed",
        )
        if st.button("Continue", type="primary"):
            data["monthly_income"] = income
            st.session_state.ob_step = 2
            st.rerun()

    elif step == 2:
        with st.chat_message("assistant"):
            st.write("How much can you comfortably set aside to invest each month?")
        income_selected = data.get("monthly_income", "Above INR 2L")
        sip_options = _get_sip_options_for_income(income_selected)
        sip = st.radio(
            "Monthly investment budget",
            options=sip_options,
            label_visibility="collapsed",
        )
        if st.button("Continue", type="primary"):
            data["monthly_sip_budget"] = sip
            st.session_state.ob_step = 3
            st.rerun()

    elif step == 3:
        with st.chat_message("assistant"):
            st.write("How comfortable are you with market ups and downs?")
        risk_keys = list(_RISK_OPTIONS.keys())
        risk_val = st.radio(
            "Risk profile",
            options=risk_keys,
            format_func=lambda k: _RISK_OPTIONS[k],
            label_visibility="collapsed",
        )
        with st.chat_message("assistant"):
            st.write("And the time horizon for the goal you have in mind?")
        horizon_keys = list(_HORIZON_OPTIONS.keys())
        horizon_val = st.radio(
            "Time horizon",
            options=horizon_keys,
            format_func=lambda k: _HORIZON_OPTIONS[k],
            label_visibility="collapsed",
        )
        if st.button("Continue", type="primary"):
            data["risk_tolerance"] = risk_val
            data["horizon_pref"] = horizon_val
            st.session_state.ob_step = 4
            st.rerun()

    elif step == 4:
        with st.chat_message("assistant"):
            st.write("Last one. What is your primary financial goal right now?")
        goal = st.selectbox("Primary goal", options=_GOALS, label_visibility="collapsed")
        bracket = st.selectbox(
            "Income tax slab",
            options=[0.0, 5.0, 20.0, 30.0],
            index=3,
            format_func=lambda x: f"{int(x)}%",
            help="Marginal income tax rate, used to personalise ELSS or NPS suggestions.",
        )
        if st.button("Finish setup", type="primary"):
            data["primary_goal"] = goal
            data["tax_bracket_pct"] = float(bracket or 30.0)
            st.session_state.ob_step = 5
            st.rerun()

    elif step == 5:
        # Summary card and persist
        dna = _classify_dna(data)
        st.markdown(
            f"""
            <div class="pp-dna">
                <h3>Your Investment DNA: {dna}</h3>
                <div class="pp-dna-grid">
                    <span class="pp-dna-key">Name</span>
                    <span class="pp-dna-val">{data.get('name','')}</span>
                    <span class="pp-dna-key">Monthly income</span>
                    <span class="pp-dna-val">{data.get('monthly_income','')}</span>
                    <span class="pp-dna-key">SIP budget</span>
                    <span class="pp-dna-val">{data.get('monthly_sip_budget','')}</span>
                    <span class="pp-dna-key">Risk comfort</span>
                    <span class="pp-dna-val">{_profile_label(data.get('risk_tolerance',''), _RISK_OPTIONS).split('.')[0]}</span>
                    <span class="pp-dna-key">Time horizon</span>
                    <span class="pp-dna-val">{_profile_label(data.get('horizon_pref',''), _HORIZON_OPTIONS)}</span>
                    <span class="pp-dna-key">Goal</span>
                    <span class="pp-dna-val">{data.get('primary_goal','')}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_a, col_b = st.columns([3, 1])
        if col_a.button("Save and start", type="primary"):
            _save_profile(
                {
                    "name": data["name"],
                    "monthly_income": data["monthly_income"],
                    "monthly_sip_budget": data["monthly_sip_budget"],
                    "risk_tolerance": data["risk_tolerance"],
                    "tax_bracket_pct": data["tax_bracket_pct"],
                    "primary_goal": data["primary_goal"],
                    "horizon_pref": data["horizon_pref"],
                }
            )
            for key in ("ob_step", "ob_data"):
                st.session_state.pop(key, None)
            st.rerun()
        if col_b.button("Edit answers"):
            st.session_state.ob_step = 0
            st.rerun()


# ── Chat answer producer ────────────────────────────────────────────────────


def _try_demo_cache(question: str) -> dict[str, Any] | None:
    """When DEMO_REPLAY_MODE=1, look up a pre-rendered answer to avoid live LLM."""
    if os.environ.get("DEMO_REPLAY_MODE") != "1":
        return None
    import re as _re

    slug = _re.sub(r"[^a-z0-9]+", "_", question.lower()).strip("_")[:60]
    path = (
        ROOT_DIR / "data" / "demo_cache" / f"{slug}.md"
        if (ROOT_DIR / "data" / "demo_cache" / f"{slug}.md").exists()
        else None
    )
    if path is None:
        return None
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    body = parts[2].strip()
    sources: list[str] = []
    for line in parts[1].splitlines():
        m = _re.match(r"\s*-\s*(.+)\s*$", line)
        if m:
            sources.append(m.group(1).strip())
    return {
        "answer": body,
        "sources": sources,
        "confidence": 0.85,
        "fast_path": "demo_cache",
        "calc_html": None,
    }


def _produce_answer(
    question: str,
    profile_dict: dict,
    hindi_mode: bool,
    market: str = "india",
) -> dict[str, Any]:
    """Return a structured answer bundle for the chat handler."""
    cached = _try_demo_cache(question)
    if cached is not None:
        return cached

    bundle: dict[str, Any] = {
        "answer": "",
        "sources": [],
        "confidence": 0.30,
        "fast_path": None,
        "calc_html": None,
    }

    if market == "india":
        # 1. FAQ fast-path (zero LLM cost)
        hit = faq_match(question)
        if hit is not None and not hindi_mode:
            bundle["answer"] = hit.answer
            bundle["sources"] = [
                f"data/wiki_india/faq/{hit.slug}.md"
            ]
            bundle["confidence"] = 0.85
            bundle["fast_path"] = "faq"

        # 2. Calculator card (always render in addition if intent matches)
        bundle["calc_html"] = _calculator_card(question, profile_dict)

        # 3. If FAQ hit, skip Gemini. Otherwise call wiki_india.
        if bundle["fast_path"] is None:
            try:
                if detect_beginner_intent_india(question):
                    ans, sources = asyncio.run(
                        beginner_answer_india(
                            question, profile=profile_dict, hindi=hindi_mode
                        )
                    )
                else:
                    ans, sources = asyncio.run(
                        query_india(question, profile=profile_dict, hindi=hindi_mode)
                    )
                bundle["answer"] = ans
                bundle["sources"] = sources
                bundle["confidence"] = _confidence_for(sources, market="india")
            except Exception as exc:
                bundle["answer"] = (
                    f"The advisor could not produce an answer: {exc}. "
                    "Try a simpler phrasing or check the System Health tab."
                )
                bundle["confidence"] = 0.0
    else:  # global / US
        try:
            if detect_beginner_intent(question):
                ans, sources = asyncio.run(beginner_answer(question))
            else:
                ans, sources = asyncio.run(query_wiki(question))
            bundle["answer"] = ans
            bundle["sources"] = sources
            bundle["confidence"] = _confidence_for(sources, market="us")
        except Exception as exc:
            bundle["answer"] = f"The global advisor failed: {exc}."
            bundle["confidence"] = 0.0

    return bundle


def _render_assistant_message(bundle: dict[str, Any]) -> None:
    badge = _confidence_badge_html(bundle["confidence"])
    fast_path_badge = ""
    if bundle.get("fast_path") == "faq":
        fast_path_badge = (
            '<span class="pp-badge pp-badge-blue" '
            'title="Pre-computed answer, no LLM call">Instant</span>'
        )
    st.markdown(badge + fast_path_badge, unsafe_allow_html=True)
    if bundle.get("calc_html"):
        st.markdown(bundle["calc_html"], unsafe_allow_html=True)
    if bundle["answer"]:
        st.markdown(bundle["answer"])
    if bundle["sources"]:
        with st.expander(f"Sources ({len(bundle['sources'])})"):
            for s in bundle["sources"]:
                st.markdown(f"- `{s}`")


def _render_chat_history(messages: list[dict]) -> None:
    for m in messages:
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                _render_assistant_message(m)


# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Finsight")
    st.markdown("#### Settings")

    hindi_mode = st.toggle(
        "Reply in Hindi",
        value=False,
        help="When enabled, India advisor answers are produced in Hindi.",
    )

    st.divider()
    st.markdown("#### About")
    st.caption(
        "AI-powered investment intelligence platform. Grounded in SEBI, AMFI, RBI public "
        "data. Educational use only, not advisory."
    )
    if _load_profile() is not None:
        st.divider()
        if st.button("Reset profile and onboard again"):
            _delete_profile()
            for k in list(st.session_state.keys()):
                key_str = str(k)
                if key_str.startswith("ob_") or key_str.endswith("_messages"):
                    del st.session_state[k]
            st.rerun()


# ── Main flow: gate on onboarding ───────────────────────────────────────────

profile_row = _load_profile()

if profile_row is None:
    _render_onboarding()
    st.stop()

profile_dict = _profile_to_dict(profile_row)

# ── Tabs ───────────────────────────────────────────────────────────────────

india_tab, global_tab, sources_tab, health_tab = st.tabs(
    [
        "India Advisor",
        "Global Markets",
        "Sources & History",
        "System Health",
    ]
)


# ── India tab ───────────────────────────────────────────────────────────────

with india_tab:
    # Profile pill
    dna = _classify_dna(profile_dict)
    st.markdown(
        f'<span class="fs-badge fs-badge-blue">{profile_row.name} · {dna}</span> '
        f'<span class="fs-badge fs-badge-green">Goal: {profile_row.primary_goal}</span> '
        f'<span class="fs-badge fs-badge-purple">SIP: {profile_row.monthly_sip_budget}</span>',
        unsafe_allow_html=True,
    )

    st.subheader("Indian market overview")

    # Market summary
    try:
        india_prices = _load_india_prices()
        if india_prices:
            usable_pcts = [
                r["change_pct"]
                for r in india_prices
                if r.get("change_pct") is not None
            ]
            any_live = any(r.get("data_label") == "Live" for r in india_prices)
            if usable_pcts:
                avg_pct = sum(usable_pcts) / len(usable_pcts)
                st.session_state["nifty_change_pct"] = avg_pct
                if not any_live:
                    st.info("Markets are closed. Showing last available prices.")
                elif avg_pct > 0.25:
                    st.success(f"Markets are up today. Average {avg_pct:+.2f}% across tracked NSE stocks.")
                elif avg_pct < -0.25:
                    st.warning(f"Markets are down today. Average {avg_pct:+.2f}% across tracked NSE stocks.")
                else:
                    st.info(f"Markets are flat today. Average {avg_pct:+.2f}%.")
            else:
                st.info("Market closed. Showing last cached prices.")

            def _format_price(price: float | None) -> str:
                if price is None:
                    return "N/A"
                if price >= 10000:
                    return f"{price/1000:.1f}K"
                elif price >= 1000:
                    return f"{price:,.0f}"
                else:
                    return f"{price:,.2f}"

            cols_per_row = 5
            rows = [india_prices[i : i + cols_per_row] for i in range(0, len(india_prices), cols_per_row)]
            for row in rows:
                cols = st.columns(len(row))
                for col, r in zip(cols, row, strict=False):
                    symbol = r["symbol"].replace(".NS", "")
                    price = r.get("price_inr")
                    pct = r.get("change_pct")
                    label = r.get("data_label", "")
                    price_str = f"INR {_format_price(price)}"
                    delta_str = f"{pct:+.2f}%" if pct is not None else None
                    with col:
                        st.metric(
                            label=symbol,
                            value=price_str,
                            delta=delta_str,
                            help=f"Full price: INR {price:,.2f} | {label} | {r.get('fetched_at','')[:16].replace('T',' ')} UTC" if price else "No data",
                        )
        else:
            st.info("No live NSE data yet. Run main.py to start the ingest agent.")
    except Exception as exc:
        st.warning(f"Live India data unavailable: {type(exc).__name__}")


    st.divider()

    # ── Chat surface ────────────────────────────────────────────────────────
    st.subheader("Ask the India advisor")

    if "india_messages" not in st.session_state:
        st.session_state.india_messages = []

    # Nudges based on recent questions
    history = [m["content"] for m in st.session_state.india_messages if m["role"] == "user"]
    _render_nudges(profile_dict, history)

    # Cold-start suggestion chips
    if not st.session_state.india_messages:
        st.markdown('<p class="pp-caption">Try one of these to start.</p>', unsafe_allow_html=True)
        chip_cols = st.columns(2)
        chips = [
            "I earn INR 40k a month, where should I start investing?",
            "ELSS vs PPF, which one for me?",
            "Mujhe 5 saal mein ghar ke liye paise jodne hain",
            "Market gir gaya, SIP band karu?",
        ]
        chip_clicked: str | None = None
        for i, chip in enumerate(chips):
            if chip_cols[i % 2].button(chip, key=f"chip_{i}", use_container_width=True):
                chip_clicked = chip
        if chip_clicked:
            st.session_state.pending_india_question = chip_clicked
            st.rerun()

    _render_chat_history(st.session_state.india_messages)

    # Determine the new question (chip click or fresh chat input)
    pending = st.session_state.pop("pending_india_question", None)
    user_q = pending or st.chat_input(
        "Ask anything about Indian markets, SIP, ELSS, NPS, PPF, taxes."
    )

    if user_q:
        st.session_state.india_messages.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)
        with st.chat_message("assistant"):
            with st.spinner("Reading the wiki and grounding the answer..."):
                bundle = _produce_answer(user_q, profile_dict, hindi_mode, market="india")
            _render_assistant_message(bundle)
        st.session_state.india_messages.append({"role": "assistant", **bundle})

    with st.expander("Quick tools (deterministic, no LLM)"):
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            st.markdown("**SIP future value**")
            sip_amt = st.number_input("Monthly SIP (INR)", min_value=500, value=5000, step=500)
            sip_yrs = st.slider("Years", 1, 30, 10)
            sip_ret = st.slider("Expected annual return (%)", 4.0, 18.0, 12.0, 0.5)
            sip_res = sip_future_value(float(sip_amt), float(sip_ret), int(sip_yrs))
            st.metric("Future value", _format_inr(sip_res["future_value"]))
            st.caption(
                f"Total invested {_format_inr(sip_res['total_invested'])}, "
                f"estimated returns {_format_inr(sip_res['estimated_returns'])}."
            )
        with tcol2:
            st.markdown("**ELSS tax savings (old regime)**")
            elss_amt = st.number_input("Annual ELSS investment (INR)", min_value=0, max_value=300000, value=150000, step=10000)
            elss_bracket = st.select_slider("Tax bracket (%)", options=[0, 5, 10, 15, 20, 25, 30], value=int(profile_dict.get("tax_bracket_pct") or 30))
            elss_res = elss_tax_savings(float(elss_amt), float(elss_bracket))  # type: ignore[arg-type]
            st.metric("Tax saved", _format_inr(elss_res["tax_saved"]))
            st.caption(
                f"Eligible deduction {_format_inr(elss_res['deduction'])}. "
                f"Effective cost {_format_inr(elss_res['effective_cost'])}."
            )


# ── Global tab ──────────────────────────────────────────────────────────────

with global_tab:
    st.subheader("Global markets")
    st.caption(
        "Same engine, US tickers. Architecture is market-agnostic. India is the "
        "primary surface; this tab proves portability."
    )

    prices = get_latest_prices()
    if prices:
        cols_per_row = 5
        rows = [prices[i : i + cols_per_row] for i in range(0, len(prices), cols_per_row)]
        for row in rows:
            cols = st.columns(len(row))
            for col, p in zip(cols, row, strict=False):
                price_str = f"${p['price']:,.2f}"
                pct = p.get("change_pct")
                delta_str = f"{pct:+.2f}%" if pct is not None else None
                with col:
                    st.metric(p["symbol"], price_str, delta_str, help=p.get("data_label", ""))
    else:
        st.info("Waiting for the first US data fetch.")

    st.divider()
    st.subheader("Recent news headlines")
    headlines = get_recent_headlines(limit=10)
    if headlines:
        for h in headlines:
            url = h.get("url", "")
            text = h["headline"]
            if url:
                st.markdown(f"- [{text[:120]}]({url}) ({h['source']})")
            else:
                st.markdown(f"- {text[:120]} ({h['source']})")
    else:
        st.info("No headlines ingested yet.")

    st.divider()
    st.subheader("Ask the global advisor")

    if "global_messages" not in st.session_state:
        st.session_state.global_messages = []
    _render_chat_history(st.session_state.global_messages)
    user_g = st.chat_input("Ask about US stocks, ETFs, 401k, IRA, taxes.", key="global_input")
    if user_g:
        st.session_state.global_messages.append({"role": "user", "content": user_g})
        with st.chat_message("user"):
            st.markdown(user_g)
        with st.chat_message("assistant"):
            with st.spinner("Consulting the global wiki..."):
                bundle = _produce_answer(user_g, profile_dict, hindi_mode=False, market="us")
            _render_assistant_message(bundle)
        st.session_state.global_messages.append({"role": "assistant", **bundle})

    st.divider()
    st.subheader("AI-generated insights")
    insights = get_recent_insights(limit=5)
    if insights:
        for insight in insights:
            with st.expander(
                f"{insight['generated_at'][:16]} · {insight['sentiment_summary']}",
                expanded=(insight == insights[0]),
            ):
                st.write(insight["insight_text"])
                if insight.get("sources"):
                    valid = [s for s in insight["sources"] if s]
                    if valid:
                        st.caption("Sources: " + " · ".join(valid[:3]))
                st.caption(f"Model: {insight.get('model_used', 'unknown')}")
    else:
        st.info("No insights yet. The analysis agent runs on a cadence.")


# ── Sources & History tab ──────────────────────────────────────────────────

with sources_tab:
    st.subheader("Source registry")

    @st.cache_data(ttl=60)
    def _load_sources_cached() -> list[dict[str, Any]]:
        return get_all_sources(_engine)

    source_rows = _load_sources_cached()
    if source_rows:
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "URL": s["url"],
                    "Name": s["source_name"],
                    "Type": s["source_type"],
                    "Domain": s["domain"],
                    "Trusted": "Yes" if s["is_trusted"] else "No",
                    "Reachable": "Yes" if s["is_reachable"] else "No",
                    "HTTP": s["http_status"],
                    "Fetches": s["fetch_count"],
                    "Last fetched": s["last_fetched_at"],
                }
                for s in source_rows
            ]
        )
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No sources registered yet. Run the ingest agent.")

    st.subheader("Wiki version history")
    wiki_page = st.text_input(
        "Page name (e.g. india/concepts/sip.md or stocks/AAPL.md)",
        placeholder="india/concepts/sip.md",
        key="wiki_page_input",
    )
    if wiki_page.strip():
        history = get_page_version_history(_engine, wiki_page.strip())
        if history:
            import pandas as pd

            hist_df = pd.DataFrame(
                [
                    {
                        "Version": h["version"],
                        "Changed at": h["changed_at"],
                        "Summary": h["change_summary"],
                        "Triggered by": h["triggered_by"],
                        "Words before": h["word_count_before"],
                        "Words after": h["word_count_after"],
                    }
                    for h in history
                ]
            )
            st.dataframe(hist_df, use_container_width=True)
        else:
            st.info(f"No version history for page '{wiki_page.strip()}'.")


# ── System Health tab ──────────────────────────────────────────────────────

with health_tab:
    st.subheader("System health")
    st.caption(
        "Read-only view of the wiki freshness and raw-data ingest. Wiki and raw "
        "freshness are computed locally on every render. The full lint audit runs "
        "on the analysis agent's cadence."
    )

    snapshot = wiki_health_snapshot()
    raw_snap = raw_data_snapshot()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Wiki pages", snapshot["total_pages"])
    c2.metric("Fresh", len(snapshot["fresh"]))
    c3.metric("Stale", len(snapshot["stale"]))
    c4.metric("Missing frontmatter", len(snapshot["missing_frontmatter"]))

    if snapshot["by_type"]:
        st.caption(
            "By page type: "
            + " · ".join(f"{k}={v}" for k, v in sorted(snapshot["by_type"].items()))
        )

    latest = snapshot.get("latest_lint_report")
    if latest:
        st.info(
            f"Last lint audit: `{latest['path']}` "
            f"({latest['generated_at_iso'][:16]} UTC). "
            f"{latest['stale_count']} stale. {latest['contradiction_count']} contradictions."
        )
    else:
        st.info(
            "No lint report yet. The analysis agent runs lint_wiki() periodically."
        )

    if snapshot["stale"]:
        with st.expander(f"Stale pages ({len(snapshot['stale'])})", expanded=False):
            stale_rows = [
                {
                    "path": e["path"],
                    "page_type": e["page_type"],
                    "age (h)": e["age_hours"],
                    "ttl (h)": e["ttl_hours"],
                    "overdue (h)": e["overdue_hours"],
                    "symbol": e.get("symbol") or "",
                }
                for e in sorted(
                    snapshot["stale"],
                    key=lambda x: x["overdue_hours"],
                    reverse=True,
                )
            ]
            st.dataframe(stale_rows, use_container_width=True, hide_index=True)
    else:
        st.success("All pages within their TTL.")

    if snapshot["fresh"]:
        with st.expander(f"Fresh pages ({len(snapshot['fresh'])})", expanded=False):
            fresh_rows = [
                {
                    "path": e["path"],
                    "page_type": e["page_type"],
                    "age (h)": e["age_hours"],
                    "ttl (h)": e["ttl_hours"],
                    "symbol": e.get("symbol") or "",
                }
                for e in sorted(snapshot["fresh"], key=lambda x: x["age_hours"])
            ]
            st.dataframe(fresh_rows, use_container_width=True, hide_index=True)

    st.subheader("Raw data freshness")
    src_rows = [
        {
            "source": name,
            "files": s["file_count"],
            "total MB": s["total_mb"],
            "latest fetch": (s["latest_iso"][:16] if s["latest_iso"] else ""),
        }
        for name, s in raw_snap["sources"].items()
    ]
    if src_rows:
        st.dataframe(src_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No raw data files ingested yet.")

    st.divider()
    if st.button("Run lint_wiki now (uses Gemini)", key="run_lint"):
        with st.spinner("Walking the wiki and consulting Gemini..."):
            try:
                result = asyncio.run(lint_wiki())
                st.success(
                    f"Lint complete. {len(result['stale_pages'])} stale, "
                    f"{len(result['contradictions'])} contradictions, "
                    f"{len(result['needs_refresh'])} need refresh."
                )
                if result["contradictions"]:
                    with st.expander("Contradictions found", expanded=True):
                        for c in result["contradictions"]:
                            st.markdown(c)
            except Exception as exc:
                st.error(f"lint_wiki failed: {exc}")


# ── Footer ─────────────────────────────────────────────────────────────────

st.markdown(
    f'<p class="fs-caption" style="text-align:center;margin-top:2rem;">'
    f"Finsight is for educational use only. Not financial advice. Verify with a SEBI-registered "
    f"investment adviser. Last render {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}."
    f"</p>",
    unsafe_allow_html=True,
)
