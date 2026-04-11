"""Expense categorization and spending pattern analysis."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, BaseFinanceAgent


class ExpenseAnalysisAgent(BaseFinanceAgent):
    """Summarizes spend by category; extend with LLM + rules over real data."""

    name = "expense_analysis"

    async def run(self, context: AgentContext) -> dict[str, Any]:
        # Placeholder: wire to TransactionRecord queries and Gemini summarization.
        return {
            "summary": "Expense baseline established (stub).",
            "top_categories": ["housing", "groceries", "transport"],
        }
