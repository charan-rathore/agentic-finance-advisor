"""Liveness and readiness endpoints."""

from fastapi import APIRouter

from api.schemas.common import MessageResponse
from core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=MessageResponse)
def health() -> MessageResponse:
    """Process is up."""
    return MessageResponse(message="ok")


@router.get("/ready", response_model=MessageResponse)
def ready() -> MessageResponse:
    """
    Dependency checks (extend with DB/Redis/Kafka pings).

    For the skeleton, returns ok when settings load.
    """
    _ = get_settings()
    return MessageResponse(message="ready")
