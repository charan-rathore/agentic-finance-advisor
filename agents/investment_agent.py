"""High-level investment education and allocation ideas (not personalized advice)."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, BaseFinanceAgent


class InvestmentInsightsAgent(BaseFinanceAgent):
    name = "investment_insights"

    async def run(self, context: AgentContext) -> dict[str, Any]:
        return {
            "disclaimer": "Educational information only; not investment advice.",
            "themes": [
                "Diversification across asset classes",
                "Low-cost index funds for long horizons",
                "Risk tolerance alignment",
            ],
        }
