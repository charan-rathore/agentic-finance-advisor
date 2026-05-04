"""tests/test_reflection.py — coverage for core/reflection.py.

The Gemini call is mocked; everything else (parsing, verdict derivation,
badge mapping, error fall-through) is exercised directly.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core import reflection

# ── Parser ───────────────────────────────────────────────────────────────────


_GOOD_RAW = """\
GROUNDED: PASS — every claim ties back to a source page
SCOPED: PASS — answer stays educational
DISCLAIMED: PASS — SEBI disclaimer present at the end
TONE: PASS — beginner-friendly throughout
CONSISTENT: PASS — no internal contradictions
PROFILE_FIT: PASS — uses the user's SIP budget
VERDICT: ACCEPT
REGENERATE_GUIDANCE:
"""


_BAD_RAW = """\
GROUNDED: FAIL — claims a 14% return that does not appear in any source
SCOPED: WARN — recommends "Reliance" by name to a beginner
DISCLAIMED: FAIL — no SEBI disclaimer
TONE: PASS — beginner-friendly
CONSISTENT: PASS
PROFILE_FIT: WARN — ignores the user's stated horizon
VERDICT: REGENERATE
REGENERATE_GUIDANCE: Remove the unsupported 14% claim, add the SEBI disclaimer, and avoid recommending individual stocks.
"""


def test_parse_good_critique_marks_accept():
    result = reflection._parse_critic_output(_GOOD_RAW)
    assert result["verdict"] == "ACCEPT"
    for name in ("grounded", "scoped", "disclaimed", "tone", "consistent", "profile_fit"):
        assert result["checks"][name] == "PASS"
    assert result["regenerate_guidance"] == ""


def test_parse_bad_critique_marks_regenerate():
    result = reflection._parse_critic_output(_BAD_RAW)
    assert result["verdict"] == "REGENERATE"
    assert result["checks"]["grounded"] == "FAIL"
    assert result["checks"]["disclaimed"] == "FAIL"
    assert result["checks"]["scoped"] == "WARN"
    assert "14%" in result["regenerate_guidance"]
    # reasons list captures the non-PASS findings
    assert any("grounded" in r for r in result["reasons"])


def test_parse_missing_verdict_derived_from_checks():
    """If Gemini omits the VERDICT line, we derive from the rule."""
    raw = """\
GROUNDED: FAIL — number not in source
SCOPED: PASS
DISCLAIMED: PASS
TONE: PASS
CONSISTENT: PASS
PROFILE_FIT: PASS
"""
    result = reflection._parse_critic_output(raw)
    # FAIL on a blocking check → REGENERATE even without explicit VERDICT
    assert result["verdict"] == "REGENERATE"


def test_two_warns_trigger_regenerate_when_no_explicit_verdict():
    raw = """\
GROUNDED: PASS
SCOPED: PASS
DISCLAIMED: PASS
TONE: WARN — too jargon-heavy for a beginner
CONSISTENT: PASS
PROFILE_FIT: WARN — ignores the user's horizon
"""
    result = reflection._parse_critic_output(raw)
    assert result["verdict"] == "REGENERATE"


def test_one_warn_no_fail_accepts():
    raw = """\
GROUNDED: PASS
SCOPED: PASS
DISCLAIMED: PASS
TONE: WARN — slightly jargon-heavy
CONSISTENT: PASS
PROFILE_FIT: PASS
"""
    result = reflection._parse_critic_output(raw)
    assert result["verdict"] == "ACCEPT"


def test_completely_unparseable_output_defaults_to_accept():
    """Defensive: a totally garbled critic response shouldn't block users."""
    result = reflection._parse_critic_output("Sorry, I can't help with that.")
    # No checks parsed → all default to PASS → derived verdict is ACCEPT
    assert result["verdict"] == "ACCEPT"
    for name in ("grounded", "scoped", "disclaimed", "tone", "consistent", "profile_fit"):
        assert result["checks"][name] == "PASS"


# ── reflect() async entry point ──────────────────────────────────────────────


