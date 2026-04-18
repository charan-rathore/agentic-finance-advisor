"""
core/finnhub_client.py

Async Finnhub client (free tier: 60 req/min, unlimited req/day).

Why Finnhub in addition to yfinance/SEC/Alpha Vantage?
- Real-time quote endpoint that does not go stale like yfinance during market hours.
- Per-symbol company news feed with proper headlines + summaries (cleaner than
  scraping Google News RSS).
- Earnings calendar / recommendation trends endpoints that give us a forward-
  looking signal the wiki otherwise lacks.

Endpoints used:
- `/quote`            — current, previous close, day high/low
- `/company-news`     — articles from the last 7 days for a symbol
- `/stock/recommendation` — analyst rating history (strong-buy/buy/hold/sell/strong-sell)

Raw payloads land in `<RAW_DATA_DIR>/finnhub/` and are picked up by wiki_ingest.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiofiles
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.schemas import RawPayload
from core.settings import settings

_BASE = "https://finnhub.io/api/v1"
_MIN_INTERVAL_SECONDS = 1.2  # ≤ 50 req/min — comfortable under the 60 cap


class FinnhubClient:
    def __init__(self) -> None:
        self.api_key = settings.FINNHUB_API_KEY
        self.raw_dir = Path(settings.RAW_DATA_DIR) / "finnhub"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            gap = now - self._last
            if gap < _MIN_INTERVAL_SECONDS:
                await asyncio.sleep(_MIN_INTERVAL_SECONDS - gap)
            self._last = asyncio.get_event_loop().time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        if not self.api_key:
            logger.warning("[Finnhub] No API key, skipping")
            return None
        await self._throttle()
        params = {**params, "token": self.api_key}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_BASE}{path}", params=params)
            if resp.status_code == 429:
                logger.warning("[Finnhub] Rate-limited")
                return None
            resp.raise_for_status()
            return resp.json()

    async def _save(self, name: str, data: dict) -> Path:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = self.raw_dir / f"{name}_{ts}.json"
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, indent=2, default=str))
        logger.debug(f"[Finnhub] Saved {path}")
        return path

    async def quote(self, symbol: str) -> Path | None:
        data = await self._get("/quote", {"symbol": symbol})
        if not data or data.get("c") in (None, 0):
            return None
        envelope = RawPayload.build(
            source="finnhub",
            endpoint="quote",
            symbol=symbol,
            url=f"{_BASE}/quote",
            params={"symbol": symbol},
            payload={
                "quote": {
                    "current": data.get("c"),
                    "change": data.get("d"),
                    "percent_change": data.get("dp"),
                    "day_high": data.get("h"),
                    "day_low": data.get("l"),
                    "open": data.get("o"),
                    "previous_close": data.get("pc"),
                    "timestamp": data.get("t"),
                }
            },
        )
        return await self._save(f"finnhub_quote_{symbol}", envelope.to_json_dict())

    async def company_news(self, symbol: str, days_back: int = 7) -> Path | None:
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days_back)
        data = await self._get(
            "/company-news",
            {"symbol": symbol, "from": str(start), "to": str(today)},
        )
        if not data:
            return None
        articles = [
            {
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source", "finnhub"),
                "url": item.get("url", ""),
                "published_at": datetime.fromtimestamp(item.get("datetime", 0), tz=UTC).isoformat()
                if item.get("datetime")
                else None,
                "category": item.get("category", ""),
            }
            for item in data[:25]
        ]
        envelope = RawPayload.build(
            source="finnhub",
            endpoint="company-news",
            symbol=symbol,
            url=f"{_BASE}/company-news",
            params={"symbol": symbol, "from": str(start), "to": str(today)},
            payload={"window_days": days_back, "articles": articles},
        )
        return await self._save(f"finnhub_news_{symbol}", envelope.to_json_dict())

    async def recommendation_trends(self, symbol: str) -> Path | None:
        data = await self._get("/stock/recommendation", {"symbol": symbol})
        if not data:
            return None
        envelope = RawPayload.build(
            source="finnhub",
            endpoint="recommendation",
            symbol=symbol,
            url=f"{_BASE}/stock/recommendation",
            params={"symbol": symbol},
            payload={"trends": data[:6]},
        )
        return await self._save(f"finnhub_recommendation_{symbol}", envelope.to_json_dict())


finnhub_client = FinnhubClient()


async def fetch_finnhub_for_symbols(symbols: list[str]) -> list[Path]:
    """
    Pull quote + company news + recommendation trends for every tracked symbol.
    Quotes are cheap (1 req each); news + recommendations add 2 more. At 50
    req/min, this handles ~16 symbols/minute comfortably.
    """
    if not settings.FINNHUB_API_KEY:
        logger.warning("[Finnhub] No API key; skipping")
        return []

    results: list[Path] = []
    for symbol in symbols:
        try:
            for coro in (
                finnhub_client.quote(symbol),
                finnhub_client.company_news(symbol),
                finnhub_client.recommendation_trends(symbol),
            ):
                path = await coro
                if path:
                    results.append(path)
        except Exception as e:
            logger.error(f"[Finnhub] {symbol} failed: {e}")
    logger.info(f"[Finnhub] Saved {len(results)} payloads across {len(symbols)} symbols")
    return results
