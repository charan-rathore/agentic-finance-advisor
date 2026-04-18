"""
core/wiki_ingest.py

Bridge between data/raw/ (fetched files) and data/wiki/ (compiled knowledge).

Reads raw JSON files and calls Gemini to update appropriate wiki pages with
structured YAML frontmatter and rich content.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
from loguru import logger

from core.settings import settings
from core.wiki import _get_gemini_model, _awrite_wiki_file, _aappend_log


def _create_frontmatter(
    page_type: str,
    symbol: Optional[str] = None,
    ttl_hours: int = 24,
    data_sources: list[str] = None,
    confidence: str = "medium"
) -> str:
    """Create YAML frontmatter for wiki pages."""
    frontmatter = {
        "page_type": page_type,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": ttl_hours,
        "data_sources": data_sources or [],
        "confidence": confidence,
        "stale": False
    }
    
    if symbol:
        frontmatter["symbol"] = symbol
    
    return "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\n"


async def process_sec_filing(raw_path: Path) -> None:
    """Process SEC filing and update stock wiki page."""
    try:
        logger.info(f"[WikiIngest] Processing SEC filing: {raw_path.name}")
        
        # Read raw SEC data
        with open(raw_path, 'r') as f:
            sec_data = json.load(f)
        
        symbol = sec_data.get("symbol", "UNKNOWN")
        filing_type = sec_data.get("filing_type", "UNKNOWN")
        filing_date = sec_data.get("date", "UNKNOWN")
        filing_text = sec_data.get("text", "")
        
        # Prepare Gemini prompt for SEC analysis
        prompt = f"""
Analyze this {filing_type} SEC filing for {symbol} and extract key information:

FILING TEXT (first 10,000 chars):
{filing_text[:10000]}

Please extract and summarize:

1. **Key Financial Metrics**: Any revenue, earnings, cash flow, or balance sheet highlights
2. **Risk Factors**: Material risks, uncertainties, or challenges mentioned
3. **Management Commentary**: Key statements from leadership about business outlook
4. **Material Events**: Any significant business developments, acquisitions, legal matters

Format your response as a structured analysis that can be added to a stock wiki page.
Focus on actionable insights for investors. Be concise but comprehensive.

If the filing text is incomplete or unclear, note what information is missing.
"""

        # Call Gemini
        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        analysis = response.text.strip()
        
        # Read existing stock page or create new one
        stock_wiki_path = Path(settings.WIKI_DIR) / "stocks" / f"{symbol}.md"
        
        existing_content = ""
        if stock_wiki_path.exists():
            existing_content = stock_wiki_path.read_text()
            # Remove old frontmatter if present
            if existing_content.startswith("---"):
                parts = existing_content.split("---", 2)
                if len(parts) >= 3:
                    existing_content = parts[2].strip()
        
        # Create new content with SEC section
        sec_section = f"""
## SEC Filing: {filing_type} ({filing_date})

{analysis}

> Source: SEC EDGAR filing processed on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
"""
        
        # Update or append SEC section
        if "## SEC Filing:" in existing_content:
            # Replace existing SEC section
            pattern = r"## SEC Filing:.*?(?=\n## |\n> Last updated:|\Z)"
            existing_content = re.sub(pattern, sec_section.strip(), existing_content, flags=re.DOTALL)
        else:
            # Append new SEC section
            existing_content += "\n" + sec_section
        
        # Add frontmatter and write
        frontmatter = _create_frontmatter(
            page_type="stock_entity",
            symbol=symbol,
            ttl_hours=168,  # SEC data stays fresh for a week
            data_sources=["sec_edgar"],
            confidence="high"
        )
        
        final_content = frontmatter + existing_content.strip()
        await _awrite_wiki_file(stock_wiki_path, final_content)
        
        # Update index
        await _update_wiki_index(f"Updated {symbol} with {filing_type} filing analysis")
        
        logger.info(f"[WikiIngest] Updated {symbol} wiki with SEC {filing_type} analysis")
        
    except Exception as e:
        logger.error(f"[WikiIngest] Error processing SEC filing {raw_path}: {e}")


async def process_macro_data(raw_path: Path) -> None:
    """Process macro indicators and update macro environment wiki page."""
    try:
        logger.info(f"[WikiIngest] Processing macro data: {raw_path.name}")
        
        # Read raw macro data
        with open(raw_path, 'r') as f:
            macro_data = json.load(f)
        
        indicators = macro_data.get("indicators", {})
        
        # Prepare Gemini prompt for macro analysis
        prompt = f"""