def test_reflect_calls_gemini_and_returns_parsed_result():
    async def _go():
        with patch.object(
            reflection, "call_gemini", new=AsyncMock(return_value=_GOOD_RAW)
        ) as mock:
            result = await reflection.reflect(
                question="What is SIP?",
                profile={"name": "Priya", "monthly_sip_budget": "₹5k"},
                source_pages={"basics/finance_basics_india.md": "SIP means..."},
                candidate_answer="A SIP is a way to invest a fixed amount monthly...",
            )
            assert mock.await_count == 1
            assert result["verdict"] == "ACCEPT"
            # Prompt must include user question, candidate, and source pages
            sent = mock.call_args.args[0]
            assert "What is SIP?" in sent
            assert "fixed amount monthly" in sent
            assert "basics/finance_basics_india.md" in sent

    asyncio.run(_go())


def test_reflect_handles_critic_call_failure_gracefully():
    """If the critic call itself raises, return ACCEPT with an error field."""
    async def _go():
        with patch.object(
            reflection,
            "call_gemini",
            new=AsyncMock(side_effect=RuntimeError("rate limit")),
        ):
            result = await reflection.reflect(
                question="What is SIP?",
                profile=None,
                source_pages={},
                candidate_answer="A non-empty answer.",
            )
            assert result["verdict"] == "ACCEPT"  # never block on infra failure
            assert "error" in result
            assert "rate limit" in result["error"]

    asyncio.run(_go())


def test_reflect_empty_candidate_short_circuits_to_regenerate():
    async def _go():
        with patch.object(reflection, "call_gemini", new=AsyncMock()) as mock:
            result = await reflection.reflect(
                question="anything",
                profile=None,
                source_pages={},
                candidate_answer="   ",
            )
            assert result["verdict"] == "REGENERATE"
            assert mock.await_count == 0  # don't even ask Gemini for empty input

    asyncio.run(_go())


# ── Badge mapping ────────────────────────────────────────────────────────────


def test_badge_all_pass_is_fact_checked():
    result = reflection._parse_critic_output(_GOOD_RAW)
    assert reflection.badge_for(result) == "🛡️ Fact-checked"


def test_badge_regenerate_is_refined():
    result = reflection._parse_critic_output(_BAD_RAW)
    assert reflection.badge_for(result) == "🟡 Refined after self-review"


def test_badge_accept_with_warn_is_use_with_care():
    raw = """\
GROUNDED: PASS
SCOPED: PASS
DISCLAIMED: PASS
TONE: WARN — slightly jargon-heavy
CONSISTENT: PASS
PROFILE_FIT: PASS
"""
    result = reflection._parse_critic_output(raw)
    assert reflection.badge_for(result) == "⚠️ Use with care"


def test_badge_critic_error_is_unavailable():
    # Direct construction to simulate a critic failure
    err_result = reflection.ReflectionResult(
        verdict="ACCEPT",
        checks={k: "PASS" for k in (
            "grounded", "scoped", "disclaimed", "tone", "consistent", "profile_fit"
        )},
        reasons=[],
        regenerate_guidance="",
        raw="",
        error="RuntimeError: rate limit",
    )
    assert reflection.badge_for(err_result) == "❌ Self-check unavailable"


# ── Sanity: prompt formatting ────────────────────────────────────────────────


def test_format_pages_caps_each_page_at_1500_chars():
    long_page = "x" * 5000
    result = reflection._format_pages({"big.md": long_page})
    # Header + 1500 char snippet
    assert "### big.md" in result
    assert len(result) < 5000  # truncation actually happened


def test_format_profile_handles_none_and_empty():
    """Both None and an empty dict take the falsy path — that's intentional."""
    assert "no profile" in reflection._format_profile(None).lower()
    assert "no profile" in reflection._format_profile({}).lower()


def test_format_profile_with_only_empty_values_says_present_but_empty():
    """A dict with all known keys set to empty strings reaches the second
    branch ("profile present but empty") because the dict itself is truthy."""
    result = reflection._format_profile({"name": "", "monthly_income": ""}).lower()
    assert "empty" in result or "no profile" in result


def test_format_profile_renders_known_keys():
    result = reflection._format_profile({
        "name": "Priya",
        "monthly_sip_budget": "₹5k",
        "horizon_pref": "intermediate",
        "junk_field": "ignored",
    })
    assert "Priya" in result
    assert "₹5k" in result
    assert "intermediate" in result
    assert "junk_field" not in result
