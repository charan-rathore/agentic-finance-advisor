"""
scripts/run_data_fetch_once.py

One-shot data-fetch harness for local development.

Runs every data source the agent knows about **exactly once**, with a strict
per-source timeout so one wedged API can never stall the whole script. Prints
a table summary at the end.

Usage:
    python scripts/run_data_fetch_once.py              # run every source
    python scripts/run_data_fetch_once.py --only finnhub,fred   # subset
    python scripts/run_data_fetch_once.py --symbols AAPL,MSFT   # override tickers
    python scripts/run_data_fetch_once.py --timeout 20          # per-source cap

Anti-stall design:
    Every fetcher is wrapped in `asyncio.wait_for(..., timeout=N)`. If a source
    blocks (e.g. network proxy, rate-limit sleep), we log the timeout and move
    on to the next one instead of hanging the entire harness.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from core.settings import settings  # noqa: E402

DEFAULT_TIMEOUT = 30.0


async def _timed(label: str, coro, timeout: float) -> dict:
    """Run `coro` with a hard timeout and return a row for the summary table."""
    t0 = time.monotonic()
    row = {"source": label, "status": "?", "detail": "", "secs": 0.0}
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        row["status"] = "ok"
        row["detail"] = _describe(result)
    except TimeoutError:
        row["status"] = "timeout"
        row["detail"] = f"exceeded {timeout:.0f}s"
    except Exception as e:
        row["status"] = "error"
        row["detail"] = f"{type(e).__name__}: {e}"[:80]
    row["secs"] = round(time.monotonic() - t0, 2)
    return row


def _describe(result) -> str:
    """Render a fetcher's return value as a short human string."""
    if result is None:
        return "None"
    if isinstance(result, Path):
        size = result.stat().st_size if result.exists() else 0
        return f"{result.name} ({size} B)"
    if isinstance(result, list):
        if not result:
            return "0 items"
        if all(isinstance(p, Path) for p in result):
            return f"{len(result)} files"
        return f"{len(result)} items"
    if isinstance(result, dict):
        return f"dict({len(result)} keys)"
    return str(result)[:60]


async def _run_all(symbols: list[str], only: set[str] | None, timeout: float) -> list[dict]:
    from agents.ingest_agent import fetch_market_data, fetch_news

    # Lazy imports so missing keys don't break the script import itself.
    from core.alpha_vantage_client import fetch_alpha_vantage_for_symbols
    from core.fetchers import (
        fetch_earnings_calendar,
        fetch_google_news_rss,
        fetch_macro_indicators,
        fetch_reddit_sentiment,
        fetch_vix_and_fear_greed,
    )
    from core.finnhub_client import fetch_finnhub_for_symbols
    from core.models import init_db
    from core.sec_client import fetch_financial_data_for_symbols

    rows: list[dict] = []
    engine = init_db(settings.DATABASE_URL)

    tasks: list[tuple[str, object]] = [
        ("yfinance_prices", fetch_market_data(engine)),
        ("rss_news", fetch_news(engine)),
        ("sec_edgar", fetch_financial_data_for_symbols(symbols[:3])),
        ("fred_macro", fetch_macro_indicators()),
        ("finnhub", fetch_finnhub_for_symbols(symbols[:3])),
        ("alpha_vantage", fetch_alpha_vantage_for_symbols(symbols[:2], max_symbols=2)),
        ("google_news", fetch_google_news_rss(symbols[:2])),
        ("vix_fear_greed", fetch_vix_and_fear_greed()),
        ("earnings_calendar", fetch_earnings_calendar(symbols[:3])),
        ("reddit", fetch_reddit_sentiment(symbols[:2])),
    ]

    for label, coro in tasks:
        if only is not None and label not in only:
            # Cancel the coroutine we won't use so it doesn't warn at shutdown.
            coro.close()  # type: ignore[attr-defined]
            continue
        logger.info(f"[Harness] Running {label} (timeout={timeout}s)")
        rows.append(await _timed(label, coro, timeout))

    return rows


def _print_table(rows: list[dict], timeout: float) -> None:
    if not rows:
        print("\n(no sources selected)")
        return

    headers = ["source", "status", "secs", "detail"]
    widths = {h: max(len(h), max(len(str(r[h])) for r in rows)) for h in headers}

    def fmt(r: dict) -> str:
        return " | ".join(str(r[h]).ljust(widths[h]) for h in headers)

    print()
    print(fmt({h: h for h in headers}))
    print("-+-".join("-" * widths[h] for h in headers))
    for r in rows:
        print(fmt(r))
    print()

    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"{ok}/{len(rows)} sources returned data (timeout={timeout}s per source)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run every data fetcher once.")
    parser.add_argument(
        "--symbols",
        default=",".join(settings.YFINANCE_SYMBOLS[:3]),
        help="Comma-separated tickers to use for per-symbol fetchers.",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Comma-separated subset of sources (default: run all).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Hard per-source timeout in seconds.",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    rows = asyncio.run(_run_all(symbols, only, args.timeout))
    _print_table(rows, args.timeout)
    return 0 if all(r["status"] == "ok" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
