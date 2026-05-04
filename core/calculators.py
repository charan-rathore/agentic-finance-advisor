"""
core/calculators.py

Deterministic Indian-investing calculators. Pure Python, no LLM, no I/O, no
external services. These are the "instant" answers that should never go through
the Gemini path because the math is exact and hallucination-free.

Every function returns a serialisable dict so callers (UI cards, Gemini prompt
context, FAQ pre-rendered answers) can consume the same structured shape.

All ₹ amounts are floats; rates are *percent* numbers (e.g. 12.0 means 12% per
annum) to match how Indian retail users phrase them. Internal computations use
the equivalent decimal where appropriate.

Designed to be importable without side effects so it can be safely loaded by
both the agent runtime and the Streamlit UI.
"""

from __future__ import annotations

from typing import TypedDict

# ── Public return shapes ─────────────────────────────────────────────────────


class SipResult(TypedDict, total=False):
    monthly: float
    annual_return_pct: float
    years: int
    total_invested: float
    estimated_returns: float
    future_value: float
    monthly_series: list[float]


class GoalResult(TypedDict, total=False):
    target: float
    annual_return_pct: float
    years: int
    monthly_required: float
    total_invested: float
    estimated_returns: float


class ElssResult(TypedDict):
    annual_invested: float
    tax_bracket_pct: float
    deduction: float
    tax_saved: float
    effective_cost: float


class StepUpResult(TypedDict, total=False):
    base_monthly: float
    annual_step_up_pct: float
    annual_return_pct: float
    years: int
    total_invested: float
    estimated_returns: float
    future_value: float
    monthly_series: list[float]


class EmergencyFundResult(TypedDict):
    monthly_expenses: float
    months: int
    target_amount: float
    suggested_split: dict[str, float]


class LumpsumVsSipResult(TypedDict):
    amount: float
    annual_return_pct: float
    years: int
    lumpsum_future_value: float
    sip_monthly: float
    sip_future_value: float
    difference: float
    winner: str


# ── Internal helpers ─────────────────────────────────────────────────────────


def _monthly_rate(annual_return_pct: float) -> float:
    """Convert an annualised percentage into a monthly decimal rate."""
    return annual_return_pct / 100.0 / 12.0


def _months(years: int) -> int:
    return int(years) * 12


# ── Public calculators ───────────────────────────────────────────────────────


def sip_future_value(
    monthly: float,
    annual_return_pct: float,
    years: int,
    *,
    include_series: bool = False,
) -> SipResult:
    """Future value of a constant-monthly SIP.

    Standard formula: FV = P × [((1+r)^n − 1) / r] × (1+r)
    where r = monthly rate, n = number of months. The trailing (1+r) factor
    assumes contributions are made at the *start* of each month, which matches
    how AMFI displays SIP returns in factsheets.

    Edge cases handled:
    - ``years == 0`` → zero invested, zero returned
    - ``annual_return_pct == 0`` → simple sum, no compounding
    - negative ``annual_return_pct`` → still computed; users may want to
      stress-test downside scenarios
    """
    if monthly < 0:
        raise ValueError("monthly contribution must be non-negative")
    if years < 0:
        raise ValueError("years must be non-negative")

    n = _months(years)
    total_invested = round(monthly * n, 2)

    if n == 0:
        return SipResult(
            monthly=float(monthly),
            annual_return_pct=float(annual_return_pct),
            years=int(years),
            total_invested=0.0,
            estimated_returns=0.0,
            future_value=0.0,
        )

    r = _monthly_rate(annual_return_pct)
    if r == 0:
        future_value = total_invested
    else:
        future_value = monthly * (((1 + r) ** n - 1) / r) * (1 + r)

    out: SipResult = {
        "monthly": float(monthly),
        "annual_return_pct": float(annual_return_pct),
        "years": int(years),
        "total_invested": total_invested,
        "estimated_returns": round(future_value - total_invested, 2),
        "future_value": round(future_value, 2),
    }

    if include_series:
        series: list[float] = []
        balance = 0.0
        for _ in range(n):
            balance = (balance + monthly) * (1 + r)
            series.append(round(balance, 2))
        out["monthly_series"] = series

    return out


