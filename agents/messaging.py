"""
Kafka publishing for agent coordination.

If the broker is unavailable (typical in local dev without Docker), publishes
degrade to structured logs so the API remains responsive.
"""

from __future__ import annotations

from typing import Any

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

from core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class AgentEventPublisher:
    """Thin async wrapper around AIOKafkaProducer with lazy startup."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._producer: AIOKafkaProducer | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._settings.kafka_bootstrap_servers,
                client_id=self._settings.app_name,
            )
            await self._producer.start()
            self._started = True
            logger.info("kafka_producer_started")
        except (KafkaConnectionError, OSError, ValueError) as exc:
            logger.warning("kafka_producer_unavailable", error=str(exc))
            self._producer = None
            self._started = False

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
        self._started = False

    async def publish(self, topic: str, key: bytes | None, value: bytes) -> None:
        await self.start()
        if self._producer is None:
            logger.info(
                "kafka_publish_skipped",
                topic=topic,
                key=key.decode() if key else None,
                value_preview=value[:200].decode(errors="replace"),
            )
            return
        await self._producer.send_and_wait(topic, value=value, key=key)


_publisher_singleton: AgentEventPublisher | None = None


def get_event_publisher() -> Any:
    """
    FastAPI dependency: returns a process-level publisher.

    Uses Any return type to avoid importing FastAPI types here.
    """
    global _publisher_singleton
    if _publisher_singleton is None:
        _publisher_singleton = AgentEventPublisher()
    return _publisher_singleton
