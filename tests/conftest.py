"""Pytest fixtures and path setup."""

from __future__ import annotations

import pytest

from core.config import reset_settings_cache


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    """Isolate settings cache between tests."""
    reset_settings_cache()
    yield
    reset_settings_cache()
