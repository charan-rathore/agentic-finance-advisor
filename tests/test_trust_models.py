"""tests/test_trust_models.py — Schema smoke test for the Trust Layer tables.

PR 1 of the Trust Layer roadmap. These tests only exercise the ORM schema —
they do NOT depend on ``core/trust.py`` (which lands in PR 2) so they can be
merged and kept green independently.

What we assert:
1. ``init_db`` creates both ``source_registry`` and ``knowledge_versions``
   alongside the pre-existing tables — i.e. the additive change did not
   regress anything.
2. Both tables accept a representative row with the column types described
   in ``new_idea.txt`` (Boolean flags, String/Text fields, auto-incrementing
   PKs, default timestamps).
3. ``SourceRegistry.url`` is ``unique=True`` — the upsert contract in PR 2
   relies on this, so we lock the constraint in now.
4. ``KnowledgeVersion.page_name`` is indexed (we query by page in the UI).
"""

from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from core.models import KnowledgeVersion, SourceRegistry, init_db


class TestTrustLayerSchema(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = init_db("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)

    def test_init_db_creates_both_tables(self) -> None:
        tables = set(inspect(self.engine).get_table_names())
        self.assertIn("source_registry", tables)
        self.assertIn("knowledge_versions", tables)
        for pre_existing in (
            "market_snapshots",
            "news_articles",
            "insights",
            "fetch_runs",
        ):
            self.assertIn(
                pre_existing,
                tables,
                f"Additive migration must not drop {pre_existing}",
            )

    def test_source_registry_accepts_row(self) -> None:
        with self.Session() as s:
            row = SourceRegistry(
                url="https://sec.gov/cgi-bin/browse-edgar?CIK=0000320193",
                domain="sec.gov",
                source_name="SEC EDGAR",
                source_type="sec_filing",
                is_trusted=True,
                is_reachable=True,
                http_status=200,
            )
            s.add(row)
            s.commit()

            fetched = s.query(SourceRegistry).one()
            self.assertEqual(fetched.domain, "sec.gov")
            self.assertTrue(fetched.is_trusted)
            self.assertTrue(fetched.is_reachable)
            self.assertEqual(fetched.fetch_count, 1)
            self.assertIsInstance(fetched.first_fetched_at, datetime)
            self.assertIsInstance(fetched.last_fetched_at, datetime)

    def test_source_registry_url_is_unique(self) -> None:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
        with self.Session() as s:
            s.add(SourceRegistry(url=url, domain="query1.finance.yahoo.com"))
            s.commit()

        with self.Session() as s:
            s.add(SourceRegistry(url=url, domain="query1.finance.yahoo.com"))
            with self.assertRaises(IntegrityError):
                s.commit()

    def test_knowledge_version_accepts_row(self) -> None:
        with self.Session() as s:
            row = KnowledgeVersion(
                page_name="stocks/AAPL.md",
                version=1,
                change_summary="Initial ingest from yfinance + Google News",
                source_urls='["https://news.google.com/rss/search?q=AAPL"]',
                source_types='["rss_news"]',
                word_count_before=0,
                word_count_after=412,
                triggered_by="ingest",
            )
            s.add(row)
            s.commit()

            fetched = s.query(KnowledgeVersion).one()
            self.assertEqual(fetched.page_name, "stocks/AAPL.md")
            self.assertEqual(fetched.version, 1)
            self.assertEqual(fetched.word_count_after, 412)
            self.assertEqual(fetched.triggered_by, "ingest")
            self.assertIsInstance(fetched.changed_at, datetime)

    def test_knowledge_version_allows_multiple_versions_per_page(self) -> None:
        """The (page_name, version) pair is logically unique but not enforced
        at the DB layer — PR 2's ``record_wiki_version`` computes the next
        version in Python. This test just locks in that the schema does NOT
        block monotonically increasing versions for the same page."""
        with self.Session() as s:
            for v in range(1, 4):
                s.add(
                    KnowledgeVersion(
                        page_name="overview.md",
                        version=v,
                        word_count_after=100 * v,
                        triggered_by="ingest",
                    )
                )
            s.commit()

            rows = (
                s.query(KnowledgeVersion)
                .filter_by(page_name="overview.md")
                .order_by(KnowledgeVersion.version.asc())
                .all()
            )
            self.assertEqual([r.version for r in rows], [1, 2, 3])

    def test_indexes_exist_for_hot_read_paths(self) -> None:
        insp = inspect(self.engine)

        sr_indexed_cols = {
            col for idx in insp.get_indexes("source_registry") for col in idx["column_names"]
        }
        # ``unique=True`` on ``url`` also creates a unique constraint — which
        # SQLAlchemy/SQLite exposes via either get_indexes or
        # get_unique_constraints depending on the dialect version.
        sr_unique_cols = {
            col
            for uc in insp.get_unique_constraints("source_registry")
            for col in uc["column_names"]
        }
        self.assertIn("domain", sr_indexed_cols)
        self.assertTrue(
            "url" in sr_indexed_cols or "url" in sr_unique_cols,
            "source_registry.url must be indexed (explicit index or UNIQUE constraint)",
        )

        kv_indexed_cols = {
            col for idx in insp.get_indexes("knowledge_versions") for col in idx["column_names"]
        }
        self.assertIn("page_name", kv_indexed_cols)
        self.assertIn("changed_at", kv_indexed_cols)


if __name__ == "__main__":
    unittest.main()
