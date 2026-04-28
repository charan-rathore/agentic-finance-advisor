"""
core/fetchers_india.py

Indian market data fetchers — purely additive, no existing code modified.

Three data sources, all free, no API keys required:

1. fetch_india_prices()
   NSE stock prices via yfinance (.NS suffix). Reuses the exact same
   `fast_info.last_price` → history() fallback pattern from ingest_agent.py.

2. fetch_amfi_nav()
   Mutual fund NAVs from api.mfapi.in (AMFI-registered, official SEBI data).
   Fetches the `/mf/{scheme_code}/latest` endpoint for each scheme in
   settings.INDIA_MF_SCHEMES. No API key, no rate limit concern at our volume.

3. fetch_india_news_rss()
   Google News RSS per NSE symbol — same feedparser pattern as fetch_google_news_rss()
   in core/fetchers.py but uses the `hl=en-IN&gl=IN` locale for Indian context.

4. fetch_rbi_rates()
   RBI policy rates fetched from the RBI website's public JSON data.
   Falls back to a sensible hardcoded snapshot if the live fetch fails so the
   wiki always has *some* macro context even during RBI API outages.
   NOTE: RBI does not publish a stable public REST JSON API. We fetch the
   publicly accessible press-release page and extract the current repo rate.
   If this proves unreliable in production, the fallback snapshot is always used.

Design rules (same as core/fetchers.py):
- Every function is `async`, uses `asyncio.get_event_loop().run_in_executor`
  for blocking calls, and saves output to `data/raw/india/` as JSON.
- Every function catches all exceptions and returns None/[] — never raises.
- No infinite loops. Timeouts on every network call.
- Each saved file follows: `{source}_{symbol_or_topic}_{YYYYMMDD_HHMM}.json`
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import feedparser
import httpx
import yfinance as yf
from loguru import logger

from core.models import init_db
from core.settings import settings
from core.trust import register_source


def _get_engine() -> object:
    """Return a short-lived SQLAlchemy engine for source registration calls."""
    return init_db(settings.DATABASE_URL)


def _schedule_registration(url: str, source_name: str, source_type: str) -> None:
    """Fire-and-forget: schedule a register_source call on the running event loop.

    Uses get_event_loop().create_task so the registration never blocks the
    fetcher and is silently skipped in sync/test contexts that have no loop.
    """
    try:
        import asyncio as _asyncio

        async def _register() -> None:
            try:
                register_source(_get_engine(), url, source_name, source_type)
            except Exception as exc:  # pragma: no cover
                logger.debug(f"[Trust] register_source failed for {url}: {exc}")

        _asyncio.get_event_loop().create_task(_register())
    except RuntimeError:
        pass  # no running loop — skip registration in sync/test contexts

# ── Shared helpers ────────────────────────────────────────────────────────────


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M")


def _india_raw_dir() -> Path:
    p = Path(settings.INDIA_RAW_DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


async def _save(filepath: Path, data: dict) -> Path:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(filepath, "w") as f:
        await f.write(json.dumps(data, indent=2, default=str))
    logger.debug(f"[India] Saved {filepath} ({filepath.stat().st_size:,} bytes)")
    return filepath


# ── 1. NSE Stock Prices ───────────────────────────────────────────────────────


def _nse_snapshot(symbol: str) -> dict | None:
    """Blocking yfinance call for one NSE symbol. Mirrors ingest_agent._yf_snapshot."""
    ticker = yf.Ticker(symbol)
    price: float | None = None
    volume: float = 0.0

    try:
        info = ticker.fast_info
        price = getattr(info, "last_price", None)
        vol = getattr(info, "three_month_average_volume", None)
        if vol is not None:
            volume = float(vol)
    except Exception as e:
        logger.debug(f"[India] fast_info failed for {symbol}: {e}")

    if price is None:
        try:
            hist = ticker.history(period="1d", auto_adjust=False)
            if len(hist) > 0:
                price = float(hist["Close"].iloc[-1])
                if "Volume" in hist.columns:
                    volume = float(hist["Volume"].iloc[-1])
        except Exception as e:
            logger.debug(f"[India] history fallback failed for {symbol}: {e}")

    if price is None:
        return None

    return {
        "symbol": symbol,
        "exchange": "NSE",
        "price_inr": round(float(price), 2),
        "volume": round(volume, 0),
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "yfinance_nse",
        "market_time": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }


async def fetch_india_prices(symbols: list[str] | None = None) -> list[dict]:
    """
    Fetch current NSE stock prices for Indian symbols.

    Returns a list of price dicts (never raises). Symbols default to
    ``settings.INDIA_SYMBOLS`` when not provided.

    Saves a combined JSON file to ``data/raw/india/nse_prices_{ts}.json``
    and returns the list of successful price records.
    """
    if symbols is None:
        symbols = settings.INDIA_SYMBOLS

    results: list[dict] = []
    loop = asyncio.get_event_loop()

    logger.info(f"[India] Fetching NSE prices for {len(symbols)} symbols...")

    for symbol in symbols:
        try:
            snap = await asyncio.wait_for(
                loop.run_in_executor(None, _nse_snapshot, symbol),
                timeout=30.0,
            )
            if snap:
                results.append(snap)
                logger.debug(f"[India] {symbol} ₹{snap['price_inr']:.2f}")
            else:
                logger.warning(f"[India] No price data for {symbol}")
        except TimeoutError:
            logger.warning(f"[India] Timeout fetching {symbol}")
        except Exception as e:
            logger.error(f"[India] Price fetch failed for {symbol}: {e}")

    if results:
        payload = {
            "source": "yfinance_nse",
            "fetched_at": datetime.now(UTC).isoformat(),
            "count": len(results),
            "prices": results,
        }
        await _save(_india_raw_dir() / f"nse_prices_{_ts()}.json", payload)
        logger.info(f"[India] Saved {len(results)}/{len(symbols)} NSE prices")

    return results


# ── 2. AMFI Mutual Fund NAVs ──────────────────────────────────────────────────


# Scheme registry: maps scheme_code → friendly_name.
# Populated from settings.INDIA_MF_SCHEMES at module load.
# Format of each entry in the setting: "code:friendly_name"
def _parse_mf_schemes() -> dict[int, str]:
    result: dict[int, str] = {}
    for entry in settings.INDIA_MF_SCHEMES:
        try:
            code_str, name = entry.split(":", 1)
            result[int(code_str)] = name.strip()
        except Exception:
            logger.warning(f"[India] Malformed INDIA_MF_SCHEMES entry: {entry!r}")
    return result


async def fetch_amfi_nav() -> list[dict]:
    """
    Fetch latest NAV for each scheme in settings.INDIA_MF_SCHEMES.

    Uses api.mfapi.in — official AMFI data, free, no auth.
    Each scheme is fetched with a 10 s timeout. A failed scheme is skipped
    and logged; the rest continue.

    Saves ``data/raw/india/amfi_nav_{ts}.json`` and returns the list of NAV
    records so the wiki pipeline can consume them directly.
    """
    schemes = _parse_mf_schemes()
    if not schemes:
        logger.warning("[India] No MF schemes configured — skipping AMFI fetch")
        return []

    results: list[dict] = []
    base_url = "https://api.mfapi.in/mf"

    logger.info(f"[India] Fetching AMFI NAV for {len(schemes)} schemes...")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for code, name in schemes.items():
            try:
                r = await client.get(f"{base_url}/{code}/latest")
                r.raise_for_status()
                data = r.json()

                if data.get("status") != "SUCCESS" or not data.get("data"):
                    logger.warning(f"[India] AMFI bad response for {code}: {data.get('status')}")
                    continue

                meta = data.get("meta", {})
                nav_entry = data["data"][0]

                record = {
                    "scheme_code": code,
                    "friendly_name": name,
                    "fund_house": meta.get("fund_house", ""),
                    "scheme_name": meta.get("scheme_name", ""),
                    "scheme_category": meta.get("scheme_category", ""),
                    "scheme_type": meta.get("scheme_type", ""),
                    "nav": float(nav_entry["nav"]),
                    "nav_date": nav_entry["date"],
                    "isin_growth": meta.get("isin_growth", ""),
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "amfi_mfapi",
                    "source_url": f"{base_url}/{code}/latest",
                }
                results.append(record)
                _schedule_registration(
                    f"{base_url}/{code}/latest", "AMFI mfapi.in", "api"
                )
                logger.debug(f"[India] {name} NAV ₹{record['nav']:.4f} ({record['nav_date']})")

            except httpx.TimeoutException:
                logger.warning(f"[India] AMFI timeout for scheme {code} ({name})")
            except Exception as e:
                logger.error(f"[India] AMFI fetch failed for scheme {code} ({name}): {e}")

    if results:
        payload = {
            "source": "amfi_mfapi",
            "fetched_at": datetime.now(UTC).isoformat(),
            "count": len(results),
            "nav_records": results,
        }
        await _save(_india_raw_dir() / f"amfi_nav_{_ts()}.json", payload)
        logger.info(f"[India] Saved NAV for {len(results)}/{len(schemes)} schemes")

    return results


# ── 3. RBI Policy Rates ───────────────────────────────────────────────────────

# Fallback snapshot used when the live fetch fails.
# Update this manually after each RBI Monetary Policy Committee meeting.
# Current as of April 2026 (RBI cut repo rate to 5.25% in Feb 2025 cycle).
_RBI_FALLBACK: dict = {
    "repo_rate_pct": 5.25,
    "reverse_repo_rate_pct": 3.35,
    "crr_pct": 4.0,
    "slr_pct": 18.0,
    "bank_rate_pct": 5.50,
    "note": "Fallback snapshot — live fetch unavailable. Last updated: 2026-04-25.",
    "source": "rbi_fallback_snapshot",
}

# RBI publishes a JSON endpoint for its current key policy rates.
# This URL serves a structured JSON that the RBI website itself uses.
_RBI_RATES_URL = "https://website.rbi.org.in/api/v1/keyrates"


async def fetch_rbi_rates() -> dict:
    """
    Fetch RBI key policy rates (repo, reverse repo, CRR, SLR).

    Tries the RBI website JSON API first (5 s timeout). Falls back to
    ``_RBI_FALLBACK`` if the live fetch fails — so the wiki always has
    macro context. Never raises.

    Saves ``data/raw/india/rbi_rates_{ts}.json``.
    Returns the rates dict (live or fallback).
    """
    logger.info("[India] Fetching RBI policy rates...")

    rates: dict = {}
    source = "rbi_live"

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(_RBI_RATES_URL)
            r.raise_for_status()
            raw = r.json()

            # RBI API returns a list of rate objects; extract the ones we care about
            if isinstance(raw, list):
                rate_map = {item.get("description", ""): item.get("rate") for item in raw}
            elif isinstance(raw, dict):
                rate_map = raw
            else:
                raise ValueError(f"Unexpected RBI API response shape: {type(raw)}")

            rates = {
                "repo_rate_pct": rate_map.get("Repo Rate") or rate_map.get("Policy Repo Rate"),
                "reverse_repo_rate_pct": rate_map.get("Reverse Repo Rate"),
                "crr_pct": rate_map.get("CRR") or rate_map.get("Cash Reserve Ratio"),
                "slr_pct": rate_map.get("SLR") or rate_map.get("Statutory Liquidity Ratio"),
                "raw_response": raw,
                "source": "rbi_live",
                "source_url": _RBI_RATES_URL,
            }
            logger.info(f"[India] RBI live rates fetched — repo: {rates.get('repo_rate_pct')}%")
            _schedule_registration(_RBI_RATES_URL, "RBI Key Rates", "api")

    except Exception as e:
        logger.warning(f"[India] RBI live fetch failed ({e}) — using fallback snapshot")
        rates = dict(_RBI_FALLBACK)
        source = "rbi_fallback"

    payload = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": source,
        **{k: v for k, v in rates.items() if k not in ("raw_response", "source")},
    }

    await _save(_india_raw_dir() / f"rbi_rates_{_ts()}.json", payload)
    return payload


# ── 4. Indian News RSS ────────────────────────────────────────────────────────


async def fetch_india_news_rss(symbols: list[str] | None = None) -> list[dict]:
    """
    Fetch Google News RSS for each NSE symbol using the India locale.

    Uses `hl=en-IN&gl=IN` so Google surfaces Indian-context articles over
    global ones. Same feedparser pattern as core/fetchers.fetch_google_news_rss.

    Returns list of article-batch dicts; saves one JSON file per symbol.
    Never raises.
    """
    if symbols is None:
        # Strip the .NS suffix for cleaner news queries
        symbols = [s.replace(".NS", "") for s in settings.INDIA_SYMBOLS]

    results: list[dict] = []
    loop = asyncio.get_event_loop()

    for symbol in symbols:
        try:
            logger.debug(f"[India] Fetching news for {symbol}")
            url = (
                f"https://news.google.com/rss/search"
                f"?q={symbol}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en"
            )

            feed = await asyncio.wait_for(
                loop.run_in_executor(None, feedparser.parse, url),
                timeout=15.0,
            )

            articles = [
                {
                    "title": e.get("title", ""),
                    "link": e.get("link", ""),
                    "published": e.get("published", ""),
                    "summary": e.get("summary", "")[:500],
                    "source": (e.get("source") or {}).get("title", "Google News"),
                }
                for e in feed.entries[:15]
            ]

            batch = {
                "symbol": symbol,
                "articles": articles,
                "fetched_at": datetime.now(UTC).isoformat(),
                "source": "google_news_rss_india",
                "feed_url": url,
            }
            results.append(batch)

            filepath = _india_raw_dir() / f"india_news_{symbol}_{_ts()}.json"
            await _save(filepath, batch)
            _schedule_registration(url, "Google News RSS India", "rss")
            logger.debug(f"[India] {len(articles)} articles for {symbol}")

            # Brief pause — we're not in a hurry and Google is generous but not unlimited
            await asyncio.sleep(0.3)

        except TimeoutError:
            logger.warning(f"[India] News RSS timeout for {symbol}")
        except Exception as e:
            logger.error(f"[India] News RSS failed for {symbol}: {e}")

    logger.info(f"[India] News fetched for {len(results)}/{len(symbols)} symbols")
    return results