def sip_needed_for_goal(
    target: float,
    annual_return_pct: float,
    years: int,
) -> GoalResult:
    """Reverse of ``sip_future_value`` — the SIP needed to reach a target.

    Solves the SIP FV formula for the monthly contribution.
    """
    if target < 0:
        raise ValueError("target must be non-negative")
    if years <= 0:
        raise ValueError("years must be > 0 for a goal calculation")

    n = _months(years)
    r = _monthly_rate(annual_return_pct)

    if r == 0:
        monthly_required = target / n
    else:
        # P = FV / [((1+r)^n − 1)/r × (1+r)]
        monthly_required = target / (((1 + r) ** n - 1) / r * (1 + r))

    monthly_required = round(monthly_required, 2)
    total_invested = round(monthly_required * n, 2)

    return GoalResult(
        target=float(target),
        annual_return_pct=float(annual_return_pct),
        years=int(years),
        monthly_required=monthly_required,
        total_invested=total_invested,
        estimated_returns=round(target - total_invested, 2),
    )


# ── ELSS / 80C tax-saving math ───────────────────────────────────────────────

ELSS_80C_DEDUCTION_CAP = 150_000.0  # ₹1.5L cap for FY 2024-25, unchanged FY 2025-26


def elss_tax_savings(
    annual_invested: float,
    tax_bracket_pct: float,
) -> ElssResult:
    """Income-tax savings from an ELSS contribution under §80C.

    Caps the deduction at ₹1,50,000 (the Section 80C limit). Anything above
    that does not provide additional 80C benefit (though it may still earn
    market returns).
    """
    if annual_invested < 0:
        raise ValueError("annual_invested must be non-negative")
    if tax_bracket_pct < 0:
        raise ValueError("tax_bracket_pct must be non-negative")

    deduction = min(float(annual_invested), ELSS_80C_DEDUCTION_CAP)
    tax_saved = deduction * (tax_bracket_pct / 100.0)
    effective_cost = float(annual_invested) - tax_saved

    return ElssResult(
        annual_invested=float(annual_invested),
        tax_bracket_pct=float(tax_bracket_pct),
        deduction=round(deduction, 2),
        tax_saved=round(tax_saved, 2),
        effective_cost=round(effective_cost, 2),
    )


# ── Step-up SIP ──────────────────────────────────────────────────────────────


def step_up_sip(
    base_monthly: float,
    annual_step_up_pct: float,
    annual_return_pct: float,
    years: int,
    *,
    include_series: bool = False,
) -> StepUpResult:
    """SIP with a fixed annual percentage increase applied each year.

    Year 1 contributes ``base_monthly`` × 12; year 2 contributes
    ``base_monthly × (1 + step_up)`` × 12; and so on. Compounded monthly at
    ``annual_return_pct`` throughout. Useful for users whose income grows
    each year and who want to step up SIPs in lockstep.
    """
    if base_monthly < 0 or annual_step_up_pct < 0 or years < 0:
        raise ValueError("inputs must be non-negative")

    r = _monthly_rate(annual_return_pct)
    monthly_contrib = float(base_monthly)
    balance = 0.0
    total_invested = 0.0
    series: list[float] = []

    for year in range(int(years)):
        for _ in range(12):
            balance = (balance + monthly_contrib) * (1 + r)
            total_invested += monthly_contrib
            if include_series:
                series.append(round(balance, 2))
        # Step up at year boundary (after the year's 12 contributions)
        if year < years - 1:
            monthly_contrib *= 1 + annual_step_up_pct / 100.0

    out: StepUpResult = {
        "base_monthly": float(base_monthly),
        "annual_step_up_pct": float(annual_step_up_pct),
        "annual_return_pct": float(annual_return_pct),
        "years": int(years),
        "total_invested": round(total_invested, 2),
        "estimated_returns": round(balance - total_invested, 2),
        "future_value": round(balance, 2),
    }
    if include_series:
        out["monthly_series"] = series
    return out


