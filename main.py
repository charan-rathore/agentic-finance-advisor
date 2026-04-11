"""
main.py

Entry point for the multi-agent finance advisor.

Starts all 3 agents as concurrent asyncio tasks:
  - ingest_agent:   fetches data every INGEST_INTERVAL_SECONDS
  - analysis_agent: processes data every ANALYSIS_INTERVAL_SECONDS
  - storage_agent:  saves insights to SQLite as they arrive

All agents share the same async queues (defined in core/queues.py).
They run concurrently in a single process — no inter-process communication needed.

To run locally:  python main.py
In Docker:       CMD ["python", "main.py"]  (see Dockerfile)
"""

import asyncio

from loguru import logger

from core.settings import settings

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    level=settings.LOG_LEVEL,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
)


async def main():
    """Launch all agents as concurrent async tasks."""
    from agents.analysis_agent import run as analysis_run
    from agents.ingest_agent import run as ingest_run
    from agents.storage_agent import run as storage_run

    logger.info("=" * 60)
    logger.info("  Multi-Agent Finance Advisor starting")
    logger.info(f"  Ingest interval:   {settings.INGEST_INTERVAL_SECONDS}s")
    logger.info(f"  Analysis interval: {settings.ANALYSIS_INTERVAL_SECONDS}s")
    logger.info(f"  Gemini model:      {settings.GEMINI_MODEL} (free tier)")
    logger.info("=" * 60)

    tasks = [
        asyncio.create_task(ingest_run(), name="ingest_agent"),
        asyncio.create_task(analysis_run(), name="analysis_agent"),
        asyncio.create_task(storage_run(), name="storage_agent"),
    ]

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    for task in done:
        if task.exception():
            logger.error(f"Task '{task.get_name()}' crashed: {task.exception()}")

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.error("All agents stopped. Check logs above for the cause.")


if __name__ == "__main__":
    asyncio.run(main())
