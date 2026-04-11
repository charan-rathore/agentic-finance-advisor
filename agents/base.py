"""Abstract base for all finance agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AgentContext(dict):
    """Lightweight bag for user id, time range, and optional RAG hits."""

    @property
    def user_external_id(self) -> str:
        return str(self["user_external_id"])


class BaseFinanceAgent(ABC):
    """Shared interface so the orchestrator can invoke agents uniformly."""

    name: str = "base"

    @abstractmethod
    async def run(self, context: AgentContext) -> dict[str, Any]:
        """Execute agent logic and return a structured result dict."""

    async def safe_run(self, context: AgentContext) -> dict[str, Any]:
        """Run with logging and soft failure for multi-agent pipelines."""
        try:
            result = await self.run(context)
            logger.info("agent_completed", agent=self.name, user=context.user_external_id)
            return {"agent": self.name, "ok": True, **result}
        except Exception as exc:  # noqa: BLE001 — boundary for agent isolation
            logger.exception("agent_failed", agent=self.name, error=str(exc))
            return {"agent": self.name, "ok": False, "error": str(exc)}
