"""
tests/test_india_wiki.py

Unit tests for core/wiki_india.py.

No Gemini calls are made — call_gemini is monkeypatched throughout.
No disk writes reach the real data/ directory — _iwrite is patched.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from core.wiki_india import (
    classify_investment_horizon,
    detect_beginner_intent_india,
    india_wiki_health,
    list_india_wiki_pages,
)

# ── detect_beginner_intent_india ──────────────────────────────────────────────


class TestDetectBeginnerIntentIndia:
    @pytest.mark.parametrize(
        "question",
        [
            "what is sip",
            "How to invest in India for beginners",
            "I'm new to investing, where do I start?",
            "What is a mutual fund?",
            "best sip to start with 500 rupees",
            "how to open demat account",
            "what is elss",
            "how to save tax in india under 80c",
            "how does sip work",
        ],
    )
    def test_detects_beginner_signals(self, question: str):
        assert detect_beginner_intent_india(question) is True

    @pytest.mark.parametrize(
        "question",
        [
            "What is the current price of TCS?",
            "Compare HDFC Bank vs ICICI Bank for a long-term portfolio",
            "What is the repo rate effect on debt funds?",
            "Should I redeem my Parag Parikh fund now?",
        ],
    )
    def test_does_not_trigger_on_experienced_questions(self, question: str):
        assert detect_beginner_intent_india(question) is False


# ── classify_investment_horizon ───────────────────────────────────────────────


class TestClassifyInvestmentHorizon:
    """
    The classifier returns exactly one of:
    "short" | "intermediate" | "long" | "unknown"
    """

    @pytest.mark.parametrize(
        "question",
        [
            "I need money in 6 months, where to park it?",
            "Best liquid fund for parking money",
            "Where to invest for emergency fund in fixed deposit?",
            "Looking for a t-bill investment",
            "I need an overnight fund for parking money",
        ],
    )
    def test_classifies_short(self, question: str) -> None:
        assert classify_investment_horizon(question) == "short"

    @pytest.mark.parametrize(
        "question",
        [
            "Best SIP plan for 3 years",
            "ELSS fund for tax saving under 80c",
            "I want to save tax and invest for a few years",
            "Which index fund should I start a SIP in?",
            "balanced fund for medium term goals",
        ],
    )
    def test_classifies_intermediate(self, question: str) -> None:
        assert classify_investment_horizon(question) == "intermediate"

    @pytest.mark.parametrize(
        "question",
        [
            "I want to build wealth over 10 years for retirement",
            "NPS investment for the long term",
            "PPF account for children education corpus",
            "Long-term wealth creation over a decade",
            "Planning for retirement in 20 years",
        ],
    )
    def test_classifies_long(self, question: str) -> None:
        assert classify_investment_horizon(question) == "long"

    @pytest.mark.parametrize(
        "question",
        [
            "What should I do with my savings?",
            "Is gold a good investment?",
            "Compare HDFC Bank vs ICICI Bank",
        ],
    )
    def test_classifies_unknown(self, question: str) -> None:
        assert classify_investment_horizon(question) == "unknown"

    def test_ambiguous_multiple_buckets_returns_unknown(self) -> None:
        # "liquid" (short) + "retirement" (long) → both hit → unknown
        q = "liquid fund for retirement planning long term"
        assert classify_investment_horizon(q) == "unknown"

    def test_return_values_are_exact_literals(self) -> None:
        """Guard against returning legacy 'short_term' / 'long_term' strings."""
        valid = {"short", "intermediate", "long", "unknown"}
        probes = [
            "liquid fund",
            "sip for 3 years",
            "nps retirement",
            "what is investing",
        ]
        for q in probes:
            result = classify_investment_horizon(q)
            assert result in valid, f"Unexpected value {result!r} for question: {q!r}"


# ── list_india_wiki_pages ─────────────────────────────────────────────────────


class TestListIndiaWikiPages:
    def test_returns_empty_list_when_dir_missing(self, tmp_path):
        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path / "nonexistent")
            result = list_india_wiki_pages()
        assert result == []

    def test_returns_relative_paths(self, tmp_path):
        (tmp_path / "equities").mkdir()
        (tmp_path / "equities" / "TCS.NS.md").write_text("content")
        (tmp_path / "macro" / "rbi_rates.md").parent.mkdir()
        (tmp_path / "macro" / "rbi_rates.md").write_text("content")

        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            result = list_india_wiki_pages()

        assert "equities/TCS.NS.md" in result
        assert "macro/rbi_rates.md" in result
        assert all(not r.startswith("/") for r in result)


# ── india_wiki_health ─────────────────────────────────────────────────────────


class TestIndiaWikiHealth:
    def test_returns_dict_with_correct_keys(self, tmp_path):
        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path / "nonexistent")
            result = india_wiki_health()

        assert "checked_at" in result
        assert "total_pages" in result
        assert "fresh" in result
        assert "stale" in result
        assert "missing_frontmatter" in result
        assert "by_type" in result

    def test_empty_wiki_dir_returns_zero_pages(self, tmp_path):
        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path / "empty")
            result = india_wiki_health()

        assert result["total_pages"] == 0

    def test_fresh_page_classified_correctly(self, tmp_path):
        from datetime import UTC, datetime

        basics_dir = tmp_path / "basics"
        basics_dir.mkdir()

        # Write a page with a recent timestamp
        recent = datetime.now(UTC).isoformat()
        (basics_dir / "finance_basics_india.md").write_text(
            f"---\npage_type: reference\nlast_updated: {recent}\nttl_hours: 9999\n---\nContent"
        )

        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            result = india_wiki_health()

        assert result["total_pages"] == 1
        assert len(result["fresh"]) == 1
        assert len(result["stale"]) == 0

    def test_stale_page_classified_correctly(self, tmp_path):
        basics_dir = tmp_path / "basics"
        basics_dir.mkdir()

        (basics_dir / "old_page.md").write_text(
            "---\npage_type: reference\nlast_updated: 2020-01-01T00:00:00+00:00\nttl_hours: 1\n---\nOld content"
        )

        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            result = india_wiki_health()

        assert len(result["stale"]) == 1
        assert result["stale"][0]["path"] == "basics/old_page.md"
        assert "overdue_hours" in result["stale"][0]

    def test_insights_excluded_from_count(self, tmp_path):
        """Insight and log files should be skipped in the health count."""
        insights_dir = tmp_path / "insights"
        insights_dir.mkdir()
        (insights_dir / "2026-04-25_10-00.md").write_text("insight content")
        (tmp_path / "log.md").write_text("log content")

        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            result = india_wiki_health()

        assert result["total_pages"] == 0

    def test_missing_frontmatter_page_classified(self, tmp_path):
        basics_dir = tmp_path / "basics"
        basics_dir.mkdir()
        (basics_dir / "no_frontmatter.md").write_text("No YAML here, just content.")

        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            result = india_wiki_health()

        assert "basics/no_frontmatter.md" in result["missing_frontmatter"]


# ── ingest_india (lightweight smoke tests) ────────────────────────────────────


class TestIngestIndiaSmoke:
    """
    We don't test the LLM prompt content — we test that ingest_india:
    - calls call_gemini the expected number of times
    - writes the expected files via _iwrite
    - does not raise on empty inputs
    """

    def test_empty_inputs_does_not_call_gemini(self):
        from core import wiki_india

        with patch.object(wiki_india, "call_gemini") as mock_gemini:
            asyncio.run(wiki_india.ingest_india())
        mock_gemini.assert_not_called()

    def test_single_price_triggers_equity_page_write(self):
        from core import wiki_india

        prices = [
            {
                "symbol": "TCS.NS",
                "exchange": "NSE",
                "price_inr": 2396.90,
                "volume": 1_000_000.0,
                "timestamp": "2026-04-25T10:00:00+00:00",
                "source": "yfinance_nse",
                "market_time": "2026-04-25 10:00 UTC",
            }
        ]
        writes: list[str] = []

        with (
            patch.object(wiki_india, "call_gemini", return_value="## Mock page content"),
            patch.object(wiki_india, "_iwrite", side_effect=lambda p, c, **_kw: writes.append(p)),
            patch.object(wiki_india, "_iappend_log"),
        ):
            asyncio.run(wiki_india.ingest_india(prices=prices))

        written_paths = set(writes)
        assert any("equities/TCS.NS.md" in p for p in written_paths)
        assert any("overview.md" in p for p in written_paths)
        assert any("index.md" in p for p in written_paths)

    def test_rbi_rates_triggers_macro_page_write(self):
        from core import wiki_india

        rbi = {
            "repo_rate_pct": 5.25,
            "source": "rbi_fallback",
            "fetched_at": "2026-04-25T10:00:00Z",
        }
        writes: list[str] = []

        with (
            patch.object(wiki_india, "call_gemini", return_value="## Mock macro page"),
            patch.object(wiki_india, "_iwrite", side_effect=lambda p, c, **_kw: writes.append(p)),
            patch.object(wiki_india, "_iappend_log"),
        ):
            asyncio.run(wiki_india.ingest_india(rbi_rates=rbi))

        assert any("macro/rbi_rates.md" in p for p in writes)


# ── query_india (lightweight smoke tests) ─────────────────────────────────────


class TestQueryIndiaSmoke:
    def test_returns_fallback_when_index_missing(self, tmp_path):
        """
        When the index is missing and no horizon is detected, the fallback message
        should be returned without any LLM call.
        The question must NOT trigger horizon routing (neutral question).
        """
        from core import wiki_india

        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path / "empty")
            # "Is gold a good investment?" has no horizon signals → reaches fallback
            answer, consulted = asyncio.run(
                wiki_india.query_india("Is gold a good investment in India?")
            )

        assert "still being built" in answer.lower() or "wait" in answer.lower()
        assert consulted == []

    def test_returns_answer_and_consulted_pages(self, tmp_path):
        from core import wiki_india

        # Write a minimal index and basics page
        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\nmarket: india\n---\n# Basics\nGold is a traditional asset."
        )
        (tmp_path / "index.md").write_text("# Index\n- basics/finance_basics_india.md\n")

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "call_gemini") as mock_gemini,
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            # First call = routing, returns the basics page path
            # Second call = actual answer generation
            # "Is gold a good investment?" → unknown horizon → uses wiki pipeline
            mock_gemini.side_effect = [
                "basics/finance_basics_india.md",
                "Gold is a traditional store of value in India.",
            ]
            answer, consulted = asyncio.run(
                wiki_india.query_india("Is gold a good investment in India?")
            )

        assert len(answer) > 0
        assert isinstance(consulted, list)


# ── Horizon routing inside query_india ────────────────────────────────────────


class TestQueryIndiaHorizonRouting:
    """
    query_india must delegate to the specialist flows when a horizon is detected,
    without ever calling the full LLM wiki-retrieval pipeline (i.e. call_gemini
    for routing is NOT invoked on the first call).
    """

    def _run(self, coro):  # tiny helper to avoid repeating asyncio.run
        return asyncio.run(coro)

    def test_short_horizon_routes_to_short_term_flow(self, tmp_path):
        from core import wiki_india

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(
                wiki_india,
                "short_term_india_answer",
                return_value=("FD answer", ["basics/finance_basics_india.md"]),
            ) as mock_short,
            patch.object(wiki_india, "intermediate_india_answer") as mock_mid,
            patch.object(wiki_india, "long_term_india_answer") as mock_long,
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            answer, consulted = self._run(
                wiki_india.query_india("Where to park money in liquid fund for 6 months?")
            )

        mock_short.assert_awaited_once()
        mock_mid.assert_not_awaited()
        mock_long.assert_not_awaited()
        assert answer == "FD answer"

    def test_intermediate_horizon_routes_to_intermediate_flow(self, tmp_path):
        from core import wiki_india

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "short_term_india_answer") as mock_short,
            patch.object(
                wiki_india,
                "intermediate_india_answer",
                return_value=("SIP answer", ["basics/finance_basics_india.md"]),
            ) as mock_mid,
            patch.object(wiki_india, "long_term_india_answer") as mock_long,
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            answer, consulted = self._run(
                wiki_india.query_india("Best ELSS fund to start a SIP for tax saving under 80c?")
            )

        mock_mid.assert_awaited_once()
        mock_short.assert_not_awaited()
        mock_long.assert_not_awaited()
        assert answer == "SIP answer"

    def test_long_horizon_routes_to_long_term_flow(self, tmp_path):
        from core import wiki_india

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "short_term_india_answer") as mock_short,
            patch.object(wiki_india, "intermediate_india_answer") as mock_mid,
            patch.object(
                wiki_india,
                "long_term_india_answer",
                return_value=("NPS/PPF answer", ["basics/finance_basics_india.md"]),
            ) as mock_long,
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            answer, consulted = self._run(
                wiki_india.query_india("How to invest in NPS for retirement over 20 years?")
            )

        mock_long.assert_awaited_once()
        mock_short.assert_not_awaited()
        mock_mid.assert_not_awaited()
        assert answer == "NPS/PPF answer"

    def test_unknown_horizon_uses_wiki_retrieval_pipeline(self, tmp_path):
        """Unknown horizon falls through to the full LLM wiki pipeline."""
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\nmarket: india\n---\n# Basics\nSIP."
        )
        (tmp_path / "index.md").write_text("# Index\n- basics/finance_basics_india.md\n")

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "short_term_india_answer") as mock_short,
            patch.object(wiki_india, "intermediate_india_answer") as mock_mid,
            patch.object(wiki_india, "long_term_india_answer") as mock_long,
            patch.object(wiki_india, "call_gemini") as mock_gemini,
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            mock_gemini.side_effect = [
                "basics/finance_basics_india.md",
                "Gold is a store of value.",
            ]
            answer, _ = asyncio.run(wiki_india.query_india("Is gold a good investment?"))

        mock_short.assert_not_awaited()
        mock_mid.assert_not_awaited()
        mock_long.assert_not_awaited()
        # call_gemini must have been called (routing + answer)
        assert mock_gemini.call_count >= 1
        assert len(answer) > 0


# ── short_term_india_answer smoke test ────────────────────────────────────────


class TestShortTermIndiaAnswer:
    def test_returns_answer_and_consulted(self, tmp_path):
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics\nFD rates are linked to repo rate."
        )

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(wiki_india, "call_gemini", return_value="Park in FD or liquid fund."),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            answer, consulted = asyncio.run(
                wiki_india.short_term_india_answer("Where to park ₹50,000 for 6 months?")
            )

        assert len(answer) > 0
        assert isinstance(consulted, list)
        assert "basics/finance_basics_india.md" in consulted

    def test_sebi_disclaimer_in_prompt(self, tmp_path):
        """The SEBI disclaimer constant must be non-empty."""
        from core.wiki_india import _SEBI_DISCLAIMER

        assert "SEBI" in _SEBI_DISCLAIMER
        assert len(_SEBI_DISCLAIMER) > 20


# ── intermediate_india_answer smoke test ──────────────────────────────────────


class TestIntermediateIndiaAnswer:
    def test_returns_answer_and_consulted(self, tmp_path):
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics\nSIP lets you invest small amounts."
        )

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(
                wiki_india,
                "call_gemini",
                return_value="Start a ₹2,000/month SIP in Nifty 50.",
            ),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            answer, consulted = asyncio.run(
                wiki_india.intermediate_india_answer("Which ELSS fund for 80c tax saving?")
            )

        assert len(answer) > 0
        assert isinstance(consulted, list)
        assert "basics/finance_basics_india.md" in consulted


# ── long_term_india_answer smoke test ─────────────────────────────────────────


class TestLongTermIndiaAnswer:
    def test_returns_answer_and_consulted(self, tmp_path):
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics\nNPS and PPF for retirement."
        )

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(
                wiki_india,
                "call_gemini",
                return_value="Open NPS Tier-I and PPF for long-term wealth.",
            ),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            answer, consulted = asyncio.run(
                wiki_india.long_term_india_answer("How do I build retirement corpus over 20 years?")
            )

        assert len(answer) > 0
        assert isinstance(consulted, list)
        assert "basics/finance_basics_india.md" in consulted


# ── beginner_answer_india ─────────────────────────────────────────────────────


class TestBeginnerAnswerIndia:
    def test_returns_answer_string(self, tmp_path):
        from core import wiki_india

        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\n---\n# Basics content here"
        )

        with (
            patch("core.wiki_india.settings") as mock_settings,
            patch.object(
                wiki_india, "call_gemini", return_value="Start with a SIP in a Nifty 50 fund."
            ),
            patch.object(wiki_india, "_iwrite"),
            patch.object(wiki_india, "_iappend_log"),
        ):
            mock_settings.INDIA_WIKI_DIR = str(tmp_path)
            answer, consulted = asyncio.run(
                wiki_india.beginner_answer_india("How do I start investing with ₹500?")
            )

        assert len(answer) > 0
        assert isinstance(consulted, list)
        assert "basics/finance_basics_india.md" in consulted
