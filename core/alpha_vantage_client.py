"""
core/alpha_vantage_client.py

Async Alpha Vantage client (free tier: 25 requests/day, 5 req/min).

We pull three endpoints worth of data:
- `GLOBAL_QUOTE`   — latest intraday quote (acts as a yfinance fallback)
- `OVERVIEW`       — company fundamentals: market cap, PE, PEG, profit margin, dividends
- `INCOME_STATEMENT` — last 4 annual + 4 quarterly reports (revenue/net income)

Why this API in addition to yfinance/SEC?
  yfinance is unofficial and breaks whenever Yahoo changes its HTML; SEC gives
  every XBRL tag but needs heavy parsing. Alpha Vantage gives one consistent
  JSON shape for fundamentals, which is ideal for feeding a wiki prompt.

Rate-limit strategy: 5 req/min hard cap. We fan out symbols sequentially with a
13-second gap (60/5 ≈ 12, plus jitter). Caller should batch to ≤ 5 symbols.

Raw payloads are saved to `<RAW_DATA_DIR>/alpha_vantage/{endpoint}_{symbol}_{ts}.json`
so `core/wiki_ingest.py` can pick them up and convert to wiki pages.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
import httpx
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from core.settings import settings


_BASE = "https://www.alphavantage.co/query"
_MIN_INTERVAL_SECONDS = 13.0


class AlphaVantageClient:
    """Minimal async wrapper around the Alpha Vantage REST API."""

    def __init__(self) -> None:
        self.api_key = settings.ALPHA_VANTAGE_API_KEY
        self.raw_dir = Path(settings.RAW_DATA_DIR) / "alpha_vantage"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            gap = now - self._last_request
            if gap < _MIN_INTERVAL_SECONDS:
                await asyncio.sleep(_MIN_INTERVAL_SECONDS - gap)
            self._last_request = asyncio.get_event_loop().time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def _get(self, params: dict[str, str]) -> dict[str, Any] | None:
        if not self.api_key:
            logger.warning("[AlphaVantage] No API key set, skipping")
            return None
        await self._throttle()
        params = {**params, "apikey": self.api_key}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        # Free tier rate-limit is returned in the body, not the HTTP status.
        note = data.get("Note") or data.get("Information")
        if note and ("limit" in note.lower() or "premium" in note.lower()):
            logger.warning(f"[AlphaVantage] Rate-limit note: {note}")
            return None
        return data

    async def _save(self, name: str, data: dict) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.raw_dir / f"{name}_{ts}.json"
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, indent=2, default=str))
        logger.debug(f"[AlphaVantage] Saved {path}")
        return path

    async def global_quote(self, symbol: str) -> Path | None:
        data = await self._get({"function": "GLOBAL_QUOTE", "symbol": symbol})
        if not data or not data.get("Global Quote"):
            return None
        payload = {
            "symbol": symbol,
            "source": "alpha_vantage",
            "endpoint": "GLOBAL_QUOTE",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "quote": data["Global Quote"],
        }
        return await self._save(f"alphavantage_quote_{symbol}", payload)

    async def overview(self, symbol: str) -> Path | None:
        data = await self._get({"function": "OVERVIEW", "symbol": symbol})
        if not data or "Symbol" not in data:
            return None
        payload = {
            "symbol": symbol,
            "source": "alpha_vantage",
            "endpoint": "OVERVIEW",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "overview": data,
        }
        return await self._save(f"alphavantage_overview_{symbol}", payload)

    async def income_statement(self, symbol: str) -> Path | None:
        data = await self._get({"function": "INCOME_STATEMENT", "symbol": symbol})
        if not data or "symbol" not in data:
            return None
        payload = {
            "symbol": symbol,
            "source": "alpha_vantage",
            "endpoint": "INCOME_STATEMENT",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "annual_reports": data.get("annualReports", [])[:4],
            "quarterly_reports": data.get("quarterlyReports", [])[:4],
        }
        return await self._save(f"alphavantage_income_{symbol}", payload)


alpha_vantage_client = AlphaVantageClient()


async def fetch_alpha_vantage_for_symbols(
    symbols: list[str], max_symbols: int = 3
) -> list[Path]:
    """
    Pull quote + overview + income statement for up to `max_symbols` tickers.

    Free tier is 25 requests/day total — each symbol costs 3 calls, so default
    cap is 3 symbols / run (9 calls). Caller decides cadence in ingest_agent.
    """
    if not settings.ALPHA_VANTAGE_API_KEY:
        logger.warning("[AlphaVantage] No API key; skipping")
        return []

    results: list[Path] = []
    for symbol in symbols[:max_symbols]:
        logger.info(f"[AlphaVantage] Fetching bundle for {symbol}")
        for coro in (
            alpha_vantage_client.global_quote(symbol),
            alpha_vantage_client.overview(symbol),
            alpha_vantage_client.income_statement(symbol),
        ):
            try:
                path = await coro
                if path:
                    results.append(path)
            except Exception as e:
                logger.error(f"[AlphaVantage] {symbol} call failed: {e}")
    logger.info(f"[AlphaVantage] Saved {len(results)} payloads")
    return results
