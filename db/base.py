"""Legacy shim — declarative Base is defined in core.models (v2 SQLite schema)."""

from core.models import Base

__all__ = ["Base"]
