"""tests/test_confidence.py — Unit tests for _compute_confidence and _any_stale.

PR 3 of the Trust Layer roadmap. All tests are fully offline — no Gemini, no
disk I/O, no SQLite. Page content is injected via the ``page_contents`` dict
that both helpers accept to avoid redundant disk reads.

Rubric under test:
    start:                          1.00
    stale penalty:                 -0.15 per page with ``stale: true``
    source-diversity penalty:      -0.20 if fewer than 2 distinct data_sources
    recency penalty:               -0.10 if NO page has last_updated within 24 h
    floor:                          0.30

We also lock in the backward-compat guarantee that both helpers accept an
empty / None ``page_contents`` and fall back gracefully (they'll just read
nothing when the wiki hasn't been built yet, rather than raising).
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import yaml

from core.wiki import _any_stale, _compute_confidence

# ── Helpers to build fake wiki page content ───────────────────────────────────


def _make_page(
    *,
    stale: bool = False,
    data_sources: list[str] | None = None,
    last_updated: datetime | None = None,
) -> str:
    """Return a minimal markdown page string with YAML frontmatter."""
    fm: dict = {
        "page_type": "stock_entity",
        "stale": stale,
        "data_sources": data_sources or ["yfinance", "rss_news"],
        "last_updated": (last_updated or datetime.now(UTC)).isoformat(),
        "ttl_hours": 24,
    }
    return "---\n" + yaml.dump(fm, default_flow_style=False) + "---\n\n# Page body\n"


def _fresh(**kwargs) -> str:
    """Page whose last_updated is 1 hour ago — well within the 24 h window."""
    return _make_page(last_updated=datetime.now(UTC) - timedelta(hours=1), **kwargs)


def _old(**kwargs) -> str:
    """Page whose last_updated is 48 hours ago — definitely stale by wall-clock."""
    return _make_page(last_updated=datetime.now(UTC) - timedelta(hours=48), **kwargs)


# ── _compute_confidence ───────────────────────────────────────────────────────


class TestComputeConfidence(unittest.TestCase):
    # ── Base cases ────────────────────────────────────────────────────────────

    def test_no_pages_returns_0_80(self) -> None:
        # No pages → only the diversity penalty fires (no source types seen → -0.20).
        # The recency penalty does NOT fire when consulted_pages is empty because
        # ``any_page_recent`` stays False but there are also no pages to be "not recent"
        # — the check ``if consulted_pages and not any_page_recent`` guards this.
        score = _compute_confidence([], page_contents={})
        self.assertAlmostEqual(score, 0.80)

    def test_perfect_conditions_returns_1(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(data_sources=["yfinance", "rss_news"]),
            "stocks/MSFT.md": _fresh(data_sources=["sec_filing", "macro"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertEqual(score, 1.00)

    # ── Stale penalty ─────────────────────────────────────────────────────────

    def test_one_stale_page_deducts_0_15(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(stale=True, data_sources=["yfinance", "rss_news"]),
            "stocks/MSFT.md": _fresh(data_sources=["sec_filing", "rss_news"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertAlmostEqual(score, 0.85)

    def test_two_stale_pages_deduct_0_30(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(stale=True, data_sources=["yfinance", "rss_news"]),
            "stocks/MSFT.md": _fresh(stale=True, data_sources=["sec_filing", "rss_news"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertAlmostEqual(score, 0.70)

    def test_stale_penalty_is_per_page_not_per_flag(self) -> None:
        # Three stale pages: 1.0 - 3*0.15 = 0.55
        pages = {
            f"stocks/S{i}.md": _fresh(stale=True, data_sources=["yfinance", "rss_news"])
            for i in range(3)
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertAlmostEqual(score, 0.55)

    # ── Source-diversity penalty ───────────────────────────────────────────────

    def test_single_source_type_deducts_0_20(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(data_sources=["rss_news"]),
            "stocks/MSFT.md": _fresh(data_sources=["rss_news"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        # No stale, one source type, pages are recent → 1.0 - 0.20 = 0.80
        self.assertAlmostEqual(score, 0.80)

    def test_two_source_types_no_diversity_penalty(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(data_sources=["yfinance"]),
            "stocks/MSFT.md": _fresh(data_sources=["rss_news"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertEqual(score, 1.00)

    def test_all_sources_on_one_page_still_passes(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(data_sources=["yfinance", "rss_news", "sec_filing"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertEqual(score, 1.00)

    # ── Recency penalty ───────────────────────────────────────────────────────

    def test_all_pages_old_deducts_0_10(self) -> None:
        pages = {
            "stocks/AAPL.md": _old(data_sources=["yfinance", "rss_news"]),
            "stocks/MSFT.md": _old(data_sources=["sec_filing", "macro"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        # Not stale flag, 2+ source types, but all > 24 h old → 1.0 - 0.10 = 0.90
        self.assertAlmostEqual(score, 0.90)

    def test_mixed_freshness_no_recency_penalty(self) -> None:
        pages = {
            "stocks/AAPL.md": _old(data_sources=["yfinance"]),
            "stocks/MSFT.md": _fresh(data_sources=["rss_news"]),
        }
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        # One fresh page → recency penalty does NOT apply → 1.0 (2 source types)
        self.assertEqual(score, 1.00)

    # ── Floor ─────────────────────────────────────────────────────────────────

    def test_floor_is_0_30(self) -> None:
        # Max possible penalty: stale×5 (0.75) + no diversity (0.20) + not recent (0.10) = 1.05
        pages = {f"s{i}.md": _old(stale=True, data_sources=["rss_news"]) for i in range(5)}
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertEqual(score, 0.30)

    # ── Combined penalties ────────────────────────────────────────────────────

    def test_stale_plus_single_source_type(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(stale=True, data_sources=["rss_news"]),
        }
        # stale: -0.15, single source: -0.20 → 0.65
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertAlmostEqual(score, 0.65)

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_page_with_no_frontmatter_ignored_gracefully(self) -> None:
        pages = {
            "stocks/AAPL.md": "# No frontmatter at all\n\nJust body text.",
            "stocks/MSFT.md": _fresh(data_sources=["yfinance", "rss_news"]),
        }
        # AAPL has no frontmatter → no stale flag, no source types, no timestamp
        # MSFT has 2 source types + fresh → passes diversity + recency
        # Result: no stale penalty, diversity met by MSFT, MSFT is recent
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertEqual(score, 1.00)

    def test_empty_page_content_ignored_gracefully(self) -> None:
        pages = {"overview.md": ""}
        score = _compute_confidence(["overview.md"], page_contents=pages)
        # Empty content → no source types → diversity penalty + recency penalty
        self.assertAlmostEqual(score, 0.70)

    def test_missing_page_ignored_gracefully(self) -> None:
        # Page listed in consulted but absent from page_contents and not on disk.
        # Should not raise — just skip the missing page.
        score = _compute_confidence(["stocks/DOES_NOT_EXIST.md"], page_contents={})
        self.assertEqual(score, 0.70)

    def test_returns_two_decimal_places(self) -> None:
        pages = {"stocks/AAPL.md": _fresh(data_sources=["yfinance", "rss_news"])}
        score = _compute_confidence(list(pages.keys()), page_contents=pages)
        self.assertIsInstance(score, float)
        self.assertEqual(score, round(score, 2))


# ── _any_stale ────────────────────────────────────────────────────────────────


class TestAnyStale(unittest.TestCase):
    def test_no_stale_pages_returns_no(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(),
            "stocks/MSFT.md": _fresh(),
        }
        self.assertEqual(_any_stale(list(pages.keys()), page_contents=pages), "no")

    def test_one_stale_page_returns_yes(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(),
            "stocks/MSFT.md": _fresh(stale=True),
        }
        self.assertEqual(_any_stale(list(pages.keys()), page_contents=pages), "yes")

    def test_all_stale_returns_yes(self) -> None:
        pages = {
            "stocks/AAPL.md": _fresh(stale=True),
            "stocks/MSFT.md": _fresh(stale=True),
        }
        self.assertEqual(_any_stale(list(pages.keys()), page_contents=pages), "yes")

    def test_no_frontmatter_treated_as_not_stale(self) -> None:
        pages = {"overview.md": "# No YAML here"}
        self.assertEqual(_any_stale(["overview.md"], page_contents=pages), "no")

    def test_empty_consulted_returns_no(self) -> None:
        self.assertEqual(_any_stale([], page_contents={}), "no")

    def test_missing_page_does_not_raise(self) -> None:
        result = _any_stale(["stocks/GHOST.md"], page_contents={})
        self.assertEqual(result, "no")


if __name__ == "__main__":
    unittest.main()