Analyze these current US economic indicators and write a comprehensive macro environment assessment:

ECONOMIC DATA:
{json.dumps(indicators, indent=2)}

Please provide:

1. **Current Rate Environment**: Fed funds rate level and trend implications
2. **Inflation Analysis**: CPI trends and what they mean for monetary policy
3. **Employment Signal**: Unemployment rate and labor market health
4. **GDP Context**: Economic growth trajectory
5. **Equity Market Implications**: How this macro backdrop affects stock investors

Write this as a comprehensive wiki page that helps investors understand the current economic context.
Use clear headings and actionable insights. Include specific numbers and trends.

Focus on what this means for different types of equity investments (growth vs value, sectors, etc.).
"""

        # Call Gemini
        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        analysis = response.text.strip()
        
        # Create macro environment page
        macro_wiki_path = Path(settings.WIKI_DIR) / "concepts" / "macro_environment.md"
        
        frontmatter = _create_frontmatter(
            page_type="concept",
            ttl_hours=72,  # Macro data refreshes every 3 days
            data_sources=["fred_api"],
            confidence="high"
        )
        
        final_content = frontmatter + analysis
        await _awrite_wiki_file(macro_wiki_path, final_content)
        
        await _update_wiki_index("Updated macro environment analysis")
        
        logger.info("[WikiIngest] Updated macro environment wiki page")
        
    except Exception as e:
        logger.error(f"[WikiIngest] Error processing macro data {raw_path}: {e}")


async def process_reddit_sentiment(raw_path: Path) -> None:
    """Process Reddit sentiment and update stock wiki page."""
    try:
        logger.info(f"[WikiIngest] Processing Reddit sentiment: {raw_path.name}")
        
        # Read raw Reddit data
        with open(raw_path, 'r') as f:
            reddit_data = json.load(f)
        
        symbol = reddit_data.get("symbol", "UNKNOWN")
        posts = reddit_data.get("posts", [])
        
        # Prepare Gemini prompt for sentiment analysis
        prompt = f"""
Analyze Reddit community sentiment for {symbol} based on these posts from r/investing and r/stocks:

REDDIT POSTS:
{json.dumps(posts[:15], indent=2)}  # Limit to avoid token overflow

Please extract:

1. **Overall Community Sentiment**: Bullish, bearish, or neutral with confidence level
2. **Key Concerns**: What are investors worried about?
3. **Excitement Factors**: What has the community excited?
4. **Notable DD (Due Diligence)**: Any substantial research or analysis shared
5. **Meme vs Fundamental**: Ratio of speculation vs serious analysis

Format this as a "Community Sentiment" section for a stock wiki page.
Be objective and highlight both positive and negative sentiment.
Include specific examples from highly-scored posts when relevant.

If sentiment is mixed, explain the different viewpoints clearly.
"""

        # Call Gemini
        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        sentiment_analysis = response.text.strip()
        
        # Update stock wiki page
        stock_wiki_path = Path(settings.WIKI_DIR) / "stocks" / f"{symbol}.md"
        
        existing_content = ""
        if stock_wiki_path.exists():
            existing_content = stock_wiki_path.read_text()
            # Remove old frontmatter if present
            if existing_content.startswith("---"):
                parts = existing_content.split("---", 2)
                if len(parts) >= 3:
                    existing_content = parts[2].strip()
        
        # Create community sentiment section
        sentiment_section = f"""
## Community Sentiment

{sentiment_analysis}

