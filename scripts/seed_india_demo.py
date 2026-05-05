"""
scripts/seed_india_demo.py

Demo-readiness check. The 25 India seed pages and 8 US seed pages are now
committed to the repo, so this script does NOT call any LLM and does NOT
fetch from the network. It simply verifies that every expected page exists
and reports any missing ones.

Run before a demo to fail fast if anything was deleted or moved.

    python scripts/seed_india_demo.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INDIA = ROOT / "data" / "wiki_india"
US = ROOT / "data" / "wiki"

EXPECTED_INDIA = {
    "equities": ["NIFTY_50", "NIFTY_BANK", "NIFTY_NEXT_50", "RELIANCE", "TCS"],
    "mutual_funds": [
        "Parag_Parikh_Flexi_Cap",
        "HDFC_Index_Nifty_50",
        "ICICI_Prudential_Bluechip",
        "Axis_ELSS",
        "Mirae_Asset_ELSS",
        "SBI_Small_Cap",
        "Quant_Active",
        "Nippon_India_Multi_Asset",
    ],
    "macro": ["rbi_rates", "inflation_cpi", "fiscal_calendar"],
    "concepts": [
        "sip",
        "elss_vs_ppf_vs_nps",
        "emergency_fund",
        "sip_vs_lumpsum",
        "ltcg_stcg_2024",
        "demat_account",
        "direct_vs_regular",
        "expense_ratio",
        "market_cap_categories",
    ],
    "faq": [
        "what_is_sip",
        "elss_vs_ppf",
        "emergency_fund",
        "how_to_start_investing",
        "index_fund_or_active",
        "should_i_stop_sip",
        "how_much_to_invest",
        "what_is_nav",
        "tax_save_india",
        "lock_in_rules",
    ],
}

EXPECTED_US = {
    "stocks": ["AAPL", "GOOGL", "JNJ", "MSFT", "NVDA", "AMZN", "META", "TSLA", "BRK_B", "JPM"],
    "concepts": [
        "finance_basics",
        "401k_basics",
        "etf_vs_mutual_fund_us",
        "roth_vs_traditional_ira",
    ],
}


def _check(group: dict[str, list[str]], root: Path) -> tuple[int, list[str]]:
    missing: list[str] = []
    found = 0
    for subdir, slugs in group.items():
        for slug in slugs:
            path = root / subdir / f"{slug}.md"
            if path.is_file():
                found += 1
            else:
                missing.append(str(path.relative_to(ROOT)))
    return found, missing


def main() -> int:
    print("Paisa Pal demo seed check")
    print("=" * 50)

    found_in, missing_in = _check(EXPECTED_INDIA, INDIA)
    expected_in = sum(len(v) for v in EXPECTED_INDIA.values())
    print(f"India wiki: {found_in}/{expected_in} pages present")

    found_us, missing_us = _check(EXPECTED_US, US)
    expected_us = sum(len(v) for v in EXPECTED_US.values())
    print(f"US wiki:    {found_us}/{expected_us} pages present")

    if missing_in or missing_us:
        print("\nMissing pages:")
        for path in missing_in + missing_us:
            print(f"  - {path}")
        return 1

    print("\nAll seed pages present. Demo-ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
