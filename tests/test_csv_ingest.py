"""Unit tests for CSV helpers."""

from __future__ import annotations

from decimal import Decimal

from services.csv_ingest import coerce_amount, parse_transaction_csv


def test_parse_csv_basic() -> None:
    raw = b"date,amount,merchant\n2024-01-01,12.50,Coffee Shop\n"
    rows = parse_transaction_csv(raw)
    assert len(rows) == 1
    assert rows[0]["merchant"] == "Coffee Shop"


def test_coerce_amount() -> None:
    assert coerce_amount("$1,234.50") == Decimal("1234.50")
