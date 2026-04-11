"""Structured logging setup for API and workers."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(json_logs: bool = False) -> None:
    """Configure structlog and stdlib logging once per process."""
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_logs:
        processors = shared + [structlog.processors.JSONRenderer()]
    else:
        processors = shared + [structlog.dev.ConsoleRenderer(colors=True)]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
