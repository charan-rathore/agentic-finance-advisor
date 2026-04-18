"""
core/sec_client.py

SEC EDGAR API client for fetching financial data.

The SEC EDGAR API is completely free and provides:
- Company facts (revenue, assets, liabilities, cash flow)
- Recent filings (10-K, 10-Q, 8-K)
- Company information (SIC codes, business descriptions)

Data Flow:
  SEC API → data/raw/sec/ → Processing → data/wiki/stocks/

Rate Limits: 10 requests per second (we'll respect this)
Authentication: None (just requires User-Agent header)
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import aiofiles
import httpx
from loguru import logger
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.settings import settings

_stdlib_logger = logging.getLogger(__name__)


class SECClient:
    """Async client for SEC EDGAR API."""

    def __init__(self) -> None:
        self.base_url = settings.SEC_BASE_URL
        self.headers = {
            "User-Agent": settings.SEC_USER_AGENT,
            "Accept": "application/json",
        }
        self.raw_dir = Path(settings.RAW_DATA_DIR) / "sec"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # Rate limiting: SEC allows 10 req/sec
        self._last_request_time = 0.0
        self._min_interval = 0.1  # 100ms between requests

    async def _rate_limit(self) -> None:
        """Ensure we don't exceed SEC rate limits."""
        now = asyncio.get_event_loop().time()
        time_since_last = now - self._last_request_time
        if time_since_last < self._min_interval:
            await asyncio.sleep(self._min_interval - time_since_last)
        self._last_request_time = asyncio.get_event_loop().time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
    )
    async def _make_request(self, url: str) -> dict:
        """Make rate-limited request to SEC API."""
        await self._rate_limit()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def _save_raw_data(self, filename: str, data: dict) -> Path:
        """Save raw API response to data/raw/sec/."""
        filepath = self.raw_dir / filename
        async with aiofiles.open(filepath, "w") as f:
            await f.write(json.dumps(data, indent=2))
        logger.debug(f"[SEC] Saved raw data to {filepath}")
        return filepath

    @staticmethod
    def _content_hash(data: dict) -> str:
        """
        Stable SHA-256 over the JSON payload. `sort_keys=True` is the bit that
        makes the hash reproducible across runs — dict ordering would otherwise
        produce spurious mismatches.
        """
        canonical = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _latest_company_facts_path(self, cik_formatted: str) -> Optional[Path]:
        """Return the most recently written company_facts file for a CIK, or None."""
        candidates = sorted(
            self.raw_dir.glob(f"company_facts_{cik_formatted}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _matches_existing_on_disk(self, cik_formatted: str, new_hash: str) -> Optional[Path]:
        """
        If the latest company_facts file on disk for this CIK has the same
        SHA-256 as the freshly fetched payload, return its path so the caller
        can short-circuit. Otherwise return None.

        We only compare against the *latest* file (not every historical copy)
        — if the payload changed then changed back we still want the new one on
        disk to advance mtime-based freshness checks downstream.
        """
        latest = self._latest_company_facts_path(cik_formatted)
        if latest is None:
            return None
        try:
            with open(latest) as f:
                existing = json.load(f)
        except Exception as e:
            logger.debug(f"[SEC] Could not read {latest} for hash comparison: {e}")
            return None
        if self._content_hash(existing) == new_hash:
            return latest
        return None

    async def get_company_facts(self, cik: str) -> Optional[dict]:
        """
        Get company financial facts (revenue, assets, etc.) by CIK.

        Deduplication: before writing, we SHA-256 the payload and compare
        against the most recent `company_facts_<CIK>_*.json` already on disk.
        If they are byte-for-byte identical, we skip the write entirely — SEC
        companyfacts only changes when the company files, so hammering the
        endpoint daily otherwise produced 21 MB+ of redundant AAPL copies.

        Args:
            cik: Central Index Key (e.g., "0000320193" for Apple)

        Returns:
            Dict with financial facts or None if error

        Example:
            facts = await sec_client.get_company_facts("0000320193")
            revenue = facts["facts"]["us-gaap"]["Revenues"]
        """
        try:
            cik_formatted = cik.zfill(10)
            url = f"{self.base_url}/companyfacts/CIK{cik_formatted}.json"

            logger.info(f"[SEC] Fetching company facts for CIK {cik_formatted}")
            data = await self._make_request(url)

            new_hash = self._content_hash(data)
            existing = self._matches_existing_on_disk(cik_formatted, new_hash)
            if existing is not None:
                logger.info(
                    f"[SEC] Unchanged payload for CIK {cik_formatted} "
                    f"(sha256={new_hash[:12]}); reusing {existing.name}"
                )
                # Touch mtime so downstream "latest file" lookups still treat this
                # as the freshest snapshot — we did confirm the data with SEC.
                os.utime(existing, None)
                return data

            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"company_facts_{cik_formatted}_{timestamp}.json"
            await self._save_raw_data(filename, data)

            return data

        except Exception as e:
            logger.error(f"[SEC] Failed to fetch company facts for CIK {cik}: {e}")
            return None

    async def get_company_concept(self, cik: str, taxonomy: str, tag: str) -> Optional[dict]:
        """
        Get specific financial concept for a company.

        Args:
            cik: Central Index Key
            taxonomy: "us-gaap" or "dei"
            tag: Financial concept (e.g., "Revenue", "Assets")

        Returns:
            Dict with concept data or None if error
        """
        try:
            cik_formatted = cik.zfill(10)
            url = f"{self.base_url}/companyconcept/CIK{cik_formatted}/{taxonomy}/{tag}.json"

            logger.info(f"[SEC] Fetching {taxonomy}:{tag} for CIK {cik_formatted}")
            data = await self._make_request(url)

            # Save raw data
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"concept_{cik_formatted}_{taxonomy}_{tag}_{timestamp}.json"
            await self._save_raw_data(filename, data)

            return data

        except Exception as e:
            logger.error(f"[SEC] Failed to fetch {taxonomy}:{tag} for CIK {cik}: {e}")
            return None

    async def search_company_by_ticker(self, ticker: str) -> Optional[str]:
        """
        Find CIK for a stock ticker symbol.

        Note: This is a simplified lookup. In production, you'd use
        the SEC company tickers JSON file for comprehensive mapping.

        Args:
            ticker: Stock symbol (e.g., "AAPL")

        Returns:
            CIK string or None if not found
        """
        # Comprehensive ticker to CIK mappings for top market cap + stable companies
        ticker_to_cik = {
            # Top Market Cap Leaders (AI & Tech)
            "NVDA": "0001045810",  # NVIDIA Corporation (#1 - $4.5T, AI leader)
            "AAPL": "0000320193",  # Apple Inc. (#2 - $4.0T)
            "GOOGL": "0001652044",  # Alphabet Inc. (#3 - $3.8T)
            "MSFT": "0000789019",  # Microsoft Corporation (#4 - $3.0T)
            "AMZN": "0001018724",  # Amazon.com Inc. (#5 - $2.5T)
            "TSM": "0001046179",  # Taiwan Semiconductor (#6 - $2.0T, AI chips)
            "META": "0001326801",  # Meta Platforms Inc. (#8 - $1.6T)
            "AVGO": "0001730168",  # Broadcom Inc. (#9 - $1.7T, AI infrastructure)
            "TSLA": "0001318605",  # Tesla Inc. (#10 - $1.6T)
            # Stability & Diversification Leaders
            "BRK.B": "0001067983",  # Berkshire Hathaway Class B (Warren Buffett)
            "JNJ": "0000200406",  # Johnson & Johnson (Healthcare stability)
            "JPM": "0000019617",  # JPMorgan Chase & Co. (Financial stability)
            "V": "0001403161",  # Visa Inc. (Payment processing moat)
            "UNH": "0000731766",  # UnitedHealth Group (Healthcare)
            "PG": "0000080424",  # Procter & Gamble (Consumer staples)
            "HD": "0000354950",  # Home Depot (Consumer discretionary)
            "MA": "0001141391",  # Mastercard Inc. (Payment processing)
            # Additional Quality Companies
            "WMT": "0000104169",  # Walmart Inc. (Retail stability)
            "KO": "0000021344",  # Coca-Cola Company (Consumer staples)
            "DIS": "0001001039",  # Walt Disney Company (Entertainment)
            "NFLX": "0001065280",  # Netflix Inc. (Streaming leader)
        }

        cik = ticker_to_cik.get(ticker.upper())
        if cik:
            logger.info(f"[SEC] Found CIK {cik} for ticker {ticker}")
            return cik
        else:
            logger.warning(f"[SEC] No CIK mapping found for ticker {ticker}")
            return None


# Global instance
sec_client = SECClient()


async def fetch_financial_data_for_symbols(symbols: list[str]) -> list[dict]:
    """
    Fetch SEC financial data for a list of stock symbols.

    This is the main function called by the ingest agent.

    Args:
        symbols: List of ticker symbols (e.g., ["AAPL", "MSFT"])

    Returns:
        List of dicts with financial data for each symbol
    """
    results = []

    for symbol in symbols:
        try:
            # Find CIK for this ticker
            cik = await sec_client.search_company_by_ticker(symbol)
            if not cik:
                continue

            # Get company financial facts
            facts = await sec_client.get_company_facts(cik)
            if not facts:
                continue

            # Extract key financial metrics
            financial_data = {
                "symbol": symbol,
                "cik": cik,
                "company_name": facts.get("entityName", "Unknown"),
                "sic_code": facts.get("sic", ""),
                "sic_description": facts.get("sicDescription", ""),
                "raw_data_path": f"data/raw/sec/company_facts_{cik}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json",
                "fetched_at": datetime.now(UTC).isoformat(),
            }

            # Extract recent revenue, assets, liabilities if available
            try:
                us_gaap = facts.get("facts", {}).get("us-gaap", {})

                # Revenue (multiple possible field names)
                for revenue_field in ["Revenues", "Revenue", "SalesRevenueNet"]:
                    if revenue_field in us_gaap:
                        units = us_gaap[revenue_field].get("units", {})
                        if "USD" in units:
                            recent_revenue = units["USD"][-1] if units["USD"] else None
                            if recent_revenue:
                                financial_data["recent_revenue"] = {
                                    "value": recent_revenue.get("val"),
                                    "period": recent_revenue.get("end"),
                                    "form": recent_revenue.get("form"),
                                }
                        break

                # Total Assets
                if "Assets" in us_gaap:
                    units = us_gaap["Assets"].get("units", {})
                    if "USD" in units:
                        recent_assets = units["USD"][-1] if units["USD"] else None
                        if recent_assets:
                            financial_data["recent_assets"] = {
                                "value": recent_assets.get("val"),
                                "period": recent_assets.get("end"),
                                "form": recent_assets.get("form"),
                            }

            except Exception as e:
                logger.warning(f"[SEC] Could not extract financial metrics for {symbol}: {e}")

            results.append(financial_data)
            logger.info(
                f"[SEC] Successfully fetched data for {symbol} ({financial_data['company_name']})"
            )

        except Exception as e:
            logger.error(f"[SEC] Failed to process {symbol}: {e}")
            continue

    return results
