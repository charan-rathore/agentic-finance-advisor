"""Market news fetch + sentiment (stub; plug Gemini + news API)."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, BaseFinanceAgent
from core.config import get_settings


class NewsSentimentAgent(BaseFinanceAgent):
    name = "news_sentiment"

    async def run(self, context: AgentContext) -> dict[str, Any]:
        if not get_settings().enable_news_sentiment:
            return {"skipped": True, "reason": "feature_disabled"}
        return {
            "headlines": [],
            "aggregate_sentiment": "neutral",
            "note": "Integrate a news provider and Gemini sentiment scoring.",
        }
