"""Unit tests for the non-Gemini wiki health snapshot helpers."""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def test_wiki_health_snapshot_classifies_pages(tmp_path, monkeypatch):
    """Fresh / stale / missing-frontmatter classification without any Gemini calls."""
    from core import wiki as wiki_module
    from core.settings import settings

    monkeypatch.setattr(settings, "WIKI_DIR", str(tmp_path))

    now = datetime.now(UTC)
    fresh_ts = (now - timedelta(hours=1)).isoformat()
    stale_ts = (now - timedelta(hours=48)).isoformat()

    _write(
        tmp_path / "stocks" / "FRESH.md",
        f"""\
        ---
        symbol: FRESH
        page_type: stock
        last_updated: {fresh_ts}
        ttl_hours: 6
        ---

        # FRESH
        Body text.
        """,
    )
    _write(
        tmp_path / "stocks" / "STALE.md",
        f"""\
        ---
        symbol: STALE
        page_type: stock
        last_updated: {stale_ts}
        ttl_hours: 6
        ---

        # STALE
        Body text.
        """,
    )
    _write(
        tmp_path / "overview.md",
        """\
        # Overview
        No frontmatter here at all.
        """,
    )
    # Lint reports and log.md must be excluded from the snapshot.
    _write(tmp_path / "insights" / "lint_2026-01-01_00-00.md", "# Lint report\n")
    _write(tmp_path / "log.md", "log\n")

    snap = wiki_module.wiki_health_snapshot()

    fresh_paths = {e["path"] for e in snap["fresh"]}
    stale_paths = {e["path"] for e in snap["stale"]}

    assert snap["total_pages"] == 3  # excludes lint_* and log.md
    assert fresh_paths == {"stocks/FRESH.md"}
    assert stale_paths == {"stocks/STALE.md"}
    assert snap["missing_frontmatter"] == ["overview.md"]
    assert snap["by_type"].get("stock") == 2

    # Stale entry exposes the overdue delta for UI sorting.
    stale_entry = next(e for e in snap["stale"] if e["path"] == "stocks/STALE.md")
    assert stale_entry["overdue_hours"] > 0
    assert stale_entry["age_hours"] > stale_entry["ttl_hours"]


def test_raw_data_snapshot_groups_files_by_source(tmp_path, monkeypatch):
    from core import wiki as wiki_module
    from core.settings import settings

    monkeypatch.setattr(settings, "RAW_DATA_DIR", str(tmp_path))

    (tmp_path / "sec").mkdir()
    (tmp_path / "sec" / "company_facts_0000320193_20260418_000000.json").write_text("{}")
    (tmp_path / "sec" / "company_facts_0000789019_20260418_000000.json").write_text("{}")

    (tmp_path / "googlenews_AAPL_20260418_0000.json").write_text("{}")
    (tmp_path / "macro_indicators_20260418_0000.json").write_text("{}")

    snap = wiki_module.raw_data_snapshot()
    sources = snap["sources"]

    assert sources["sec"]["file_count"] == 2
    assert sources["googlenews"]["file_count"] == 1
    assert sources["macro"]["file_count"] == 1
    assert sources["reddit"]["file_count"] == 0
    assert sources["sec"]["latest_iso"] is not None
