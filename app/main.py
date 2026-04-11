"""
FastAPI application entrypoint.

Run locally: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.messaging import AgentEventPublisher, get_event_publisher
from api.routes import health, transactions
from core.config import get_settings
from core.logging_config import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown hooks (DB pools, Kafka consumers, etc.)."""
    configure_logging(json_logs=get_settings().is_production)
    publisher: AgentEventPublisher = get_event_publisher()
    await publisher.start()
    try:
        yield
    finally:
        await publisher.stop()


def create_app() -> FastAPI:
    """Application factory for tests and ASGI servers."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name.replace("-", " ").title(),
        version="0.1.0",
        lifespan=lifespan,
    )
    origins = settings.cors_allow_origins
    # Browsers reject `credentials` with wildcard origins.
    allow_credentials = "*" not in origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router, prefix=settings.api_prefix)
    application.include_router(transactions.router, prefix=settings.api_prefix)
    return application


app = create_app()
