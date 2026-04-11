"""Plain-language financial explanations powered by RAG + Gemini (stub)."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, BaseFinanceAgent


class FinancialExplanationAgent(BaseFinanceAgent):
    name = "financial_explanation"

    async def run(self, context: AgentContext) -> dict[str, Any]:
        topic = str(context.get("topic", "compound interest"))
        return {
            "topic": topic,
            "explanation": f"Brief overview of {topic} (connect RAG + Gemini here).",
        }
