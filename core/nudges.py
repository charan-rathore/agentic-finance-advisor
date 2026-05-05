"""
core/nudges.py

Deterministic behavioural-finance nudge engine. Pure Python, no LLM calls.

A nudge is a short, contextual prompt rendered above the chat to encourage the
user to take a specific positive action (or avoid a specific negative one).
The rules in this module are intentionally simple and explainable, so the
behaviour is auditable and the user can trust the reasoning.

Public API:
    generate_nudges(profile, recent_questions, market) -> list[Nudge]

A ``Nudge`` is a dict with these keys:
    - ``icon``: short label (we keep this restrained, no emoji storms)
    - ``title``: 4-7 word title
    - ``body``: 1-3 sentence explanation
    - ``priority``: integer; higher means render first
    - ``rule``: identifier of the rule that fired (for telemetry)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict


class Nudge(TypedDict):
    icon: str
    title: str
    body: str
    priority: int
    rule: str


# ── Trigger word lists (kept module-level for testability) ───────────────────

_PANIC_TRIGGERS: tuple[str, ...] = (
    "stop sip",
    "stop my sip",
    "pause sip",
    "pause my sip",
    "band karu",
    "rok du",
    "should i sell",
    "exit my sip",
    "market crashed",
    "market gir gaya",
    "gir gaya",
)

_TAX_TRIGGERS: tuple[str, ...] = (
    "tax saving",
    "save tax",
    "80c",
    "elss",
    "ppf",
    "tax bachana",
    "tax kaise bachaye",
)

# 7-day rotation of educational tips for new users.
_DAILY_TIPS: tuple[tuple[str, str], ...] = (
    (
        "Start small, stay consistent",
        "An INR 2,000 monthly SIP for 20 years at 12 percent grows to about "
        "INR 19.9 lakh. The number you can sustain is more important than the "
        "number you start with.",
    ),
    (
        "Index funds win over the long run",
        "About 70 to 80 percent of active large-cap funds in India trail the "
        "Nifty 100 over rolling 10-year windows. A low-cost index fund is a "
        "defensible default for the core of your portfolio.",
    ),
    (
        "Build an emergency fund first",
        "Three to six months of essential expenses parked in a liquid fund or "
        "savings account should come before any equity SIP. It prevents you "
        "from selling equity at exactly the wrong moment.",
    ),
    (
        "Get term life insurance, not investment-cum-insurance",
        "ULIPs and traditional endowment plans bundle insurance with poor "
        "investment outcomes. A pure term plan plus a separate SIP is almost "
        "always cheaper and clearer.",
    ),
    (
        "Avoid concentration in single stocks",
        "First-time investors who put more than 20 percent in a single stock "
        "typically underperform a plain index fund. Mutual funds and index "
        "funds give you diversification at a low cost.",
    ),
    (
        "Compounding rewards patience",
        "Money doubles every six years at a 12 percent return (rule of 72). "
        "Stopping a SIP for 12 months mid-cycle costs more than most "
        "investors imagine, because that is when units are cheapest.",
    ),
    (
        "Be skeptical of finfluencer tips",
        "SEBI's 2024 framework restricts unregistered advice. Cross-check any "
        "WhatsApp or YouTube tip against AMFI fund factsheets and the SEBI "
        "investor portal before acting.",
    ),
)


def _has_trigger(text: str, triggers: tuple[str, ...]) -> bool:
    norm = text.lower()
    return any(t in norm for t in triggers)


def _format_inr(amount: float) -> str:
    if amount >= 100000:
        return f"INR {amount/100000:.1f} lakh"
    return f"INR {int(amount):,}"


def generate_nudges(
    profile: dict | None = None,
    recent_questions: list[str] | None = None,
    market: dict | None = None,
    now: datetime | None = None,
) -> list[Nudge]:
    """
    Return up to 3 contextual nudges, sorted by descending priority.

    Args:
        profile: optional user profile dict with optional keys
            ``primary_goal``, ``tax_bracket_pct``, ``monthly_sip_budget``,
            ``risk_tolerance``, ``created_at``.
        recent_questions: list of recent user questions (most recent last).
        market: optional dict with ``nifty_change_pct`` (today's percent move).
        now: optional injected ``datetime`` for deterministic testing.

    The function is pure: same inputs always yield the same outputs.
    """
    now = now or datetime.now(UTC)
    profile = profile or {}
    recent_questions = recent_questions or []
    market = market or {}

    nudges: list[Nudge] = []

    # ── Rule 1: stop-SIP / panic regret guard ────────────────────────────────
    panic_hit = any(_has_trigger(q, _PANIC_TRIGGERS) for q in recent_questions)
    if panic_hit:
        nudges.append(
            Nudge(
                icon="warn",
                title="Pause before pausing your SIP",
                body=(
                    "INR 5,000 per month at 12 percent compounds to about INR 11.6 "
                    "lakh over 10 years. Pausing for 12 months mid-cycle typically "
                    "costs INR 1 to 2 lakh of long-run growth. Drawdowns are when "
                    "SIPs accumulate the most units per rupee."
                ),
                priority=100,
                rule="panic_guard",
            )
        )

    # ── Rule 2: market dip nudge ─────────────────────────────────────────────
    nifty_change = market.get("nifty_change_pct")
    if isinstance(nifty_change, int | float) and nifty_change <= -3.0:
        nudges.append(
            Nudge(
                icon="info",
                title=f"Markets dipped {nifty_change:+.1f}% today",
                body=(
                    "Dips are when SIP investors quietly do best. Your fixed SIP "
                    "amount buys more units at lower NAVs. Long-run outcomes are "
                    "decided by staying invested across cycles, not by exiting "
                    "during them."
                ),
                priority=80,
                rule="market_dip",
            )
        )

    # ── Rule 3: tax-saving deadline nudge (Jan to March) ─────────────────────
    is_tax_window = now.month in (1, 2, 3)
    goal = (profile.get("primary_goal") or "").lower()
    if is_tax_window and ("tax" in goal or "80c" in goal or "elss" in goal):
        bracket = float(profile.get("tax_bracket_pct") or 30)
        max_savings = 150000 * (bracket / 100.0)
        nudges.append(
            Nudge(
                icon="info",
                title="80C deadline is 31 March",
                body=(
                    f"At a {int(bracket)} percent marginal rate, fully using the "
                    f"INR 1.5 lakh 80C limit could save you up to "
                    f"{_format_inr(max_savings)} of tax this year. "
                    f"ELSS has the shortest lock-in (3 years per SIP) among 80C "
                    f"equity options."
                ),
                priority=70,
                rule="tax_window",
            )
        )

    # ── Rule 4: tax-curious user (any month) ─────────────────────────────────
    elif any(_has_trigger(q, _TAX_TRIGGERS) for q in recent_questions):
        nudges.append(
            Nudge(
                icon="info",
                title="Tax: old vs new regime",
                body=(
                    "80C, 80D and HRA only apply under the old tax regime. Run "
                    "your numbers under both regimes before optimising for "
                    "deductions. Below ~INR 3 lakh of total deductions, the new "
                    "regime is often simpler and slightly better."
                ),
                priority=50,
                rule="tax_curious",
            )
        )

    # ── Rule 5: daily tip (rotation by day-of-year) ──────────────────────────
    tip_index = now.timetuple().tm_yday % len(_DAILY_TIPS)
    tip_title, tip_body = _DAILY_TIPS[tip_index]
    nudges.append(
        Nudge(
            icon="tip",
            title=tip_title,
            body=tip_body,
            priority=10,
            rule=f"daily_tip_{tip_index}",
        )
    )

    nudges.sort(key=lambda n: n["priority"], reverse=True)
    return nudges[:3]
