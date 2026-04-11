"""tests/test_ingest.py — basic tests for ingest agent functions."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from agents.ingest_agent import fetch_market_data
from core.models import init_db
from core.settings import settings


class TestFetchMarketData(unittest.TestCase):
    def test_bad_symbol_is_skipped(self) -> None:
        """If yfinance returns no price, the symbol should be skipped gracefully."""
        with patch("agents.ingest_agent.yf.Ticker") as mock_ticker:
            mock_info = MagicMock()
            mock_info.last_price = None
            mock_ticker.return_value.fast_info = mock_info
            engine = init_db("sqlite:///:memory:")
            result = asyncio.run(fetch_market_data(engine))
            self.assertEqual(result, [])


class TestSettings(unittest.TestCase):
    def test_database_url_is_sqlite(self) -> None:
        """DATABASE_URL must be SQLite — not Postgres or anything paid."""
        self.assertTrue(
            settings.DATABASE_URL.startswith("sqlite:///"),
            "DATABASE_URL must use SQLite (free, local). Never use Postgres here.",
        )

    def test_gemini_model_is_free_tier(self) -> None:
        """Gemini model must be the free flash model, not the paid pro model."""
        self.assertIn(
            "flash",
            settings.GEMINI_MODEL,
            "GEMINI_MODEL must be gemini-1.5-flash (free tier). "
            "gemini-pro requires billing and is not allowed.",
        )


if __name__ == "__main__":
    unittest.main()
