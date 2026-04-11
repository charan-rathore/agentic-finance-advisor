"""Budget recommendations from income, goals, and historical spend."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, BaseFinanceAgent


class BudgetAgent(BaseFinanceAgent):
    name = "budget"

    async def run(self, context: AgentContext) -> dict[str, Any]:
        return {
            "recommendation": "Target 50/30/20 split as a starting heuristic (stub).",
            "suggested_monthly_savings_rate": 0.20,
        }
