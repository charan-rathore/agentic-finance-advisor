"""One-off smoke test for Finnhub + Alpha Vantage clients.

Run:  python scripts/smoke_new_fetchers.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.alpha_vantage_client import alpha_vantage_client
from core.finnhub_client import finnhub_client


async def main() -> None:
    print("\n--- Finnhub quote (AAPL) ---")
    print(await finnhub_client.quote("AAPL"))

    print("\n--- Finnhub news (AAPL) ---")
    print(await finnhub_client.company_news("AAPL"))

    print("\n--- Finnhub recommendation (AAPL) ---")
    print(await finnhub_client.recommendation_trends("AAPL"))

    print("\n--- Alpha Vantage quote (AAPL) ---")
    print(await alpha_vantage_client.global_quote("AAPL"))

    print("\n--- Alpha Vantage overview (AAPL) ---")
    print(await alpha_vantage_client.overview("AAPL"))


if __name__ == "__main__":
    asyncio.run(main())