# ── Emergency fund target ────────────────────────────────────────────────────


def emergency_fund_target(
    monthly_expenses: float,
    months: int = 6,
) -> EmergencyFundResult:
    """Target corpus for an emergency fund.

    Standard guidance: 3 months for stable salaried, 6 for variable income, 9
    for single-earner households or freelancers. Default 6 months is a
    conservative middle-of-the-road number we recommend for most users.

    The suggested split is a rule-of-thumb three-bucket allocation:
    - 30%   — savings account (immediate liquidity, ATM access)
    - 40%   — sweep / liquid mutual fund (T+1 redemption, slightly better yield)
    - 30%   — short-term FD / overnight fund (highest of the three for last-resort)
    """
    if monthly_expenses < 0:
        raise ValueError("monthly_expenses must be non-negative")
    if months <= 0:
        raise ValueError("months must be positive")

    target = round(float(monthly_expenses) * months, 2)

    return EmergencyFundResult(
        monthly_expenses=float(monthly_expenses),
        months=int(months),
        target_amount=target,
        suggested_split={
            "savings_account": round(target * 0.30, 2),
            "liquid_fund": round(target * 0.40, 2),
            "short_term_fd": round(target * 0.30, 2),
        },
    )


# ── Lumpsum vs SIP comparison ────────────────────────────────────────────────


def lumpsum_vs_sip(
    amount: float,
    annual_return_pct: float,
    years: int,
) -> LumpsumVsSipResult:
    """Compare investing ``amount`` as a single lumpsum vs an equal-total SIP.

    The SIP variant invests ``amount / months`` each month for the same horizon
    so total contribution matches. Mathematically the lumpsum almost always
    wins in a steadily-rising market because every rupee compounds for the
    full horizon, whereas SIP rupees compound for progressively shorter
    fractions. The realistic counter-argument (rupee-cost averaging on
    volatile markets) is empirical and lives outside this calculator.
    """
    if amount <= 0 or years <= 0:
        raise ValueError("amount and years must be > 0")

    n = _months(years)
    r = _monthly_rate(annual_return_pct)

    lumpsum_fv = amount * ((1 + r) ** n) if r != 0 else amount

    sip_monthly = amount / n
    if r == 0:
        sip_fv = sip_monthly * n
    else:
        sip_fv = sip_monthly * (((1 + r) ** n - 1) / r) * (1 + r)

    diff = round(lumpsum_fv - sip_fv, 2)
    winner = "lumpsum" if diff > 0 else "sip" if diff < 0 else "tie"

    return LumpsumVsSipResult(
        amount=float(amount),
        annual_return_pct=float(annual_return_pct),
        years=int(years),
        lumpsum_future_value=round(lumpsum_fv, 2),
        sip_monthly=round(sip_monthly, 2),
        sip_future_value=round(sip_fv, 2),
        difference=diff,
        winner=winner,
    )


# ── Convenience: detect a calculator-shaped question ─────────────────────────


_CALCULATOR_TRIGGERS: tuple[str, ...] = (
    "sip calculator",
    "calculate sip",
    "kitna milega",
    "kitna return",
    "how much will",
    "future value",
    "fv of",
    "emi for",
    "tax saved",
    "tax saving",
    "elss tax",
    "80c saving",
    "emergency fund",
    "step up sip",
    "step-up sip",
    "lumpsum vs sip",
    "sip vs lumpsum",
    "goal planner",
    "i want to save",
    "i want to accumulate",
)


def is_calculator_question(question: str) -> bool:
    """Cheap rule-based pre-check for calculator-shaped intents.

    The intent classifier in core/intent.py (P1.9) will eventually subsume
    this with a Gemini call; until then the chat handler can short-circuit
    obvious calculator questions to the deterministic path with zero LLM cost.
    """
    if not question:
        return False
    q = question.lower()
    return any(t in q for t in _CALCULATOR_TRIGGERS)
