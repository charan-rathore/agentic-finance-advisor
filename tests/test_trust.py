"""tests/test_trust.py — Unit tests for the Trust Layer (PR 2).

Covers ``core/trust.py`` end-to-end without ever touching the network or the
on-disk wiki:

- :func:`extract_domain` — including the ``lstrip``-vs-``removeprefix`` bug
  fix (``wsj.com`` must NOT become ``sj.com``).
- :func:`is_trusted_domain` — exact match, www-prefix, sub-domain match, and
  rejection of look-alike hosts.
- :func:`validate_source` — happy path, HEAD-rejected → GET fallback, and
  network failure → ``is_reachable=False``. Network is mocked via
  :class:`httpx.MockTransport` (no respx dependency needed).
- :func:`register_source` — first insert, then upsert semantics
  (``fetch_count`` increments, ``first_fetched_at`` preserved,
  reachability/status updated).
- :func:`record_wiki_version` — monotonically increasing per-page versions,
  word-count tracking, JSON-encoded source lists.
- :func:`get_page_version_history` / :func:`get_all_sources` — UI read paths
  return plain dicts in the expected order.
"""

from __future__ import annotations

import asyncio
import unittest

import httpx
from sqlalchemy.orm import sessionmaker

from core.models import SourceRegistry, init_db
from core.trust import (
    TRUSTED_DOMAINS,
    extract_domain,
    get_all_sources,
    get_page_version_history,
    is_trusted_domain,
    record_wiki_version,
    register_source,
    validate_source,
)