> Source: Reddit analysis from r/investing and r/stocks on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
"""
        
        # Update or append sentiment section
        if "## Community Sentiment" in existing_content:
            pattern = r"## Community Sentiment.*?(?=\n## |\n> Last updated:|\Z)"
            existing_content = re.sub(pattern, sentiment_section.strip(), existing_content, flags=re.DOTALL)
        else:
            existing_content += "\n" + sentiment_section
        
        # Add frontmatter and write
        frontmatter = _create_frontmatter(
            page_type="stock_entity",
            symbol=symbol,
            ttl_hours=12,  # Reddit sentiment changes quickly
            data_sources=["reddit"],
            confidence="medium"
        )
        
        final_content = frontmatter + existing_content.strip()
        await _awrite_wiki_file(stock_wiki_path, final_content)
        
        await _update_wiki_index(f"Updated {symbol} with Reddit community sentiment")
        
        logger.info(f"[WikiIngest] Updated {symbol} wiki with Reddit sentiment")
        
    except Exception as e:
        logger.error(f"[WikiIngest] Error processing Reddit sentiment {raw_path}: {e}")


async def process_earnings_calendar(raw_path: Path) -> None:
    """Process earnings calendar and create/update earnings calendar wiki page."""
    try:
        logger.info(f"[WikiIngest] Processing earnings calendar: {raw_path.name}")
        
        # Read raw earnings data
        with open(raw_path, 'r') as f:
            earnings_data = json.load(f)
        
        companies = earnings_data.get("companies", {})
        
        # Prepare Gemini prompt for earnings analysis
        prompt = f"""
Create an earnings calendar wiki page based on this upcoming earnings data:

EARNINGS DATA:
{json.dumps(companies, indent=2)}

Please create:

1. **High Priority Earnings** (within 7 days): List companies with imminent earnings
2. **Upcoming Earnings Timeline**: Organized by date/week
3. **Key Companies to Watch**: Focus on high-impact earnings
4. **Earnings Season Context**: What to expect from this earnings cycle

For each company, include:
- Earnings date
- Analyst estimates (if available)
- Why this earnings report matters
- Key metrics to watch

Flag any earnings within the next 7 days as **HIGH PRIORITY**.

Format this as a comprehensive earnings calendar that helps investors prepare.
"""

        # Call Gemini
        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        calendar_content = response.text.strip()
        
        # Create earnings calendar page
        earnings_wiki_path = Path(settings.WIKI_DIR) / "concepts" / "earnings_calendar.md"
        
        frontmatter = _create_frontmatter(
            page_type="concept",
            ttl_hours=24,  # Earnings calendar updates daily
            data_sources=["yfinance_calendar"],
            confidence="high"
        )
        
        final_content = frontmatter + calendar_content
        await _awrite_wiki_file(earnings_wiki_path, final_content)
        
        await _update_wiki_index("Updated earnings calendar")
        
        logger.info("[WikiIngest] Updated earnings calendar wiki page")
        
    except Exception as e:
        logger.error(f"[WikiIngest] Error processing earnings calendar {raw_path}: {e}")


async def process_market_sentiment(raw_path: Path) -> None:
    """Process VIX and Fear & Greed data to update market sentiment wiki page."""
    try:
        logger.info(f"[WikiIngest] Processing market sentiment: {raw_path.name}")
        
        # Read raw market sentiment data
        with open(raw_path, 'r') as f:
            sentiment_data = json.load(f)
        
        # Prepare Gemini prompt for market sentiment analysis
        prompt = f"""
Analyze current market sentiment based on this VIX and Fear & Greed data:

MARKET SENTIMENT DATA:
{json.dumps(sentiment_data, indent=2)}

Please create a comprehensive market sentiment analysis covering:

1. **VIX Analysis**: Current volatility level and what it means
   - Below 15: Calm market conditions
   - 15-25: Moderate volatility
   - Above 25: Fear/uncertainty in markets

2. **Fear & Greed Index**: Current reading and interpretation
   - What's driving current sentiment
   - Historical context

3. **Market Implications**: What this means for different investment strategies
   - Risk-on vs risk-off positioning
   - Sector rotation implications
   - Timing considerations

4. **Actionable Insights**: How investors should position given current sentiment

