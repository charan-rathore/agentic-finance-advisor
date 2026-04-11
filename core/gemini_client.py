"""
Gemini client wrapper (Google AI Studio).

Set `GEMINI_API_KEY` in `.env`. Without a key, helpers return safe placeholders
so local development does not require billing.
"""

from __future__ import annotations

from typing import Any

import google.generativeai as genai

from core.config import get_settings


def configure_genai() -> None:
    """Configure the global Gemini SDK from settings."""
    settings = get_settings()
    if settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)


def generate_text(prompt: str, **kwargs: Any) -> str:
    """
    Run a text generation with the configured model (blocking SDK call).

    For high concurrency, offload to a thread pool. Ground with `rag.vector_store`.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return "[Gemini disabled: set GEMINI_API_KEY] " + prompt[:200]
    configure_genai()
    model = genai.GenerativeModel(settings.gemini_model)
    response = model.generate_content(prompt, **kwargs)
    return getattr(response, "text", None) or str(response)
