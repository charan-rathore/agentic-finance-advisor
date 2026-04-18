"""tests/test_sec_client.py — SEC EDGAR client invariants."""

from __future__ import annotations

import asyncio
import time
import unittest

from core.sec_client import sec_client


class TestSECClient(unittest.TestCase):
    def test_all_known_tickers_resolve_to_10_digit_cik(self) -> None:
        """Every CIK returned by the lookup must be 10 digits (SEC's format)."""
        known = [
            "NVDA",
            "AAPL",
            "GOOGL",
            "MSFT",
            "AMZN",
            "TSM",
            "META",
            "AVGO",
            "TSLA",
            "BRK.B",
            "JNJ",
            "JPM",
            "V",
            "UNH",
            "PG",
            "HD",
            "MA",
        ]

        async def _run() -> dict[str, str | None]:
            return {t: await sec_client.search_company_by_ticker(t) for t in known}

        mapping = asyncio.run(_run())
        for ticker, cik in mapping.items():
            self.assertIsNotNone(cik, msg=f"Missing CIK for {ticker}")
            self.assertEqual(len(cik), 10, msg=f"{ticker} CIK is not 10 digits: {cik}")
            self.assertTrue(cik.isdigit(), msg=f"{ticker} CIK is not numeric: {cik}")

    def test_known_tickers_resolve(self) -> None:
        async def _run() -> str | None:
            return await sec_client.search_company_by_ticker("AAPL")

        cik = asyncio.run(_run())
        self.assertEqual(cik, "0000320193")
        self.assertEqual(len(cik), 10)

    def test_unknown_ticker_returns_none(self) -> None:
        async def _run() -> str | None:
            return await sec_client.search_company_by_ticker("NOPE123")

        self.assertIsNone(asyncio.run(_run()))

    def test_rate_limiter_enforces_minimum_gap(self) -> None:
        """Two back-to-back `_rate_limit` calls must take at least _min_interval."""

        async def _run() -> float:
            t0 = time.monotonic()
            await sec_client._rate_limit()
            await sec_client._rate_limit()
            return time.monotonic() - t0

        elapsed = asyncio.run(_run())
        self.assertGreaterEqual(elapsed, sec_client._min_interval * 0.9)


if __name__ == "__main__":
    unittest.main()
