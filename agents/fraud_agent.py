"""Heuristic fraud and anomaly flags on transaction streams."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, BaseFinanceAgent
from core.config import get_settings


class FraudDetectionAgent(BaseFinanceAgent):
    name = "fraud_detection"

    async def run(self, context: AgentContext) -> dict[str, Any]:
        if not get_settings().enable_fraud_detection:
            return {"skipped": True, "reason": "feature_disabled"}
        return {
            "alerts": [],
            "notes": "Hook ML/rules on amount velocity, geo, and merchant mismatch (stub).",
        }
