"""
core/schemas.py

Pydantic models that define the on-disk shape of every raw payload we fetch.

Goal: every file under `data/raw/` carries the same provenance fields so the
wiki-ingest layer (and any future audit tool) can trust them:

    {
      "source":       "finnhub" | "alpha_vantage" | "sec" | "fred" | "google_news" | ...
      "endpoint":     str,          # API path or logical name (e.g. "quote", "OVERVIEW")
      "symbol":       str | None,   # set when the payload is per-ticker
      "fetched_at":   ISO-8601 UTC timestamp
      "url":          str | None,   # resolved request URL, if known
      "request_hash": str | None,   # sha256 of (source,endpoint,symbol,params)
      "status":       "ok" | "error" | "rate_limited" | "empty"
      "payload":      {...}         # the actual data
    }

Why Pydantic?  Three reasons:
  1. One-line validation when reading raw files back.
  2. Docstring-as-contract — new contributors can see exactly which fields
     every file must carry.
  3. `.model_dump()` gives us canonical JSON that our clients all agree on.

This sits beside (not inside) the API clients so the clients can be imported
without pulling in Pydantic at call time.  Clients call `RawPayload.build(...)`
as a factory and then `.to_json_dict()` to serialize.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PayloadStatus = Literal["ok", "error", "rate_limited", "empty"]


class RawPayload(BaseModel):
    """Canonical envelope for anything written to `data/raw/`."""

    source: str = Field(..., description="Logical data source name (e.g. 'finnhub').")
    endpoint: str = Field(..., description="API path or logical endpoint name.")
    symbol: str | None = Field(default=None, description="Ticker if per-symbol.")
    fetched_at: str = Field(..., description="ISO-8601 UTC timestamp.")
    url: str | None = Field(default=None, description="Resolved request URL.")
    request_hash: str | None = Field(
        default=None,
        description="Deterministic hash of (source,endpoint,symbol,params).",
    )
    status: PayloadStatus = Field(default="ok")
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        source: str,
        endpoint: str,
        payload: dict[str, Any] | list[Any] | None = None,
        symbol: str | None = None,
        url: str | None = None,
        params: dict[str, Any] | None = None,
        status: PayloadStatus = "ok",
    ) -> RawPayload:
        """
        Factory that fills in `fetched_at` and `request_hash` for you.

        Accepts `payload` as dict *or* list; list payloads are wrapped under
        the `"items"` key so the schema stays dict-shaped on disk.
        """
        body: dict[str, Any]
        if payload is None:
            body = {}
        elif isinstance(payload, list):
            body = {"items": payload}
        else:
            body = payload

        hash_seed = json.dumps(
            {"s": source, "e": endpoint, "sym": symbol, "p": params or {}},
            sort_keys=True,
            default=str,
        )
        request_hash = hashlib.sha256(hash_seed.encode()).hexdigest()[:16]

        return cls(
            source=source,
            endpoint=endpoint,
            symbol=symbol,
            fetched_at=datetime.now(UTC).isoformat(),
            url=url,
            request_hash=request_hash,
            status=status,
            payload=body,
        )

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (what goes on disk)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_file_dict(cls, data: dict[str, Any]) -> RawPayload:
        """
        Reverse adapter.  Handles our pre-provenance payloads gracefully by
        filling in reasonable defaults so legacy files keep routing through
        wiki_ingest without exceptions.
        """
        if "source" not in data:
            data = {**data, "source": data.get("source", "unknown")}
        if "endpoint" not in data:
            data = {**data, "endpoint": data.get("endpoint", "")}
        if "fetched_at" not in data:
            data = {
                **data,
                "fetched_at": data.get("fetched_at", datetime.now(UTC).isoformat()),
            }
        # Anything not in our canonical field list becomes the payload.
        known = {
            "source",
            "endpoint",
            "symbol",
            "fetched_at",
            "url",
            "request_hash",
            "status",
            "payload",
        }
        leftover = {k: v for k, v in data.items() if k not in known}
        if leftover and "payload" not in data:
            data = {**data, "payload": leftover}
        return cls.model_validate(data)
