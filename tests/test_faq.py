"""Tests for the deterministic FAQ matcher."""

from __future__ import annotations

import pytest

from core.faq import _normalise, faq_match, list_faq_pages


def test_list_faq_pages_returns_entries() -> None:
    pages = list_faq_pages()
    assert len(pages) >= 8, f"expected at least 8 FAQ pages, got {len(pages)}"
    slugs = {p.slug for p in pages}
    assert "what_is_sip" in slugs
    assert "elss_vs_ppf" in slugs
    assert "emergency_fund" in slugs


def test_normalise_lowers_and_strips_punctuation() -> None:
    assert _normalise("What is SIP?") == "what is sip"
    assert _normalise("ELSS vs. PPF!!") == "elss vs ppf"
    assert _normalise("  multiple   spaces  ") == "multiple spaces"


def test_faq_match_returns_none_for_empty_question() -> None:
    assert faq_match("") is None
    assert faq_match("   ") is None


def test_faq_match_finds_sip_question() -> None:
    hit = faq_match("What is SIP?")
    assert hit is not None
    assert hit.slug == "what_is_sip"
    assert "Systematic Investment Plan" in hit.answer


def test_faq_match_handles_hinglish_pattern() -> None:
    hit = faq_match("sip kya hai bhai")
    assert hit is not None
    assert hit.slug == "what_is_sip"


def test_faq_match_picks_longest_pattern() -> None:
    """When multiple FAQs could match, the longest pattern wins."""
    hit = faq_match("Should I stop my SIP since the market crashed?")
    assert hit is not None
    # "should i stop sip" (17) is more specific than "stop sip" (8)
    assert hit.slug == "should_i_stop_sip"


def test_faq_match_returns_none_for_unrelated_question() -> None:
    hit = faq_match("Where can I trade Bitcoin futures in Switzerland?")
    assert hit is None


def test_faq_match_for_emergency_fund() -> None:
    hit = faq_match("how much emergency fund do I need")
    assert hit is not None
    assert hit.slug == "emergency_fund"


def test_faq_match_includes_sources() -> None:
    hit = faq_match("how to start investing")
    assert hit is not None
    assert "SEBI" in hit.sources


@pytest.mark.parametrize(
    ("question", "expected_slug"),
    [
        ("what is nav", "what_is_nav"),
        ("how to save tax in india", "tax_save_india"),
        ("ELSS lock in period", "lock_in_rules"),
        ("how much should i invest", "how_much_to_invest"),
        ("index fund or active", "index_fund_or_active"),
    ],
)
def test_faq_match_targeted_questions(question: str, expected_slug: str) -> None:
    hit = faq_match(question)
    assert hit is not None, f"expected a hit for '{question}'"
    assert hit.slug == expected_slug
