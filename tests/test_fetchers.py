"""tests/test_fetchers.py — data-layer fetcher guard-rails.

We don't hit live networks here (CI would flake); instead we verify the
graceful-degradation paths: missing API keys return `None`, empty symbol
lists return empty results, etc. Those are the code paths that actually
prevent the ingest loop from stalling.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from core import fetchers


class TestFetcherGuardRails(unittest.TestCase):
    def test_fred_returns_none_when_no_key(self) -> None:
        with patch.object(fetchers.settings, "FRED_API_KEY", ""):
            result = asyncio.run(fetchers.fetch_macro_indicators())
        self.assertIsNone(result)

    def test_reddit_returns_empty_when_no_creds(self) -> None:
        with (
            patch.object(fetchers.settings, "REDDIT_CLIENT_ID", ""),
            patch.object(fetchers.settings, "REDDIT_CLIENT_SECRET", ""),
        ):
            result = asyncio.run(fetchers.fetch_reddit_sentiment(["AAPL"]))
        self.assertEqual(result, [])


class TestAlphaVantageClientGuards(unittest.TestCase):
    def test_no_key_returns_empty_list(self) -> None:
        from core import alpha_vantage_client as av

        with patch.object(av.settings, "ALPHA_VANTAGE_API_KEY", ""):
            result = asyncio.run(av.fetch_alpha_vantage_for_symbols(["AAPL"]))
        self.assertEqual(result, [])


class TestFinnhubClientGuards(unittest.TestCase):
    def test_no_key_returns_empty_list(self) -> None:
        from core import finnhub_client as fh

        with patch.object(fh.settings, "FINNHUB_API_KEY", ""):
            result = asyncio.run(fh.fetch_finnhub_for_symbols(["AAPL"]))
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
