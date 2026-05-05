"""Tests for the deterministic nudge engine."""

from __future__ import annotations

from datetime import UTC, datetime

from core.nudges import generate_nudges


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def test_default_returns_at_least_one_daily_tip() -> None:
    nudges = generate_nudges(now=_at(2026, 5, 15))
    assert len(nudges) >= 1
    assert any(n["rule"].startswith("daily_tip_") for n in nudges)


def test_panic_question_triggers_panic_guard_first() -> None:
    nudges = generate_nudges(
        recent_questions=["should I stop my SIP this market is scary"],
        now=_at(2026, 5, 15),
    )
    # Panic guard has priority 100, should land first
    assert nudges[0]["rule"] == "panic_guard"
    assert "Pausing" in nudges[0]["body"] or "compounds" in nudges[0]["body"]


def test_hinglish_panic_phrase_triggers_panic_guard() -> None:
    nudges = generate_nudges(
        recent_questions=["market gir gaya, sip band karu kya"],
        now=_at(2026, 5, 15),
    )
    assert nudges[0]["rule"] == "panic_guard"


def test_market_dip_triggers_when_nifty_drops_three_percent() -> None:
    nudges = generate_nudges(
        market={"nifty_change_pct": -3.4},
        now=_at(2026, 5, 15),
    )
    assert any(n["rule"] == "market_dip" for n in nudges)
    dip = next(n for n in nudges if n["rule"] == "market_dip")
    assert "-3.4%" in dip["title"] or "-3.4" in dip["title"]


def test_market_dip_does_not_trigger_for_small_moves() -> None:
    nudges = generate_nudges(
        market={"nifty_change_pct": -1.2},
        now=_at(2026, 5, 15),
    )
    assert not any(n["rule"] == "market_dip" for n in nudges)


def test_tax_window_nudge_fires_in_february_with_tax_goal() -> None:
    nudges = generate_nudges(
        profile={"primary_goal": "Save tax (80C)", "tax_bracket_pct": 30},
        now=_at(2026, 2, 15),
    )
    assert any(n["rule"] == "tax_window" for n in nudges)
    tax = next(n for n in nudges if n["rule"] == "tax_window")
    assert "31 March" in tax["body"] or "INR" in tax["body"]


def test_tax_window_nudge_does_not_fire_in_august() -> None:
    nudges = generate_nudges(
        profile={"primary_goal": "Save tax (80C)", "tax_bracket_pct": 30},
        now=_at(2026, 8, 15),
    )
    assert not any(n["rule"] == "tax_window" for n in nudges)


def test_tax_curious_nudge_fires_outside_window() -> None:
    nudges = generate_nudges(
        recent_questions=["how do I save tax in India"],
        now=_at(2026, 8, 15),
    )
    assert any(n["rule"] == "tax_curious" for n in nudges)


def test_returns_at_most_three_nudges() -> None:
    nudges = generate_nudges(
        profile={"primary_goal": "Save tax (80C)", "tax_bracket_pct": 30},
        recent_questions=["should I stop my SIP", "how to save tax"],
        market={"nifty_change_pct": -4.5},
        now=_at(2026, 2, 15),
    )
    assert len(nudges) <= 3


def test_priority_ordering_descending() -> None:
    nudges = generate_nudges(
        recent_questions=["should I stop my SIP"],
        market={"nifty_change_pct": -3.5},
        now=_at(2026, 5, 15),
    )
    priorities = [n["priority"] for n in nudges]
    assert priorities == sorted(priorities, reverse=True)


def test_deterministic_for_same_inputs() -> None:
    args = {
        "profile": {"primary_goal": "Grow wealth (SIP)"},
        "recent_questions": [],
        "market": {},
        "now": _at(2026, 5, 15),
    }
    a = generate_nudges(**args)
    b = generate_nudges(**args)
    assert a == b
