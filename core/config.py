"""
Central configuration loaded from environment variables.

Uses pydantic-settings for validation and `.env` support in development.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; override via environment or `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="finance-advisor", alias="APP_NAME")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        alias="APP_ENV",
    )
    debug: bool = Field(default=False, alias="DEBUG")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")

    secret_key: str = Field(default="change-me", alias="SECRET_KEY")

    database_url: str = Field(
        default="postgresql+psycopg2://finance:finance@localhost:5432/finance_advisor",
        alias="DATABASE_URL",
    )

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        alias="KAFKA_BOOTSTRAP_SERVERS",
    )
    kafka_consumer_group: str = Field(
        default="finance-advisor-agents",
        alias="KAFKA_CONSUMER_GROUP",
    )
    kafka_topic_agent_events: str = Field(
        default="agent.events",
        alias="KAFKA_TOPIC_AGENT_EVENTS",
    )
    kafka_topic_transactions: str = Field(
        default="finance.transactions",
        alias="KAFKA_TOPIC_TRANSACTIONS",
    )

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")

    chroma_host: str = Field(default="localhost", alias="CHROMA_HOST")
    chroma_port: int = Field(default=8001, alias="CHROMA_PORT")
    chroma_collection: str = Field(
        default="finance_knowledge",
        alias="CHROMA_COLLECTION",
    )
    chroma_persist_dir: str = Field(default="./data/chroma", alias="CHROMA_PERSIST_DIR")

    fastapi_base_url: str = Field(
        default="http://localhost:8000",
        alias="FASTAPI_BASE_URL",
    )

    enable_fraud_detection: bool = Field(default=True, alias="ENABLE_FRAUD_DETECTION")
    enable_news_sentiment: bool = Field(default=True, alias="ENABLE_NEWS_SENTIMENT")

    # Comma-separated origins; use "*" for open dev only (not recommended in prod).
    cors_origins: str = Field(
        default="http://localhost:8501,http://127.0.0.1:8501",
        alias="CORS_ORIGINS",
    )

    @field_validator("secret_key")
    @classmethod
    def warn_weak_secret(cls, v: str) -> str:
        if v in ("change-me", "change-me-in-production"):
            # Do not raise in dev; production should override.
            pass
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_allow_origins(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton for dependency injection."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear settings cache (useful in tests)."""
    get_settings.cache_clear()
