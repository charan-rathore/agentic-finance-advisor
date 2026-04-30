"""tests/test_calculators.py — golden-value coverage for core/calculators.py.

These tests are deterministic, offline, and fast. No mocks needed: the module
is pure arithmetic.
"""

from __future__ import annotations

import math

import pytest

from core.calculators import (
    ELSS_80C_DEDUCTION_CAP,
    elss_tax_savings,
    emergency_fund_target,
    is_calculator_question,
    lumpsum_vs_sip,
    sip_future_value,
    sip_needed_for_goal,
    step_up_sip,
)

# ── SIP future value ─────────────────────────────────────────────────────────


def test_sip_future_value_classic_5k_12pct_10y():
    """₹5,000/month at 12% for 10 years → ~₹11.6L (within 1% of widely-cited
    figure on AMFI/Groww/ET Money calculators)."""
    result = sip_future_value(5000, 12.0, 10)
    assert result["total_invested"] == 600_000.0
    assert 1_150_000 <= result["future_value"] <= 1_175_000
    assert result["estimated_returns"] == round(
        result["future_value"] - result["total_invested"], 2
    )


def test_sip_future_value_zero_years():
    result = sip_future_value(5000, 12.0, 0)
    assert result["total_invested"] == 0.0
    assert result["future_value"] == 0.0
    assert result["estimated_returns"] == 0.0


def test_sip_future_value_zero_return():
    """0% return → returns equal to invested."""
    result = sip_future_value(1000, 0.0, 5)
    assert result["total_invested"] == 60_000.0
    assert result["future_value"] == 60_000.0
    assert result["estimated_returns"] == 0.0


def test_sip_future_value_series_length():
    result = sip_future_value(1000, 10.0, 2, include_series=True)
    assert "monthly_series" in result
    assert len(result["monthly_series"]) == 24
    # Series must be monotonically non-decreasing for positive return
    series = result["monthly_series"]
    assert all(series[i] <= series[i + 1] + 1e-6 for i in range(len(series) - 1))


def test_sip_future_value_rejects_negative_inputs():
    with pytest.raises(ValueError):
        sip_future_value(-100, 12.0, 5)
    with pytest.raises(ValueError):
        sip_future_value(1000, 12.0, -1)


# ── Goal SIP ─────────────────────────────────────────────────────────────────


def test_goal_sip_one_million_in_5_years_at_12pct():
    """₹10L target in 5 years at 12% → monthly between ₹11.5k and ₹13.5k."""
    result = sip_needed_for_goal(1_000_000.0, 12.0, 5)
    assert 11_500 <= result["monthly_required"] <= 13_500
    assert result["target"] == 1_000_000.0
    assert result["total_invested"] == round(result["monthly_required"] * 60, 2)


def test_goal_sip_zero_return():
    """0% return → monthly = target / months."""
    result = sip_needed_for_goal(120_000.0, 0.0, 1)
    assert math.isclose(result["monthly_required"], 10_000.0, rel_tol=0.01)


def test_goal_sip_round_trip_with_sip_future_value():
    """If we compute the SIP needed for a goal and then plug that SIP back in,
    the future value should match the original target within rounding."""
    target = 5_000_000.0
    rate = 12.0
    years = 15
    inverse = sip_needed_for_goal(target, rate, years)
    forward = sip_future_value(inverse["monthly_required"], rate, years)
    assert math.isclose(forward["future_value"], target, rel_tol=0.001)


# ── ELSS tax savings ─────────────────────────────────────────────────────────


def test_elss_full_cap_30_percent_bracket():
    """₹2L invested, 30% bracket — deduction caps at ₹1.5L, tax saved = ₹45k."""
    result = elss_tax_savings(200_000.0, 30.0)
    assert result["deduction"] == ELSS_80C_DEDUCTION_CAP
    assert result["tax_saved"] == 45_000.0
    assert result["effective_cost"] == 200_000.0 - 45_000.0


def test_elss_below_cap_20_percent_bracket():
    """₹80k invested at 20% bracket — full deduction, ₹16k saved."""
    result = elss_tax_savings(80_000.0, 20.0)
    assert result["deduction"] == 80_000.0
    assert result["tax_saved"] == 16_000.0


def test_elss_zero_bracket_no_savings():
    result = elss_tax_savings(100_000.0, 0.0)
    assert result["tax_saved"] == 0.0
    assert result["effective_cost"] == 100_000.0


def test_elss_rejects_negative():
    with pytest.raises(ValueError):
        elss_tax_savings(-1, 30.0)
    with pytest.raises(ValueError):
        elss_tax_savings(100_000, -5)


# ── Step-up SIP ──────────────────────────────────────────────────────────────


def test_step_up_with_zero_step_matches_constant_sip():
    """A 0% step-up should produce the same FV as a constant SIP."""
    flat = sip_future_value(5000, 12.0, 5)
    stepped = step_up_sip(5000, 0.0, 12.0, 5)
    assert math.isclose(stepped["future_value"], flat["future_value"], rel_tol=0.001)


def test_step_up_grows_more_than_constant():
    """A 10% annual step-up should beat the same starting flat SIP."""
    flat = sip_future_value(5000, 12.0, 10)
    stepped = step_up_sip(5000, 10.0, 12.0, 10)
    assert stepped["future_value"] > flat["future_value"]
    assert stepped["total_invested"] > flat["total_invested"]


# ── Emergency fund ───────────────────────────────────────────────────────────


def test_emergency_fund_default_six_months():
    """₹40k/mo expenses × 6 months = ₹2.4L target; split sums to target."""
    result = emergency_fund_target(40_000.0)
    assert result["target_amount"] == 240_000.0
    split_sum = sum(result["suggested_split"].values())
    assert math.isclose(split_sum, 240_000.0, rel_tol=0.01)


def test_emergency_fund_three_months():
    result = emergency_fund_target(50_000.0, months=3)
    assert result["target_amount"] == 150_000.0


def test_emergency_fund_rejects_invalid_months():
    with pytest.raises(ValueError):
        emergency_fund_target(40_000, months=0)


# ── Lumpsum vs SIP ───────────────────────────────────────────────────────────


def test_lumpsum_beats_sip_in_rising_market():
    """At a steady positive return, lumpsum > SIP for the same total."""
    result = lumpsum_vs_sip(100_000.0, 10.0, 5)
    assert result["lumpsum_future_value"] > result["sip_future_value"]
    assert result["winner"] == "lumpsum"
    assert math.isclose(result["sip_monthly"], 100_000 / 60, rel_tol=0.001)


def test_lumpsum_vs_sip_zero_return_is_tie():
    result = lumpsum_vs_sip(100_000.0, 0.0, 5)
    assert math.isclose(
        result["lumpsum_future_value"], result["sip_future_value"], abs_tol=0.5
    )
    assert result["winner"] == "tie"


# ── Calculator-intent detector ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "Open the SIP calculator",
        "Calculate SIP for ₹5000",
        "kitna milega in 10 years",
        "How much will ₹2000 grow in 15 years?",
        "tax saved on ELSS?",
        "step-up SIP for retirement",
        "lumpsum vs SIP comparison",
        "I want to save ₹20 lakh",
    ],
)
def test_is_calculator_question_positive(question: str):
    assert is_calculator_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "What is a mutual fund?",
        "Why did Nifty drop today?",
        "Should I switch from PPF to ELSS?",
        "",
    ],
)
def test_is_calculator_question_negative(question: str):
    assert not is_calculator_question(question)
