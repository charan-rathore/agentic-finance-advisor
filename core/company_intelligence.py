"""
core/company_intelligence.py

Per-ticker risk profiles + wiki cross-references.

Data source: `data/reference/companies.yaml` (editable; covers all 17 tickers
in the default YFINANCE_SYMBOLS). If PyYAML or the file is unavailable we fall
back to an empty dict — callers still get a safe generic profile via
`get_company_intelligence`.

This module exposes the same surface it always did so nothing downstream
needs to change:

    COMPANY_INTELLIGENCE: dict[str, dict]
    get_company_intelligence(symbol) -> dict
    get_enhanced_context_for_symbol(symbol) -> str
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from loguru import logger

_YAML_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "companies.yaml"


@lru_cache(maxsize=1)
def _load_yaml() -> dict[str, dict]:
    try:
        import yaml  # local import so the rest of the app works without PyYAML
    except ImportError:
        logger.warning("[CompanyIntelligence] PyYAML not installed — using empty profile map")
        return {}

    if not _YAML_PATH.exists():
        logger.warning(f"[CompanyIntelligence] {_YAML_PATH} missing — using empty profile map")
        return {}

    try:
        with _YAML_PATH.open("r") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            logger.error(f"[CompanyIntelligence] {_YAML_PATH} root is not a mapping")
            return {}
        return data
    except Exception as e:
        logger.error(f"[CompanyIntelligence] Failed to load {_YAML_PATH}: {e}")
        return {}


# Public alias kept for back-compat with modules that import COMPANY_INTELLIGENCE.
# It's a view over the cached YAML; reload the process to pick up edits.
COMPANY_INTELLIGENCE: dict[str, dict] = _load_yaml()


_GENERIC_PROFILE: dict = {
    "key_risks": [
        "Market volatility",
        "Competitive pressure",
        "Regulatory changes",
    ],
    "cross_references": [
        "[[Market Risk]]",
        "[[Sector Analysis]]",
        "[[Competitive Landscape]]",
    ],
    "sector": "General",
    "defensive_rating": "Market Average",
}


def get_company_intelligence(symbol: str) -> dict:
    """Get intelligence data for a company symbol (generic fallback if unknown)."""
    return COMPANY_INTELLIGENCE.get(symbol, _GENERIC_PROFILE)


def get_enhanced_context_for_symbol(symbol: str) -> str:
    """Get enhanced context string for wiki generation."""
    intel = get_company_intelligence(symbol)
    return f"""
COMPANY INTELLIGENCE FOR {symbol}:
Sector: {intel.get('sector', 'General')}
Defensive Rating: {intel.get('defensive_rating', 'Market Average')}

Key Material Risks to Address:
{chr(10).join(f"- {risk}" for risk in intel.get('key_risks', []))}

Sophisticated Cross-References to Use:
{chr(10).join(intel.get('cross_references', []))}
"""
