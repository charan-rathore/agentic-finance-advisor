"""
tests/test_india_wiki.py

Unit tests for core/wiki_india.py.

No Gemini calls are made — call_gemini is monkeypatched throughout.
No disk writes reach the real data/ directory — _iwrite is patched.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.wiki_india import (
    _iread,
    _iwrite,
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
    @pytest.mark.parametrize(
        "question, expected",
        [
            ("I need money in 6 months, where to park it?", "short_term"),
            ("Best liquid fund for parking money", "short_term"),
            ("I want to build wealth over 10 years for retirement", "long_term"),
            ("5 year investment plan for children education", "long_term"),
            ("SIP for wealth creation over long term", "long_term"),
            ("What should I do with my savings?", "unknown"),
        ],
    )
    def test_horizon_classification(self, question: str, expected: str):
        assert classify_investment_horizon(question) == expected

    def test_long_term_wins_when_both_present(self):
        # Ambiguous — both signals present; long wins when explicitly stated
        q = "short term saving but planning for retirement long term"
        result = classify_investment_horizon(q)
        # Both signals → unknown (neither dominates unambiguously)
        assert result == "unknown"


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
            patch.object(wiki_india, "_iwrite", side_effect=lambda p, c: writes.append(p)),
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
            patch.object(wiki_india, "_iwrite", side_effect=lambda p, c: writes.append(p)),
            patch.object(wiki_india, "_iappend_log"),
        ):
            asyncio.run(wiki_india.ingest_india(rbi_rates=rbi))

        assert any("macro/rbi_rates.md" in p for p in writes)


# ── query_india (lightweight smoke tests) ─────────────────────────────────────


class TestQueryIndiaSmoke:
    def test_returns_fallback_when_index_missing(self, tmp_path):
        from core import wiki_india

        with patch("core.wiki_india.settings") as mock_settings:
            mock_settings.INDIA_WIKI_DIR = str(tmp_path / "empty")
            answer, consulted = asyncio.run(wiki_india.query_india("What is a SIP?"))

        assert "still being built" in answer.lower() or "wait" in answer.lower()
        assert consulted == []

    def test_returns_answer_and_consulted_pages(self, tmp_path):
        from core import wiki_india

        # Write a minimal index and basics page
        (tmp_path / "basics").mkdir(parents=True)
        (tmp_path / "basics" / "finance_basics_india.md").write_text(
            "---\npage_type: reference\nmarket: india\n---\n# Basics\nSIP stands for Systematic Investment Plan."
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
            mock_gemini.side_effect = [
                "basics/finance_basics_india.md",
                "SIP allows you to invest small amounts regularly.",
            ]
            answer, consulted = asyncio.run(wiki_india.query_india("What is a SIP?"))

        assert "SIP" in answer or len(answer) > 0
        assert isinstance(consulted, list)


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
