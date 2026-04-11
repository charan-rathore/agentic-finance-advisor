"""
Coordinates multiple agents for a single user request or event.

Publishes high-level outcomes to Kafka for asynchronous consumers (dashboards,
notifications, audit logs).
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy.orm import Session

from agents.base import AgentContext
from agents.budget_agent import BudgetAgent
from agents.expense_agent import ExpenseAnalysisAgent
from agents.explanation_agent import FinancialExplanationAgent
from agents.fraud_agent import FraudDetectionAgent
from agents.investment_agent import InvestmentInsightsAgent
from agents.messaging import AgentEventPublisher
from agents.news_agent import NewsSentimentAgent
from core.config import get_settings

logger = structlog.get_logger(__name__)


class FinanceOrchestrator:
    """Runs agents sequentially; swap to graph/planner pattern as complexity grows."""

    def __init__(self, db: Session, publisher: AgentEventPublisher) -> None:
        self._db = db
        self._publisher = publisher
        self._agents: list[Any] = [
            ExpenseAnalysisAgent(),
            BudgetAgent(),
            InvestmentInsightsAgent(),
            FraudDetectionAgent(),
            NewsSentimentAgent(),
            FinancialExplanationAgent(),
        ]

    async def on_csv_uploaded(self, payload: dict[str, Any]) -> None:
        """React to a new CSV upload event."""
        logger.info("csv_upload_pipeline", payload=payload)
        settings = get_settings()
        await self._publisher.publish(
            settings.kafka_topic_agent_events,
            key=payload.get("user_external_id", "unknown").encode(),
            value=json.dumps({"event": "csv_uploaded", **payload}).encode(),
        )

    async def run_sample_pipeline(self, user_external_id: str) -> str:
        """Execute all agents for smoke testing and demo dashboards."""
        ctx = AgentContext(user_external_id=user_external_id, topic="emergency fund")
        results: list[dict[str, Any]] = []
        for agent in self._agents:
            results.append(await agent.safe_run(ctx))
        logger.info("pipeline_finished", user=user_external_id, steps=len(results))
        ok = sum(1 for r in results if r.get("ok"))
        return f"Agents completed: {ok}/{len(results)} succeeded (see logs for details)."
