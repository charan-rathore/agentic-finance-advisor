"""
tests/test_user_profile.py

Tests for:
1. UserProfile ORM model — creation, persistence, defaults.
2. Profile-aware query_india — verifies that the profile context block is
   injected into the Gemini prompt captured by the mock.
3. _profile_block helper — renders correct fields / empty string for None.

No network calls; no Gemini calls; no real SQLite file.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import call, patch

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from core.models import UserProfile, init_db
from core.wiki_india import _profile_block

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session():
    """In-memory SQLite session, torn down after each test."""
    engine = init_db("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s


SAMPLE_PROFILE = {
    "name": "Priya",
    "monthly_income": "₹50k–₹1L",
    "monthly_sip_budget": "₹5k–₹10k",
    "risk_tolerance": "medium",
    "tax_bracket_pct": 20.0,
    "primary_goal": "Grow wealth (SIP)",
    "horizon_pref": "intermediate",
}


# ── UserProfile ORM tests ─────────────────────────────────────────────────────


class TestUserProfileModel:
    def test_table_created(self):
        engine = init_db("sqlite:///:memory:")
        assert "user_profiles" in inspect(engine).get_table_names()

    def test_all_pre_existing_tables_still_present(self):
        engine = init_db("sqlite:///:memory:")
        tables = set(inspect(engine).get_table_names())
        for t in (
            "market_snapshots",
            "news_articles",
            "insights",
            "fetch_runs",
            "source_registry",
            "knowledge_versions",
        ):
            assert t in tables, f"Additive migration must not drop {t}"

    def test_insert_and_retrieve(self, db_session):
        db_session.add(UserProfile(**SAMPLE_PROFILE))
        db_session.commit()

        row = db_session.query(UserProfile).one()
        assert row.name == "Priya"
        assert row.monthly_income == "₹50k–₹1L"
        assert row.monthly_sip_budget == "₹5k–₹10k"
        assert row.risk_tolerance == "medium"
        assert row.tax_bracket_pct == 20.0
        assert row.primary_goal == "Grow wealth (SIP)"
        assert row.horizon_pref == "intermediate"
        assert isinstance(row.created_at, datetime)

    def test_created_at_auto_populated(self, db_session):
        db_session.add(UserProfile(**SAMPLE_PROFILE))
        db_session.commit()
        row = db_session.query(UserProfile).one()
        assert row.created_at is not None

    def test_default_name(self, db_session):
        p = UserProfile(
            monthly_income="Below ₹25k",
            monthly_sip_budget="Below ₹1k",
            risk_tolerance="low",
            tax_bracket_pct=0.0,
            primary_goal="Build emergency fund",
            horizon_pref="short",
        )
        db_session.add(p)
        db_session.commit()
        assert db_session.query(UserProfile).one().name == "Investor"

    def test_first_row_semantics(self, db_session):
        """Second insert is allowed; caller reads by id ASC."""
        for i in range(3):
            db_session.add(
                UserProfile(
                    name=f"User{i}",
                    monthly_income="₹25k–₹50k",
                    monthly_sip_budget="₹1k–₹2k",
                    risk_tolerance="low",
                    tax_bracket_pct=5.0,
                    primary_goal="Save tax (80C)",
                    horizon_pref="intermediate",
                )
            )
        db_session.commit()
        first = db_session.query(UserProfile).order_by(UserProfile.id.asc()).first()
        assert first.name == "User0"


# ── _profile_block helper ─────────────────────────────────────────────────────


class TestProfileBlock:
    def test_returns_empty_string_for_none(self):
        assert _profile_block(None) == ""

    def test_returns_empty_string_for_empty_dict(self):
        # Empty dict is falsy — same as None
        assert _profile_block({}) == ""

    def test_contains_all_fields(self):
        block = _profile_block(SAMPLE_PROFILE)
        assert "₹50k–₹1L" in block
        assert "₹5k–₹10k" in block
        assert "medium" in block
        assert "20.0" in block
        assert "Grow wealth (SIP)" in block
        assert "intermediate" in block

    def test_contains_header_label(self):
        block = _profile_block(SAMPLE_PROFILE)
        assert "USER PROFILE" in block

    def test_missing_keys_do_not_raise(self):
        partial = {"monthly_income": "₹50k–₹1L"}
        block = _profile_block(partial)
        assert "₹50k–₹1L" in block
        assert "unknown" in block  # missing keys fall back to "unknown"


# ── query_india profile injection ─────────────────────────────────────────────


class TestQueryIndiaProfileInjection:
    """
    Verify that _profile_block content reaches the Gemini prompt when a profile
    is supplied.  We capture every call_gemini invocation and check the prompt
    text — no real Gemini call is made.
    """

    def _make_tmp_wiki(self, tmp_path):
        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\nmarket: india\n---\n# Basics\nContent here."
        )
        (tmp_path / "index.md").write_text("# Index\n- basics/finance_basics_india.md\n")

    def test_profile_context_in_intermediate_prompt(self, tmp_path):
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics\nSIP info."
        )

        captured_prompts: list[str] = []

        async def mock_gemini(prompt: str) -> str:
            captured_prompts.append(prompt)
            return "Mock answer about SIP."

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "call_gemini", side_effect=mock_gemini),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            asyncio.run(
                wiki_india.intermediate_india_answer(
                    "Which ELSS should I pick for 80c?",
                    profile=SAMPLE_PROFILE,
                )
            )

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "₹5k–₹10k" in prompt, "SIP budget must appear in prompt"
        assert "medium" in prompt, "risk_tolerance must appear in prompt"
        assert "20.0" in prompt, "tax_bracket_pct must appear in prompt"
        assert "USER PROFILE" in prompt

    def test_profile_context_in_short_term_prompt(self, tmp_path):
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics\nFD info."
        )

        captured: list[str] = []

        async def mock_gemini(prompt: str) -> str:
            captured.append(prompt)
            return "Park in liquid fund."

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "call_gemini", side_effect=mock_gemini),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            asyncio.run(
                wiki_india.short_term_india_answer(
                    "Where to park money for 6 months?",
                    profile=SAMPLE_PROFILE,
                )
            )

        assert "USER PROFILE" in captured[0]
        assert "₹50k–₹1L" in captured[0]

    def test_profile_context_in_long_term_prompt(self, tmp_path):
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics\nNPS PPF info."
        )

        captured: list[str] = []

        async def mock_gemini(prompt: str) -> str:
            captured.append(prompt)
            return "Open NPS."

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "call_gemini", side_effect=mock_gemini),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            asyncio.run(
                wiki_india.long_term_india_answer(
                    "How to plan for retirement?",
                    profile={**SAMPLE_PROFILE, "horizon_pref": "long"},
                )
            )

        assert "USER PROFILE" in captured[0]
        assert "Grow wealth (SIP)" in captured[0]

    def test_query_india_uses_profile_horizon_pref(self, tmp_path):
        """horizon_pref from profile overrides question-level signal."""
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics"
        )

        short_profile = {**SAMPLE_PROFILE, "horizon_pref": "short"}

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(
                wiki_india,
                "short_term_india_answer",
                return_value=("FD answer", []),
            ) as mock_short,
            patch.object(wiki_india, "intermediate_india_answer") as mock_mid,
            patch.object(wiki_india, "long_term_india_answer") as mock_long,
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            # The question has no horizon signal — but profile says "short"
            answer, _ = asyncio.run(
                wiki_india.query_india("Is gold a good investment?", profile=short_profile)
            )

        mock_short.assert_awaited_once()
        mock_mid.assert_not_awaited()
        mock_long.assert_not_awaited()
        assert answer == "FD answer"

    def test_no_profile_no_injection(self, tmp_path):
        """When profile=None, profile data values must NOT appear in prompt."""
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics"
        )

        captured: list[str] = []

        async def mock_gemini(prompt: str) -> str:
            captured.append(prompt)
            return "Answer without profile."

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "call_gemini", side_effect=mock_gemini),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            asyncio.run(
                wiki_india.short_term_india_answer(
                    "Where to park money for 6 months?",
                    profile=None,
                )
            )

        # _profile_block(None) returns "" so profile-specific data must not appear
        assert "Monthly income range" not in captured[0]
        assert "Monthly SIP budget" not in captured[0]
        assert "Risk tolerance" not in captured[0]
