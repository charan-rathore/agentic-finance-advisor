#!/usr/bin/env python3
"""
Minimal Kafka consumer for local debugging (prints messages).

Usage (from project root, with infra up):

  PYTHONPATH=. python scripts/kafka_print_consumer.py agent.events
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from aiokafka import AIOKafkaConsumer

from core.config import get_settings


async def run(topic: str) -> None:
    settings = get_settings()
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{settings.kafka_consumer_group}-debug",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for msg in consumer:
            try:
                payload = json.loads(msg.value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = msg.value
            print(topic, msg.partition, msg.offset, payload, flush=True)
    finally:
        await consumer.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "topic",
        nargs="?",
        default=get_settings().kafka_topic_agent_events,
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.topic))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
