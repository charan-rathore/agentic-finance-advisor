"""
CSV transaction ingestion (legacy v1 helper — not used by the v2 agent pipeline).

Wire this from a Kafka consumer or background task after `upload_transactions_csv`.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass
class ParsedRow:
    """Normalized row before ORM mapping."""

    txn_date: datetime
    amount: Decimal
    merchant: str | None
    category: str | None
    description: str | None


def parse_transaction_csv(content: bytes, encoding: str = "utf-8") -> list[dict[str, Any]]:
    """
    Parse CSV bytes into dict rows.

    Expects headers such as: date, amount, merchant, category, description.
    Adjust mapping to match your bank export format.
    """
    text = content.decode(encoding, errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        rows.append(dict(raw))
    return rows


def coerce_amount(value: str | None) -> Decimal | None:
    """Best-effort parse for currency strings."""
    if value is None or value == "":
        return None
    cleaned = value.strip().replace(",", "").replace("$", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