def _run(coro):
    """Execute ``coro`` on a fresh event loop for sync unittest methods."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ── extract_domain ───────────────────────────────────────────────────────────


class TestExtractDomain(unittest.TestCase):
    def test_basic_https(self) -> None:
        self.assertEqual(extract_domain("https://sec.gov/foo/bar"), "sec.gov")

    def test_strips_only_www_prefix_not_arbitrary_chars(self) -> None:
        # The original spec used ``lstrip("www.")`` which is a *character set*
        # strip and would mangle these. Locking the fix in.
        self.assertEqual(extract_domain("https://wsj.com/article/123"), "wsj.com")
        self.assertEqual(extract_domain("https://www.wsj.com/article/123"), "wsj.com")
        self.assertEqual(extract_domain("https://www.example.com"), "example.com")
        # A leading "w" with no "www." should stay put.
        self.assertEqual(extract_domain("https://wikipedia.org/x"), "wikipedia.org")

    def test_uppercase_normalised(self) -> None:
        self.assertEqual(extract_domain("https://SEC.GOV/x"), "sec.gov")

    def test_unparseable_returns_empty(self) -> None:
        # urlparse is permissive — but a pure path with no scheme has empty
        # netloc, which is exactly what we want to fall back to.
        self.assertEqual(extract_domain("not a url at all"), "")
        self.assertEqual(extract_domain(""), "")


# ── is_trusted_domain ────────────────────────────────────────────────────────


class TestIsTrustedDomain(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(is_trusted_domain("https://sec.gov/cgi-bin/browse-edgar"))
        self.assertTrue(is_trusted_domain("https://news.google.com/rss/search?q=AAPL"))

    def test_www_variant_is_trusted(self) -> None:
        # www.X is normalised to X by extract_domain, so the whitelist hits.
        for url in (
            "https://www.wsj.com/markets",
            "https://www.cnn.com/business",
            "https://www.reddit.com/r/investing",
        ):
            self.assertTrue(is_trusted_domain(url), url)

    def test_subdomain_of_trusted_parent(self) -> None:
        # api.fred.stlouisfed.org is a child of fred.stlouisfed.org.
        self.assertTrue(is_trusted_domain("https://api.fred.stlouisfed.org/fred/series"))
        self.assertTrue(is_trusted_domain("https://data.sec.gov/submissions/x.json"))

    def test_lookalike_rejected(self) -> None:
        # "fakesec.gov" must NOT be treated as a child of "sec.gov".
        self.assertFalse(is_trusted_domain("https://fakesec.gov/x"))
        # "evil-cnn.com" must NOT be treated as a child of "cnn.com".
        self.assertFalse(is_trusted_domain("https://evil-cnn.com/x"))

    def test_completely_unknown_domain(self) -> None:
        self.assertFalse(is_trusted_domain("https://random-blog.example/post/1"))

    def test_empty_or_garbage(self) -> None:
        self.assertFalse(is_trusted_domain(""))
        self.assertFalse(is_trusted_domain("not-a-url"))

    def test_whitelist_is_non_trivial(self) -> None:
        # Sanity: the whitelist should have several entries — guards against
        # an accidental ``TRUSTED_DOMAINS = set()``.
        self.assertGreater(len(TRUSTED_DOMAINS), 10)


# ── validate_source (httpx.MockTransport — no live network) ──────────────────


class TestValidateSource(unittest.TestCase):
    def _transport(self, handler):
        return httpx.MockTransport(handler)

    def test_head_200_marks_reachable_and_trusted(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "HEAD")
            return httpx.Response(200)

        result = _run(validate_source("https://sec.gov/x", transport=self._transport(handler)))
        self.assertTrue(result["is_trusted"])
        self.assertTrue(result["is_reachable"])
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["domain"], "sec.gov")

    def test_head_405_falls_back_to_get(self) -> None:
        seen_methods: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_methods.append(request.method)
            if request.method == "HEAD":
                return httpx.Response(405)
            return httpx.Response(206)  # Partial Content for the Range request

        result = _run(
            validate_source(
                "https://news.google.com/rss/search?q=AAPL",
                transport=self._transport(handler),
            )
        )
        self.assertEqual(seen_methods, ["HEAD", "GET"])
        self.assertTrue(result["is_reachable"])
        self.assertEqual(result["http_status"], 206)

    def test_network_error_returns_unreachable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("DNS failure", request=request)

        result = _run(
            validate_source(
                "https://nonexistent.invalid/x",
                transport=self._transport(handler),
            )
        )
        self.assertFalse(result["is_reachable"])
        # http_status remains None when the request never completed.
        self.assertIsNone(result["http_status"])
        self.assertFalse(result["is_trusted"])  # nonexistent.invalid not in whitelist

    def test_500_marks_reachable_false_but_status_recorded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        result = _run(validate_source("https://sec.gov/broken", transport=self._transport(handler)))
        # 500 is recorded as a status but reachable=False (status >= 400).
        self.assertFalse(result["is_reachable"])
        self.assertEqual(result["http_status"], 500)


# ── register_source ──────────────────────────────────────────────────────────


class TestRegisterSource(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = init_db("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)

    def test_first_call_inserts_full_row(self) -> None:
        register_source(
            self.engine,
            url="https://api.stlouisfed.org/fred/series?id=DFF",
            source_name="FRED — Fed Funds Rate",
            source_type="macro",
            validation_result={
                "url": "https://api.stlouisfed.org/fred/series?id=DFF",
                "domain": "api.stlouisfed.org",
                "is_trusted": True,
                "is_reachable": True,
                "http_status": 200,
            },
        )

        with self.Session() as s:
            row = s.query(SourceRegistry).one()
            self.assertEqual(row.source_name, "FRED — Fed Funds Rate")
            self.assertEqual(row.source_type, "macro")
            self.assertTrue(row.is_trusted)
            self.assertEqual(row.fetch_count, 1)

    def test_second_call_increments_fetch_count(self) -> None:
        url = "https://finnhub.io/api/v1/quote?symbol=AAPL"
        for _ in range(3):
            register_source(
                self.engine,
                url=url,
                source_name="Finnhub",
                source_type="price",
            )

        with self.Session() as s:
            rows = s.query(SourceRegistry).filter_by(url=url).all()
            self.assertEqual(len(rows), 1, "URL is unique — must not insert duplicates")
            self.assertEqual(rows[0].fetch_count, 3)

    def test_upsert_preserves_first_fetched_at(self) -> None:
        url = "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=MSFT"
        register_source(self.engine, url=url, source_name="AV", source_type="price")
        with self.Session() as s:
            first_seen = s.query(SourceRegistry).filter_by(url=url).one().first_fetched_at

        register_source(self.engine, url=url, source_name="AV", source_type="price")
        with self.Session() as s:
            row = s.query(SourceRegistry).filter_by(url=url).one()
            self.assertEqual(row.first_fetched_at, first_seen)
            self.assertGreaterEqual(row.last_fetched_at, first_seen)

    def test_upsert_updates_reachability_to_latest_observation(self) -> None:
        url = "https://news.google.com/rss/search?q=AAPL"
        register_source(
            self.engine,
            url=url,
            source_name="Google News AAPL",
            source_type="rss_news",
            validation_result={
                "url": url,
                "domain": "news.google.com",
                "is_trusted": True,
                "is_reachable": True,
                "http_status": 200,
            },
        )
        # Source goes down between fetches — reachability must reflect latest.
        register_source(
            self.engine,
            url=url,
            source_name="Google News AAPL",
            source_type="rss_news",
            validation_result={
                "url": url,
                "domain": "news.google.com",
                "is_trusted": True,
                "is_reachable": False,
                "http_status": 503,
            },
        )

        with self.Session() as s:
            row = s.query(SourceRegistry).filter_by(url=url).one()
            self.assertFalse(row.is_reachable)
            self.assertEqual(row.http_status, 503)
            self.assertEqual(row.fetch_count, 2)

    def test_no_validation_result_assumes_trusted_and_reachable(self) -> None:
        """The 'reachability proven by successful fetch' shortcut PR 4 will use."""
        register_source(
            self.engine,
            url="https://sec.gov/cgi-bin/browse-edgar?CIK=0000320193",
            source_name="SEC EDGAR",
            source_type="sec_filing",
        )

        with self.Session() as s:
            row = s.query(SourceRegistry).one()
            self.assertTrue(row.is_trusted)  # sec.gov is in the whitelist
            self.assertTrue(row.is_reachable)
            self.assertEqual(row.http_status, 200)


# ── record_wiki_version + read helpers ───────────────────────────────────────


class TestKnowledgeVersioning(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = init_db("sqlite:///:memory:")

    def test_first_version_is_one(self) -> None:
        v = record_wiki_version(
            self.engine,
            page_name="stocks/AAPL.md",
            new_content="hello world from apple " * 50,
            old_content="",
            change_summary="initial create",
            source_urls=["https://sec.gov/x"],
            source_types=["sec_filing"],
        )
        self.assertEqual(v, 1)

    def test_versions_increment_per_page(self) -> None:
        for expected in (1, 2, 3):
            v = record_wiki_version(
                self.engine,
                page_name="overview.md",
                new_content="overview text " * (10 * expected),
                old_content="overview text " * (10 * (expected - 1)) if expected > 1 else "",
                change_summary=f"cycle {expected}",
                source_urls=["https://news.google.com/rss/x"],
                source_types=["rss_news"],
            )
            self.assertEqual(v, expected)

    def test_versions_are_per_page_independent(self) -> None:
        record_wiki_version(
            self.engine,
            "stocks/AAPL.md",
            "x" * 10,
            "",
            "init",
            ["https://sec.gov/x"],
            ["sec_filing"],
        )
        record_wiki_version(
            self.engine,
            "stocks/AAPL.md",
            "x" * 20,
            "x" * 10,
            "update",
            ["https://sec.gov/x"],
            ["sec_filing"],
        )
        v_msft = record_wiki_version(
            self.engine,
            "stocks/MSFT.md",
            "y" * 10,
            "",
            "init",
            ["https://sec.gov/y"],
            ["sec_filing"],
        )
        self.assertEqual(v_msft, 1, "MSFT versioning is independent of AAPL")

    def test_word_counts_recorded(self) -> None:
        record_wiki_version(
            self.engine,
            page_name="stocks/AAPL.md",
            new_content="one two three four five",  # 5 words
            old_content="one two",  # 2 words
            change_summary="grew the page",
            source_urls=[],
            source_types=[],
        )

        history = get_page_version_history(self.engine, "stocks/AAPL.md")
        self.assertEqual(history[0]["word_count_before"], 2)
        self.assertEqual(history[0]["word_count_after"], 5)

    def test_get_page_version_history_returns_newest_first(self) -> None:
        for i in range(1, 4):
            record_wiki_version(
                self.engine,
                page_name="stocks/AAPL.md",
                new_content="word " * (i * 10),
                old_content="word " * ((i - 1) * 10) if i > 1 else "",
                change_summary=f"v{i}",
                source_urls=[f"https://sec.gov/v{i}"],
                source_types=["sec_filing"],
            )

        history = get_page_version_history(self.engine, "stocks/AAPL.md")
        self.assertEqual([h["version"] for h in history], [3, 2, 1])
        # source_urls round-trips as a list, not a JSON string.
        self.assertIsInstance(history[0]["source_urls"], list)
        self.assertEqual(history[0]["source_urls"], ["https://sec.gov/v3"])

    def test_triggered_by_default_is_ingest(self) -> None:
        record_wiki_version(
            self.engine,
            "stocks/AAPL.md",
            "hello",
            "",
            "x",
            [],
            [],
        )
        history = get_page_version_history(self.engine, "stocks/AAPL.md")
        self.assertEqual(history[0]["triggered_by"], "ingest")

    def test_triggered_by_can_be_overridden(self) -> None:
        record_wiki_version(
            self.engine,
            "stocks/AAPL.md",
            "hello",
            "",
            "x",
            [],
            [],
            triggered_by="lint",
        )
        history = get_page_version_history(self.engine, "stocks/AAPL.md")
        self.assertEqual(history[0]["triggered_by"], "lint")


class TestGetAllSources(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = init_db("sqlite:///:memory:")

    def test_empty_db_returns_empty_list(self) -> None:
        self.assertEqual(get_all_sources(self.engine), [])

    def test_returns_dicts_sorted_by_last_fetched_desc(self) -> None:
        urls = [
            "https://sec.gov/a",
            "https://news.google.com/b",
            "https://finnhub.io/c",
        ]
        for u in urls:
            register_source(self.engine, url=u, source_name="x", source_type="t")

        sources = get_all_sources(self.engine)
        self.assertEqual(len(sources), 3)
        # Most-recent registration was the last URL — should appear first.
        self.assertEqual(sources[0]["url"], urls[-1])
        # Each entry is a plain dict with the documented keys.
        for key in (
            "url",
            "domain",
            "source_name",
            "source_type",
            "is_trusted",
            "is_reachable",
            "http_status",
            "first_fetched_at",
            "last_fetched_at",
            "fetch_count",
        ):
            self.assertIn(key, sources[0])


if __name__ == "__main__":
    unittest.main()
