"""
tests/test_india_fetchers.py

Unit tests for core/fetchers_india.py.

All network calls are intercepted with httpx.MockTransport or monkeypatched
executor functions — this suite never touches the live internet.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.fetchers_india import (
    _RBI_FALLBACK,
    _nse_snapshot,
    _parse_mf_schemes,
    fetch_amfi_nav,
    fetch_india_news_rss,
    fetch_india_prices,
    fetch_rbi_rates,
)
from core.settings import settings

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mfapi_response(scheme_code: int, nav: str = "100.0") -> bytes:
    """Build a minimal mfapi.in /latest response payload."""
    body = {
        "status": "SUCCESS",
        "meta": {
            "fund_house": "Test AMC",
            "scheme_type": "Open Ended Schemes",
            "scheme_category": "Equity Scheme - Large Cap Fund",
            "scheme_code": scheme_code,
            "scheme_name": f"Test Fund {scheme_code} - Direct - Growth",
            "isin_growth": "INF000TEST001",
        },
        "data": [{"date": "25-04-2026", "nav": nav}],
    }
    return json.dumps(body).encode()


# ── _parse_mf_schemes ─────────────────────────────────────────────────────────


class TestParseMfSchemes:
    def test_returns_dict_of_int_keys(self):
        result = _parse_mf_schemes()
        assert isinstance(result, dict)
        for k in result:
            assert isinstance(k, int)

    def test_uses_settings_values(self):
        # The default settings have at least one scheme
        result = _parse_mf_schemes()
        assert len(result) >= 1

    def test_malformed_entry_skipped(self):
        """A malformed entry (no colon) should be silently skipped."""
        with patch.object(settings, "INDIA_MF_SCHEMES", ["BADENTRY", "135781:Mirae"]):
            result = _parse_mf_schemes()
        assert 135781 in result
        # BADENTRY should not appear
        assert all(isinstance(k, int) for k in result)


# ── _nse_snapshot ─────────────────────────────────────────────────────────────


class TestNseSnapshot:
    def test_returns_dict_with_price(self):
        mock_info = MagicMock()
        mock_info.last_price = 1327.80
        mock_info.three_month_average_volume = 5_000_000.0

        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        with patch("core.fetchers_india.yf.Ticker", return_value=mock_ticker):
            result = _nse_snapshot("RELIANCE.NS")

        assert result is not None
        assert result["symbol"] == "RELIANCE.NS"
        assert result["price_inr"] == pytest.approx(1327.80)
        assert result["exchange"] == "NSE"
        assert result["source"] == "yfinance_nse"

    def test_falls_back_to_history_when_fast_info_fails(self):
        import pandas as pd

        mock_info = MagicMock()
        mock_info.last_price = None  # fast_info returns None

        hist_df = pd.DataFrame(
            {"Close": [2396.90], "Volume": [1_000_000]},
            index=pd.to_datetime(["2026-04-25"]),
        )

        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info
        mock_ticker.history.return_value = hist_df

        with patch("core.fetchers_india.yf.Ticker", return_value=mock_ticker):
            result = _nse_snapshot("TCS.NS")

        assert result is not None
        assert result["price_inr"] == pytest.approx(2396.90)

    def test_returns_none_when_all_fetches_fail(self):
        mock_info = MagicMock()
        mock_info.last_price = None
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info
        mock_ticker.history.side_effect = Exception("network error")

        with patch("core.fetchers_india.yf.Ticker", return_value=mock_ticker):
            result = _nse_snapshot("BADTICKER.NS")

        assert result is None


# ── fetch_india_prices ────────────────────────────────────────────────────────


class TestFetchIndiaPrices:
    def test_returns_list_of_price_dicts(self):
        mock_snap = {
            "symbol": "RELIANCE.NS",
            "exchange": "NSE",
            "price_inr": 1327.80,
            "volume": 5_000_000.0,
            "timestamp": "2026-04-25T10:00:00+00:00",
            "source": "yfinance_nse",
            "market_time": "2026-04-25 10:00 UTC",
        }
        with (
            patch("core.fetchers_india._nse_snapshot", return_value=mock_snap),
            patch("core.fetchers_india._save", return_value=None),
        ):
            results = asyncio.run(fetch_india_prices(["RELIANCE.NS"]))

        assert len(results) == 1
        assert results[0]["price_inr"] == pytest.approx(1327.80)

    def test_empty_list_when_all_fail(self):
        with (
            patch("core.fetchers_india._nse_snapshot", return_value=None),
        ):
            results = asyncio.run(fetch_india_prices(["BADTICKER.NS"]))

        assert results == []

    def test_uses_settings_symbols_by_default(self):
        """When symbols=None it should use settings.INDIA_SYMBOLS."""
        call_log: list[str] = []

        def mock_snap(symbol: str) -> dict:
            call_log.append(symbol)
            return {
                "symbol": symbol,
                "exchange": "NSE",
                "price_inr": 100.0,
                "volume": 1.0,
                "timestamp": "2026-04-25T10:00:00+00:00",
                "source": "yfinance_nse",
                "market_time": "2026-04-25 10:00 UTC",
            }

        with (
            patch("core.fetchers_india._nse_snapshot", side_effect=mock_snap),
            patch("core.fetchers_india._save", return_value=None),
        ):
            results = asyncio.run(fetch_india_prices())

        assert set(call_log) == set(settings.INDIA_SYMBOLS)
        assert len(results) == len(settings.INDIA_SYMBOLS)


# ── fetch_amfi_nav ────────────────────────────────────────────────────────────


def _make_transport(responses: dict[str, bytes]) -> httpx.MockTransport:
    """Build a MockTransport that maps URL → response bytes."""

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        for pattern, body in responses.items():
            if pattern in url_str:
                return httpx.Response(200, content=body)
        return httpx.Response(404, content=b'{"status":"ERROR"}')

    return httpx.MockTransport(handler)


# Capture the real AsyncClient at module import time — before any test patches it.
_RealAsyncClient = httpx.AsyncClient


def _mock_async_client_cls(transport: httpx.MockTransport):
    """Return a mock AsyncClient class whose instances use MockTransport.

    Uses ``_RealAsyncClient`` (captured at module load) to avoid recursion
    when the patch replaces ``core.fetchers_india.httpx.AsyncClient``.
    """

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            kwargs.pop("transport", None)
            self._real = _RealAsyncClient(*args, transport=transport, **kwargs)

        async def __aenter__(self):
            await self._real.__aenter__()
            return self._real

        async def __aexit__(self, *exc_info):
            return await self._real.__aexit__(*exc_info)

    return _FakeClient


class TestFetchAmfiNav:
    def test_returns_nav_records(self):
        scheme_code = 135781
        transport = _make_transport({str(scheme_code): _mfapi_response(scheme_code, nav="54.46")})

        with (
            patch.object(settings, "INDIA_MF_SCHEMES", [f"{scheme_code}:Mirae_ELSS"]),
            patch("core.fetchers_india.httpx.AsyncClient", _mock_async_client_cls(transport)),
            patch("core.fetchers_india._save", return_value=None),
        ):
            results = asyncio.run(fetch_amfi_nav())

        assert len(results) == 1
        assert results[0]["scheme_code"] == scheme_code
        assert results[0]["nav"] == pytest.approx(54.46)
        assert results[0]["nav_date"] == "25-04-2026"
        assert results[0]["friendly_name"] == "Mirae_ELSS"

    def test_skips_failed_scheme_continues_rest(self):
        """A 404 on one scheme should not abort the remaining ones."""
        transport = _make_transport({"119800": _mfapi_response(119800, nav="4332.15")})

        schemes = ["999999:BadFund", "119800:SBI_Liquid"]
        with (
            patch.object(settings, "INDIA_MF_SCHEMES", schemes),
            patch("core.fetchers_india.httpx.AsyncClient", _mock_async_client_cls(transport)),
            patch("core.fetchers_india._save", return_value=None),
        ):
            results = asyncio.run(fetch_amfi_nav())

        assert len(results) == 1
        assert results[0]["scheme_code"] == 119800

    def test_empty_schemes_returns_empty(self):
        with patch.object(settings, "INDIA_MF_SCHEMES", []):
            results = asyncio.run(fetch_amfi_nav())
        assert results == []

    def test_nav_record_has_required_fields(self):
        code = 122639
        transport = _make_transport({str(code): _mfapi_response(code, nav="91.07")})
        with (
            patch.object(settings, "INDIA_MF_SCHEMES", [f"{code}:Parag_Parikh"]),
            patch("core.fetchers_india.httpx.AsyncClient", _mock_async_client_cls(transport)),
            patch("core.fetchers_india._save", return_value=None),
        ):
            results = asyncio.run(fetch_amfi_nav())

        rec = results[0]
        for field in ("scheme_code", "friendly_name", "nav", "nav_date", "fetched_at", "source"):
            assert field in rec, f"Missing field: {field}"


# ── fetch_rbi_rates ───────────────────────────────────────────────────────────


class TestFetchRbiRates:
    def test_uses_fallback_on_network_error(self):
        def bad_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        transport = httpx.MockTransport(bad_handler)
        with (
            patch("core.fetchers_india.httpx.AsyncClient", _mock_async_client_cls(transport)),
            patch("core.fetchers_india._save", return_value=None),
        ):
            result = asyncio.run(fetch_rbi_rates())

        # fallback source comes from _RBI_FALLBACK["source"] = "rbi_fallback_snapshot"
        # but fetch_rbi_rates() overwrites source in the payload with "rbi_fallback"
        assert result["source"] == "rbi_fallback"
        assert result["repo_rate_pct"] == _RBI_FALLBACK["repo_rate_pct"]

    def test_uses_fallback_on_non_200(self):
        transport = httpx.MockTransport(lambda r: httpx.Response(503, content=b""))
        with (
            patch("core.fetchers_india.httpx.AsyncClient", _mock_async_client_cls(transport)),
            patch("core.fetchers_india._save", return_value=None),
        ):
            result = asyncio.run(fetch_rbi_rates())

        assert result["source"] == "rbi_fallback"

    def test_fallback_has_all_required_fields(self):
        transport = httpx.MockTransport(lambda r: httpx.Response(500, content=b""))
        with (
            patch("core.fetchers_india.httpx.AsyncClient", _mock_async_client_cls(transport)),
            patch("core.fetchers_india._save", return_value=None),
        ):
            result = asyncio.run(fetch_rbi_rates())

        for field in ("repo_rate_pct", "fetched_at", "source"):
            assert field in result, f"Missing field: {field}"

    def test_live_response_parsed_correctly(self):
        live_body = json.dumps(
            [
                {"description": "Policy Repo Rate", "rate": 5.25},
                {"description": "Reverse Repo Rate", "rate": 3.35},
                {"description": "Cash Reserve Ratio", "rate": 4.0},
                {"description": "Statutory Liquidity Ratio", "rate": 18.0},
            ]
        ).encode()
        transport = httpx.MockTransport(lambda r: httpx.Response(200, content=live_body))
        with (
            patch("core.fetchers_india.httpx.AsyncClient", _mock_async_client_cls(transport)),
            patch("core.fetchers_india._save", return_value=None),
        ):
            result = asyncio.run(fetch_rbi_rates())

        assert result["source"] == "rbi_live"
        assert result["repo_rate_pct"] == pytest.approx(5.25)


# ── fetch_india_news_rss ──────────────────────────────────────────────────────


class TestFetchIndiaNewsRss:
    def _mock_feed(self, symbol: str) -> object:
        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(
                title=f"{symbol} gains 2% on strong results",
                link="https://economictimes.indiatimes.com/test",
                published="Thu, 25 Apr 2026 10:00:00 +0530",
                summary="Strong quarterly results drive the stock higher.",
                source=MagicMock(title="Economic Times"),
            )
            for _ in range(5)
        ]
        return mock_feed

    def test_returns_list_of_batches(self):
        symbols = ["RELIANCE", "TCS"]
        feed = self._mock_feed("RELIANCE")

        with (
            patch("core.fetchers_india.feedparser.parse", return_value=feed),
            patch("core.fetchers_india._save", return_value=None),
            patch("asyncio.sleep", return_value=None),
        ):
            results = asyncio.run(fetch_india_news_rss(symbols))

        assert len(results) == len(symbols)
        assert all("articles" in r for r in results)
        assert all(len(r["articles"]) <= 15 for r in results)

    def test_empty_symbols_returns_empty(self):
        results = asyncio.run(fetch_india_news_rss([]))
        assert results == []

    def test_individual_symbol_failure_does_not_abort_rest(self):
        call_count = 0

        def flaky_parse(url: str) -> object:
            nonlocal call_count
            call_count += 1
            if "RELIANCE" in url:
                raise Exception("feedparser error")
            feed = MagicMock()
            feed.entries = []
            return feed

        with (
            patch("core.fetchers_india.feedparser.parse", side_effect=flaky_parse),
            patch("core.fetchers_india._save", return_value=None),
            patch("asyncio.sleep", return_value=None),
        ):
            results = asyncio.run(fetch_india_news_rss(["RELIANCE", "TCS"]))

        # TCS should still be in results
        assert any(r["symbol"] == "TCS" for r in results)

    def test_uses_india_locale_in_url(self):
        urls_called: list[str] = []

        def capture_parse(url: str) -> object:
            urls_called.append(url)
            feed = MagicMock()
            feed.entries = []
            return feed

        with (
            patch("core.fetchers_india.feedparser.parse", side_effect=capture_parse),
            patch("core.fetchers_india._save", return_value=None),
            patch("asyncio.sleep", return_value=None),
        ):
            asyncio.run(fetch_india_news_rss(["TCS"]))

        assert any("gl=IN" in u for u in urls_called), "India locale not used in RSS URL"