Format this as a market sentiment wiki page that helps investors understand current market psychology.
Include specific numbers and clear interpretations.
"""

        # Call Gemini
        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        sentiment_analysis = response.text.strip()
        
        # Create market sentiment page
        sentiment_wiki_path = Path(settings.WIKI_DIR) / "concepts" / "market_sentiment.md"
        
        frontmatter = _create_frontmatter(
            page_type="concept",
            ttl_hours=6,  # Market sentiment changes quickly
            data_sources=["vix", "cnn_fear_greed"],
            confidence="high"
        )
        
        final_content = frontmatter + sentiment_analysis
        await _awrite_wiki_file(sentiment_wiki_path, final_content)
        
        await _update_wiki_index("Updated market sentiment analysis")
        
        logger.info("[WikiIngest] Updated market sentiment wiki page")
        
    except Exception as e:
        logger.error(f"[WikiIngest] Error processing market sentiment {raw_path}: {e}")


async def process_sec_company_facts(raw_path: Path) -> None:
    """
    Process a `company_facts_<CIK>_<ts>.json` file produced by core/sec_client.py.

    These payloads contain every GAAP tag a company has ever reported (thousands).
    We don't hand the whole blob to Gemini; we extract the latest value for a
    short list of high-signal concepts and hand just those to the LLM.
    """
    try:
        logger.info(f"[WikiIngest] Processing SEC company facts: {raw_path.name}")
        with open(raw_path, "r") as f:
            sec_data = json.load(f)

        cik = str(sec_data.get("cik", "")).zfill(10)
        entity_name = sec_data.get("entityName", "Unknown")
        us_gaap = sec_data.get("facts", {}).get("us-gaap", {})

        from core.sec_client import sec_client  # local to avoid cycles
        symbol = None
        for ticker, mapped_cik in getattr(sec_client, "_TICKER_TO_CIK", {}).items():
            if mapped_cik.lstrip("0") == cik.lstrip("0"):
                symbol = ticker
                break
        if symbol is None:
            fname = raw_path.name
            for candidate in settings.YFINANCE_SYMBOLS:
                cand_cik = await sec_client.search_company_by_ticker(candidate)
                if cand_cik and cand_cik.lstrip("0") == cik.lstrip("0"):
                    symbol = candidate
                    break
        if symbol is None:
            logger.warning(
                f"[WikiIngest] Could not map CIK {cik} to a tracked ticker; skipping"
            )
            return

        def _latest(tag: str) -> dict | None:
            units = us_gaap.get(tag, {}).get("units", {}).get("USD")
            return units[-1] if units else None

        highlights = {
            "Revenues": _latest("Revenues") or _latest("RevenueFromContractWithCustomerExcludingAssessedTax"),
            "NetIncome": _latest("NetIncomeLoss"),
            "Assets": _latest("Assets"),
            "Liabilities": _latest("Liabilities"),
            "StockholdersEquity": _latest("StockholdersEquity"),
            "CashAndCashEquivalents": _latest("CashAndCashEquivalentsAtCarryingValue"),
        }

        prompt = f"""Summarise the latest reported fundamentals for {entity_name} ({symbol}).

LATEST GAAP FIGURES (USD, may be quarterly or annual — check each `form` field):
{json.dumps(highlights, indent=2, default=str)}

Write a compact wiki section that:
1. States the most recent revenue, net income, assets, and equity with the reporting period.
2. Highlights any quarter-over-quarter or year-over-year change if multiple data points are present.
3. Calls out leverage (liabilities / equity) in one sentence.
4. Is specific — use the actual dollar figures above, no invented numbers.

