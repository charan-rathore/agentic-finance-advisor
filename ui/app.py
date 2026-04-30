"""
ui/app.py

Streamlit dashboard for the Multi-Agent Finance Advisor.

Data source: imports query functions from agents/storage_agent.py directly.
No HTTP API needed — Streamlit runs in the same codebase.

To run locally:  streamlit run ui/app.py
In Docker:       separate service in docker-compose.yml (port 8501)
"""

import asyncio
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import sessionmaker

from agents.storage_agent import (
    get_latest_prices,
    get_recent_headlines,
    get_recent_insights,
)
from core.fetchers_india import fetch_amfi_nav, fetch_india_prices, fetch_rbi_rates
from core.models import UserProfile, init_db
from core.settings import settings
from core.trust import get_all_sources, get_page_version_history
from core.wiki import (
    beginner_answer,
    detect_beginner_intent,
    lint_wiki,
    query_wiki,
    raw_data_snapshot,
    wiki_health_snapshot,
)
from core.wiki_india import (
    beginner_answer_india,
    detect_beginner_intent_india,
    query_india,
)

st.set_page_config(
    page_title="AI Finance Advisor",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Multi-Agent AI Finance Advisor")
st.caption(
    "Google Gemini · yfinance · Alpha Vantage · Finnhub · SEC EDGAR · FRED · "
    "LLM Wiki (Karpathy) · All free-tier"
)

# ── DB session (shared for this run) ─────────────────────────────────────────

_engine = init_db(settings.DATABASE_URL)
_Session = sessionmaker(bind=_engine)


def _load_profile() -> UserProfile | None:
    """Return the first UserProfile row, or None if the table is empty."""
    with _Session() as s:
        return s.query(UserProfile).order_by(UserProfile.id.asc()).first()


def _save_profile(data: dict) -> None:
    """Insert a new profile row (single-user: one row is enough)."""
    with _Session() as s:
        s.add(UserProfile(**data))
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


# ── India dashboard cached loaders ───────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_india_prices() -> list[dict]:
    return asyncio.run(fetch_india_prices())


@st.cache_data(ttl=3600)
def _load_amfi_nav() -> list[dict]:
    return asyncio.run(fetch_amfi_nav())


@st.cache_data(ttl=3600)
def _load_rbi_rates() -> dict:
    return asyncio.run(fetch_rbi_rates())


# ── Sidebar: global ask-anything (US wiki) ───────────────────────────────────

with st.sidebar:
    st.header("Ask the advisor")
    experience = st.radio(
        "Your experience level",
        options=["Auto-detect from question", "I'm new to investing", "I'm experienced"],
        index=0,
        help=(
            "Beginner mode teaches the concepts first, then gives advice. "
            "Experienced mode skips the primer and answers directly from the "
            "live LLM wiki."
        ),
    )
    question = st.text_area(
        "Your question",
        placeholder="e.g. How do I get started and where should I invest?",
        height=120,
    )
    ask = st.button("Ask", type="primary", use_container_width=True)
    st.caption(
        "The advisor reads the wiki under `data/wiki/` and grounds every answer "
        "in the latest ingested prices, news, and SEC filings."
    )

    st.divider()
    hindi_mode = st.checkbox(
        "हिंदी में जवाब दें (Answer in Hindi)",
        value=False,
        help="India Advisor answers will be in Hindi (Devanagari script).",
    )


# ── Main area: answer ───────────────────────────────────────────────────────

if ask and question.strip():
    # Pick the flow up front so the UI copy matches what the model was told.
    force_beginner = experience == "I'm new to investing"
    force_expert = experience == "I'm experienced"
    use_beginner = force_beginner or (not force_expert and detect_beginner_intent(question))

    badge = "🧑‍🏫 Beginner mode" if use_beginner else "📊 Advisor mode"
    st.header(f"{badge}: {question.strip()[:80]}")

    with st.spinner("Reading the wiki and consulting Gemini..."):
        try:
            if use_beginner:
                answer, consulted = asyncio.run(beginner_answer(question.strip()))
            else:
                answer, consulted = asyncio.run(query_wiki(question.strip()))
        except Exception as e:
            st.error(f"Advisor call failed: {e}")
            answer, consulted = "", []

    if answer:
        st.markdown(answer)
        if consulted:
            with st.expander("Sources consulted"):
                for path in consulted:
                    st.markdown(f"- `{path}`")

    st.divider()


# ── Dashboard panels ────────────────────────────────────────────────────────

dashboard_tab, india_tab, sources_tab, health_tab = st.tabs(
    ["Dashboard", "🇮🇳 India Advisor", "🔍 Sources & History", "System Health"]
)


# ── India Advisor tab ────────────────────────────────────────────────────────

with india_tab:
    st.subheader("🇮🇳 Indian Market Overview")

    # ── Row 1: NSE stock prices ───────────────────────────────────────────────
    try:
        india_prices = _load_india_prices()
        if india_prices:
            def _fmt_change(r: dict) -> str:
                pct = r.get("change_pct")
                if pct is None:
                    return "N/A"
                arrow = "▲" if pct >= 0 else "▼"
                return f"{arrow} {pct:+.2f}%"

            price_rows = [
                {
                    "Symbol": r["symbol"],
                    "Price (₹)": f"₹{r['price_inr']:,.2f}",
                    "Prev Close (₹)": f"₹{r['prev_close_inr']:,.2f}"
                    if r.get("prev_close_inr") is not None
                    else "N/A",
                    "Change (₹)": f"{r['change_abs']:+.2f}"
                    if r.get("change_abs") is not None
                    else "N/A",
                    "Change%": _fmt_change(r),
                    "Status": r.get("data_label", ""),
                    "Last Updated": r.get("fetched_at", "")[:16].replace("T", " ") + " UTC"
                    if r.get("fetched_at")
                    else "N/A",
                    "Source": r.get("source", "yfinance_nse"),
                }
                for r in india_prices
            ]
            st.dataframe(price_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No NSE price data available yet.")
    except Exception:
        st.warning("Live data unavailable — using cached wiki data")

    # ── Row 2: Mutual fund NAVs ───────────────────────────────────────────────
    try:
        amfi_navs = _load_amfi_nav()
        if amfi_navs:
            nav_rows = [
                {
                    "Scheme": r.get("scheme_name") or r.get("friendly_name", ""),
                    "NAV (₹)": r["nav"],
                    "Date": r["nav_date"],
                }
                for r in amfi_navs
            ]
            st.dataframe(nav_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No mutual fund NAV data available yet.")
    except Exception:
        st.warning("Live data unavailable — using cached wiki data")

    # ── Row 3: RBI macro ─────────────────────────────────────────────────────
    try:
        rbi = _load_rbi_rates()
        rbi_col1, rbi_col2, rbi_col3 = st.columns(3)
        rbi_col1.metric(
            "Repo Rate",
            f"{rbi.get('repo_rate_pct', 'N/A')}%",
        )
        rbi_col2.metric(
            "CPI India",
            str(rbi.get("cpi_pct", "N/A")),
        )
        rbi_col3.metric(
            "INR/USD",
            str(rbi.get("inr_usd", "N/A")),
        )
    except Exception:
        st.warning("Live data unavailable — using cached wiki data")

    st.divider()

    profile_row = _load_profile()

    # ── Onboarding form (shown when no profile exists) ────────────────────
    if profile_row is None:
        st.header("👋 Welcome! Let's set up your investor profile")
        st.caption(
            "Answer 5 quick questions so the advisor can personalise its recommendations. "
            "Your answers are stored locally only."
        )

        with st.form("onboarding_form"):
            col_a, col_b = st.columns(2)

            with col_a:
                name = st.text_input("Your name (optional)", value="Investor")

                monthly_income = st.selectbox(
                    "Monthly income range",
                    options=[
                        "Below ₹25k",
                        "₹25k–₹50k",
                        "₹50k–₹1L",
                        "₹1L–₹2L",
                        "Above ₹2L",
                    ],
                    help="Approximate gross monthly income",
                )

                monthly_sip_budget = st.selectbox(
                    "How much can you invest each month?",
                    options=[
                        "Below ₹1k",
                        "₹1k–₹2k",
                        "₹2k–₹5k",
                        "₹5k–₹10k",
                        "₹10k–₹25k",
                        "Above ₹25k",
                    ],
                )

            with col_b:
                risk_tolerance = st.selectbox(
                    "Risk appetite",
                    options=["low", "medium", "high"],
                    format_func=lambda x: {
                        "low": "🟢 Low — I prefer safety over returns",
                        "medium": "🟡 Medium — balanced approach",
                        "high": "🔴 High — I can handle volatility",
                    }[x],
                )

                primary_goal = st.selectbox(
                    "Primary financial goal",
                    options=[
                        "Build emergency fund",
                        "Save tax (80C)",
                        "Grow wealth (SIP)",
                        "Retirement / NPS",
                        "Child education",
                        "Buy a house",
                        "Other",
                    ],
                )

                horizon_pref = st.selectbox(
                    "Investment time horizon",
                    options=["short", "intermediate", "long"],
                    format_func=lambda x: {
                        "short": "Short (≤ 1 year)",
                        "intermediate": "Medium (2–5 years)",
                        "long": "Long (5+ years)",
                    }[x],
                )

                tax_bracket_pct = st.selectbox(
                    "Income tax slab",
                    options=[0.0, 5.0, 20.0, 30.0],
                    format_func=lambda x: f"{int(x)}%",
                    help="Your marginal income tax rate — used to personalise ELSS / NPS suggestions",
                )

            submitted = st.form_submit_button("Save profile & continue", type="primary")

        if submitted:
            _save_profile(
                {
                    "name": name.strip() or "Investor",
                    "monthly_income": monthly_income,
                    "monthly_sip_budget": monthly_sip_budget,
                    "risk_tolerance": risk_tolerance,
                    "tax_bracket_pct": float(tax_bracket_pct),
                    "primary_goal": primary_goal,
                    "horizon_pref": horizon_pref,
                }
            )
            st.success("✅ Profile saved! Refreshing…")
            st.rerun()

    else:
        # ── Profile exists — show advisor UI ─────────────────────────────
        profile_dict = _profile_to_dict(profile_row)

        with st.expander(
            f"👤 {profile_row.name}'s profile  "
            f"({profile_row.horizon_pref} horizon · {profile_row.risk_tolerance} risk · "
            f"{profile_row.primary_goal})",
            expanded=False,
        ):
            cols = st.columns(3)
            cols[0].metric("Monthly income", profile_row.monthly_income)
            cols[1].metric("SIP budget", profile_row.monthly_sip_budget)
            cols[2].metric("Tax bracket", f"{int(profile_row.tax_bracket_pct)}%")
            if st.button("Reset profile", key="reset_profile"):
                with _Session() as s:
                    s.query(UserProfile).delete()
                    s.commit()
                st.rerun()

        st.header("🇮🇳 Ask the India Advisor")
        india_q = st.text_area(
            "Your question (Indian markets, SIP, ELSS, NPS, PPF…)",
            placeholder="e.g. Which index fund should I start with given my risk tolerance?",
            height=110,
            key="india_question",
        )
        india_ask = st.button("Ask India Advisor", type="primary", key="india_ask")

        if india_ask and india_q.strip():
            is_beginner = detect_beginner_intent_india(india_q)
            badge = "🧑‍🏫 Beginner" if is_beginner else "📊 Advisor"
            st.subheader(f"{badge}: {india_q.strip()[:80]}")

            with st.spinner("Consulting the India wiki…"):
                try:
                    if is_beginner:
                        ans, sources = asyncio.run(
                            beginner_answer_india(
                                india_q.strip(),
                                profile=profile_dict,
                                hindi=hindi_mode,
                            )
                        )
                    else:
                        ans, sources = asyncio.run(
                            query_india(
                                india_q.strip(),
                                profile=profile_dict,
                                hindi=hindi_mode,
                            )
                        )
                except Exception as e:
                    st.error(f"India advisor failed: {e}")
                    ans, sources = "", []

            if ans:
                st.markdown(ans)
                if sources:
                    with st.expander("Sources consulted"):
                        for p in sources:
                            st.markdown(f"- `{p}`")

with sources_tab:
    st.subheader("Source Registry")

    @st.cache_data(ttl=60)
    def _load_sources() -> list[dict[str, object]]:
        return get_all_sources(_engine)

    source_rows = _load_sources()
    if source_rows:
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "URL": s["url"],
                    "Name": s["source_name"],
                    "Type": s["source_type"],
                    "Domain": s["domain"],
                    "Trusted": "✅" if s["is_trusted"] else "⚠️",
                    "Reachable": "✅" if s["is_reachable"] else "❌",
                    "HTTP": s["http_status"],
                    "Fetches": s["fetch_count"],
                    "Last fetched": s["last_fetched_at"],
                }
                for s in source_rows
            ]
        )
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No sources registered yet. Run the ingest agent first.")

    st.subheader("Wiki Version History")
    wiki_page = st.text_input(
        "Page name (e.g. stocks/RELIANCE)",
        placeholder="stocks/RELIANCE",
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
            st.info(f"No version history found for page '{wiki_page.strip()}'.")


with dashboard_tab:
    st.header("Current Market Prices")
    prices = get_latest_prices()

    if prices:
        price_table = [
            {
                "Symbol": p["symbol"],
                "Price (USD)": f"${p['price']:,.2f}",
                "Prev Close": f"${p['prev_close']:,.2f}" if p.get("prev_close") else "N/A",
                "Change (USD)": f"{p['change_abs']:+.2f}" if p.get("change_abs") is not None else "N/A",
                "Change%": f"{p['change_pct']:+.2f}%" if p.get("change_pct") is not None else "N/A",
                "Status": p.get("data_label", ""),
                "Last Updated": p["captured_at"][:16].replace("T", " ") + " UTC",
                "Source": p.get("source", "yfinance"),
            }
            for p in prices
        ]
        st.dataframe(price_table, use_container_width=True, hide_index=True)
        st.caption(f"Last updated: {prices[0]['captured_at'][:16]} UTC · {prices[0].get('data_label', '')}")
    else:
        st.info("⏳ Waiting for first data fetch (up to 5 minutes)...")

    st.header("Recent News Headlines")
    headlines = get_recent_headlines(limit=10)

    if headlines:
        for h in headlines:
            url = h.get("url", "")
            headline_text = h["headline"]
            if url:
                st.markdown(f"- [{headline_text[:120]}]({url}) — *{h['source']}*")
            else:
                st.markdown(f"- {headline_text[:120]} — *{h['source']}*")
    else:
        st.info("⏳ No headlines yet...")

    st.header("AI-Generated Insights")
    st.caption("Generated by Gemini · Refreshes every 10 minutes")

    insights = get_recent_insights(limit=5)

    if insights:
        for insight in insights:
            with st.expander(
                f"🤖 {insight['generated_at'][:16]}  —  {insight['sentiment_summary']}",
                expanded=(insight == insights[0]),
            ):
                st.write(insight["insight_text"])

                if insight["sources"]:
                    valid_sources = [s for s in insight["sources"] if s]
                    if valid_sources:
                        st.caption("Sources: " + " · ".join(valid_sources[:3]))

                st.caption(f"Model: {insight['model_used']}")
    else:
        st.info(
            "⏳ No insights yet. The analysis agent runs every 10 minutes. "
            "Check back shortly or reduce ANALYSIS_INTERVAL_SECONDS in .env for faster testing."
        )

    st.divider()
    col1, col2 = st.columns([3, 1])
    col1.caption("This is a personal project for educational purposes. Not financial advice.")
    if col2.button("🔄 Refresh", key="dashboard_refresh"):
        st.rerun()


# ── System Health tab ───────────────────────────────────────────────────────

with health_tab:
    st.header("🩺 System Health")
    st.caption(
        "Read-only view of the knowledge base. "
        "`Wiki freshness` and `Raw data freshness` are computed locally on every "
        "render (no Gemini calls). The last Gemini-based audit from `lint_wiki()` "
        "is surfaced below when it exists."
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
            f"Last full `lint_wiki()` audit: `{latest['path']}` "
            f"({latest['generated_at_iso'][:16]} UTC) — "
            f"{latest['stale_count']} stale · {latest['contradiction_count']} contradictions"
        )
    else:
        st.info(
            "No full lint report on disk yet. The analysis agent runs `lint_wiki()` "
            "every `WIKI_LINT_INTERVAL_HOURS` hours, or trigger it on demand below."
        )

    st.subheader("Wiki freshness")
    if snapshot["stale"]:
        with st.expander(f"⚠️ Stale pages ({len(snapshot['stale'])})", expanded=True):
            rows = [
                {
                    "path": e["path"],
                    "page_type": e["page_type"],
                    "age (h)": e["age_hours"],
                    "ttl (h)": e["ttl_hours"],
                    "overdue (h)": e["overdue_hours"],
                    "symbol": e.get("symbol") or "",
                }
                for e in sorted(snapshot["stale"], key=lambda x: x["overdue_hours"], reverse=True)
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.success("All pages are within their TTL.")

    if snapshot["missing_frontmatter"]:
        with st.expander(
            f"Pages without frontmatter ({len(snapshot['missing_frontmatter'])})",
            expanded=False,
        ):
            for p in snapshot["missing_frontmatter"]:
                st.markdown(f"- `{p}`")

    if snapshot["fresh"]:
        with st.expander(f"Fresh pages ({len(snapshot['fresh'])})", expanded=False):
            rows = [
                {
                    "path": e["path"],
                    "page_type": e["page_type"],
                    "age (h)": e["age_hours"],
                    "ttl (h)": e["ttl_hours"],
                    "symbol": e.get("symbol") or "",
                }
                for e in sorted(snapshot["fresh"], key=lambda x: x["age_hours"])
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)

    st.subheader("Raw data freshness")
    src_rows = [
        {
            "source": name,
            "files": s["file_count"],
            "total MB": s["total_mb"],
            "latest fetch": (s["latest_iso"][:16] if s["latest_iso"] else "—"),
        }
        for name, s in raw_snap["sources"].items()
    ]
    st.dataframe(src_rows, use_container_width=True, hide_index=True)

    st.subheader("Run full audit now")
    st.caption(
        "Calls `lint_wiki()` — walks every page, stamps stale banners into the "
        "ones past TTL, and asks Gemini to look for contradictions across the "
        "top 20 pages. Costs tokens; prefer letting the analysis agent run it on "
        "its regular cadence."
    )
    if st.button("Run lint_wiki now (uses Gemini)", key="run_lint"):
        with st.spinner("Walking the wiki and consulting Gemini..."):
            try:
                result = asyncio.run(lint_wiki())
                st.success(
                    f"Lint complete: {len(result['stale_pages'])} stale, "
                    f"{len(result['contradictions'])} contradictions, "
                    f"{len(result['needs_refresh'])} pages need refresh."
                )
                if result["contradictions"]:
                    with st.expander("Contradictions found", expanded=True):
                        for c in result["contradictions"]:
                            st.markdown(c)
                st.rerun()
            except Exception as e:
                st.error(f"lint_wiki failed: {e}")
