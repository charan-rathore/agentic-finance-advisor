"""Shared API schema types."""

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Generic status payload."""

    message: str = Field(..., examples=["ok"])