Limit to ~200 words. Markdown only, no preamble."""

        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        analysis = response.text.strip()

        stock_wiki_path = Path(settings.WIKI_DIR) / "stocks" / f"{symbol}.md"
        existing_content = ""
        if stock_wiki_path.exists():
            existing_content = stock_wiki_path.read_text()
            if existing_content.startswith("---"):
                parts = existing_content.split("---", 2)
                if len(parts) >= 3:
                    existing_content = parts[2].strip()

        section_header = "## SEC Fundamentals (EDGAR)"
        new_section = (
            f"\n{section_header}\n\n{analysis}\n\n"
            f"> Source: SEC EDGAR company facts, processed "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        )

        if section_header in existing_content:
            pattern = rf"{re.escape(section_header)}.*?(?=\n## |\n> Last updated:|\Z)"
            existing_content = re.sub(
                pattern, new_section.strip(), existing_content, flags=re.DOTALL
            )
        else:
            existing_content = existing_content.rstrip() + "\n" + new_section

        frontmatter = _create_frontmatter(
            page_type="stock_entity",
            symbol=symbol,
            ttl_hours=168,
            data_sources=["sec_edgar"],
            confidence="high",
        )
        await _awrite_wiki_file(stock_wiki_path, frontmatter + existing_content.strip())
        await _update_wiki_index(f"Updated {symbol} with SEC fundamentals")
        logger.info(f"[WikiIngest] Updated {symbol} wiki with SEC fundamentals")

    except Exception as e:
        logger.error(f"[WikiIngest] Error processing SEC company facts {raw_path}: {e}")


async def process_alpha_vantage(raw_path: Path) -> None:
    """Route Alpha Vantage quote/overview/income payloads into the symbol's wiki page."""
    try:
        with open(raw_path, "r") as f:
            data = json.load(f)
        symbol = data.get("symbol")
        endpoint = data.get("endpoint", "")
        if not symbol:
            return

        body = (
            data.get("quote")
            or data.get("overview")
            or {
                "annual_reports": data.get("annual_reports", []),
                "quarterly_reports": data.get("quarterly_reports", []),
            }
        )
        prompt = f"""Write a concise wiki section for {symbol} based on this Alpha Vantage
{endpoint} payload. Use only the numbers below.

PAYLOAD:
{json.dumps(body, indent=2, default=str)[:6000]}

Cover, in 120-180 words:
- Latest quote or fundamentals highlights (market cap, PE, PEG, margins if available)
- Trend signal (is the latest figure better or worse than the previous one?)
- A one-line caveat about data freshness.

Markdown only, no preamble."""

        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        analysis = response.text.strip()

        stock_wiki_path = Path(settings.WIKI_DIR) / "stocks" / f"{symbol}.md"
        existing = ""
        if stock_wiki_path.exists():
            existing = stock_wiki_path.read_text()
            if existing.startswith("---"):
                parts = existing.split("---", 2)
                if len(parts) >= 3:
                    existing = parts[2].strip()

        section_header = f"## Alpha Vantage — {endpoint}"
        section = (
            f"\n{section_header}\n\n{analysis}\n\n"
            f"> Source: Alpha Vantage, fetched "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        )
        if section_header in existing:
            pattern = rf"{re.escape(section_header)}.*?(?=\n## |\n> Last updated:|\Z)"
            existing = re.sub(pattern, section.strip(), existing, flags=re.DOTALL)
        else:
            existing = existing.rstrip() + "\n" + section

        frontmatter = _create_frontmatter(
            page_type="stock_entity",
            symbol=symbol,
            ttl_hours=24,
            data_sources=["alpha_vantage"],
            confidence="high",
        )
        await _awrite_wiki_file(stock_wiki_path, frontmatter + existing.strip())
        await _update_wiki_index(f"Alpha Vantage {endpoint} for {symbol}")
        logger.info(f"[WikiIngest] Updated {symbol} wiki with Alpha Vantage {endpoint}")
    except Exception as e:
        logger.error(f"[WikiIngest] Error processing Alpha Vantage {raw_path}: {e}")


async def process_finnhub(raw_path: Path) -> None:
    """Route Finnhub quote/news/recommendation payloads."""
    try:
        with open(raw_path, "r") as f:
            data = json.load(f)
        symbol = data.get("symbol")
        endpoint = data.get("endpoint", "")
        if not symbol:
            return

        if endpoint == "quote":
            body = data.get("quote", {})
            prompt_body = json.dumps(body, indent=2)
            ask = (
                "Summarise the latest Finnhub quote in 3-5 bullets: current price, "
                "percent change today, intraday range, and whether the stock is "
                "trading above or below the previous close."
            )
        elif endpoint == "company-news":
            articles = data.get("articles", [])[:12]
            prompt_body = json.dumps(articles, indent=2, default=str)
            ask = (
                "Summarise the last week's news for this ticker in 4-6 bullet "
                "points. Group by theme (earnings, product, regulation, macro). "
                "Cite the most important 1-2 headlines by source."
            )
        else:
            body = data.get("trends", [])
            prompt_body = json.dumps(body, indent=2, default=str)
            ask = (
                "Summarise analyst recommendation trends over the past months. "
                "Report strong-buy/buy/hold/sell/strong-sell counts for the "
                "latest period and note any clear shift vs the earlier period."
            )

        prompt = (
            f"{ask}\n\nDATA:\n{prompt_body}\n\nMarkdown only, ~120 words."
        )
        gemini = _get_gemini_model()
        response = await gemini.generate_content_async(prompt)
        analysis = response.text.strip()

        stock_wiki_path = Path(settings.WIKI_DIR) / "stocks" / f"{symbol}.md"
        existing = ""
        if stock_wiki_path.exists():
            existing = stock_wiki_path.read_text()
            if existing.startswith("---"):
                parts = existing.split("---", 2)
                if len(parts) >= 3:
                    existing = parts[2].strip()

        section_header = f"## Finnhub — {endpoint}"
        section = (
            f"\n{section_header}\n\n{analysis}\n\n"
            f"> Source: Finnhub, fetched "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        )
        if section_header in existing:
            pattern = rf"{re.escape(section_header)}.*?(?=\n## |\n> Last updated:|\Z)"
            existing = re.sub(pattern, section.strip(), existing, flags=re.DOTALL)
        else:
            existing = existing.rstrip() + "\n" + section

        frontmatter = _create_frontmatter(
            page_type="stock_entity",
            symbol=symbol,
            ttl_hours=6 if endpoint == "quote" else 12,
            data_sources=["finnhub"],
            confidence="medium" if endpoint == "company-news" else "high",
        )
        await _awrite_wiki_file(stock_wiki_path, frontmatter + existing.strip())
        await _update_wiki_index(f"Finnhub {endpoint} for {symbol}")
        logger.info(f"[WikiIngest] Updated {symbol} wiki with Finnhub {endpoint}")
    except Exception as e:
        logger.error(f"[WikiIngest] Error processing Finnhub {raw_path}: {e}")


