"""tests/test_schemas.py — provenance envelope."""

from __future__ import annotations

import json
import unittest

from core.schemas import RawPayload


class TestRawPayload(unittest.TestCase):
    def test_build_populates_metadata(self) -> None:
        env = RawPayload.build(
            source="finnhub",
            endpoint="quote",
            symbol="AAPL",
            url="https://finnhub.io/api/v1/quote",
            params={"symbol": "AAPL"},
            payload={"quote": {"current": 270.23}},
        )
        self.assertEqual(env.source, "finnhub")
        self.assertEqual(env.endpoint, "quote")
        self.assertEqual(env.symbol, "AAPL")
        self.assertEqual(env.status, "ok")
        self.assertEqual(env.payload, {"quote": {"current": 270.23}})
        self.assertTrue(env.fetched_at.endswith("+00:00"))
        self.assertIsNotNone(env.request_hash)
        self.assertEqual(len(env.request_hash), 16)

    def test_request_hash_is_deterministic(self) -> None:
        a = RawPayload.build(source="x", endpoint="y", symbol="Z", params={"k": 1})
        b = RawPayload.build(source="x", endpoint="y", symbol="Z", params={"k": 1})
        self.assertEqual(a.request_hash, b.request_hash)

    def test_list_payload_is_wrapped(self) -> None:
        env = RawPayload.build(source="s", endpoint="e", payload=[1, 2, 3])
        self.assertEqual(env.payload, {"items": [1, 2, 3]})

    def test_round_trip_through_json(self) -> None:
        env = RawPayload.build(
            source="alpha_vantage",
            endpoint="OVERVIEW",
            symbol="AAPL",
            payload={"overview": {"Symbol": "AAPL", "MarketCap": "3T"}},
        )
        serialized = json.dumps(env.to_json_dict())
        restored = RawPayload.from_file_dict(json.loads(serialized))
        self.assertEqual(restored.source, "alpha_vantage")
        self.assertEqual(restored.symbol, "AAPL")
        self.assertEqual(restored.payload["overview"]["Symbol"], "AAPL")

    def test_from_file_dict_handles_legacy_flat_payload(self) -> None:
        """Old on-disk files lack source/endpoint/fetched_at; parser must not crash."""
        legacy = {"symbol": "AAPL", "quote": {"c": 270.0}}
        restored = RawPayload.from_file_dict(legacy)
        self.assertEqual(restored.symbol, "AAPL")
        self.assertEqual(restored.source, "unknown")


if __name__ == "__main__":
    unittest.main()