async def process_all_new_raw_files() -> int:
    """
    Scan data/raw/ for unprocessed JSON files and route them to the right
    processor. Processed filenames are recorded in `data/wiki/log.md` so we
    never re-process the same file twice.
    """
    try:
        logger.info("[WikiIngest] Scanning for new raw data files...")

        raw_dir = Path(settings.RAW_DATA_DIR)
        if not raw_dir.exists():
            logger.warning(f"[WikiIngest] Raw data directory not found: {raw_dir}")
            return 0

        log_path = Path(settings.WIKI_DIR) / "log.md"
        processed_files: set[str] = set()
        if log_path.exists():
            for line in log_path.read_text().splitlines():
                if "Processed:" in line:
                    processed_files.add(line.split("Processed:")[-1].strip())

        json_files = list(raw_dir.glob("**/*.json"))
        new_files = [f for f in json_files if f.name not in processed_files]
        logger.info(f"[WikiIngest] Found {len(new_files)} new files to process")

        processed_count = 0
        for filepath in new_files:
            try:
                filename = filepath.name

                if filename.startswith("sec_"):
                    await process_sec_filing(filepath)
                elif filename.startswith("company_facts_"):
                    await process_sec_company_facts(filepath)
                elif filename.startswith("macro_indicators_"):
                    await process_macro_data(filepath)
                elif filename.startswith("reddit_"):
                    await process_reddit_sentiment(filepath)
                elif filename.startswith("alphavantage_"):
                    await process_alpha_vantage(filepath)
                elif filename.startswith("finnhub_"):
                    await process_finnhub(filepath)
                elif filename.startswith("googlenews_"):
                    logger.debug(f"[WikiIngest] Skipping Google News file: {filename}")
                    continue
                elif filename.startswith("market_sentiment_"):
                    await process_market_sentiment(filepath)
                elif filename.startswith("earnings_calendar_"):
                    await process_earnings_calendar(filepath)
                else:
                    logger.debug(f"[WikiIngest] Unknown file type: {filename}")
                    continue

                await _aappend_log(f"Processed: {filename}")
                processed_count += 1
                logger.info(f"[WikiIngest] Processed {filename}")

            except Exception as e:
                logger.error(f"[WikiIngest] Error processing {filepath}: {e}")
                continue

        logger.info(f"[WikiIngest] Successfully processed {processed_count} new files")
        return processed_count

    except Exception as e:
        logger.error(f"[WikiIngest] Error in process_all_new_raw_files: {e}")
        return 0


async def _update_wiki_index(message: str) -> None:
    """Update the wiki index with a new entry."""
    try:
        index_path = Path(settings.WIKI_DIR) / "index.md"
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        entry = f"- {timestamp}: {message}\n"
        
        if index_path.exists():
            content = index_path.read_text()
            # Insert new entry after the header
            lines = content.split('\n')
            header_end = 0
            for i, line in enumerate(lines):
                if line.startswith('#') or line.startswith('---'):
                    header_end = i + 1
            
            lines.insert(header_end, entry.strip())
            new_content = '\n'.join(lines)
        else:
            new_content = f"# Wiki Index\n\n{entry}"
        
        await _awrite_wiki_file(index_path, new_content)
        
    except Exception as e:
        logger.error(f"[WikiIngest] Error updating index: {e}")