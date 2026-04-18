"""tests/test_wiki_ingest.py — routing + envelope compatibility."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import wiki_ingest
from core.schemas import RawPayload


class _FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeGeminiModel:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_content_async(self, prompt: str):
        self.calls.append(prompt)
        return _FakeGeminiResponse("FAKE ANALYSIS")


class TestRouter(unittest.TestCase):
    """process_all_new_raw_files picks the right handler by prefix."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.wiki = self.tmp / "wiki"
        (self.raw).mkdir()
        (self.wiki / "stocks").mkdir(parents=True)
        (self.wiki / "concepts").mkdir()

        self._patches = [
            patch.object(wiki_ingest.settings, "RAW_DATA_DIR", str(self.raw)),
            patch.object(wiki_ingest.settings, "WIKI_DIR", str(self.wiki)),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, data: dict) -> Path:
        path = self.raw / name
        path.write_text(json.dumps(data))
        return path

    def test_alpha_vantage_file_is_routed_with_new_envelope(self) -> None:
        env = RawPayload.build(
            source="alpha_vantage",
            endpoint="GLOBAL_QUOTE",
            symbol="AAPL",
            payload={"quote": {"05. price": "270.23"}},
        )
        self._write("alphavantage_quote_AAPL_20260418.json", env.to_json_dict())

        fake = _FakeGeminiModel()
        with (
            patch.object(wiki_ingest, "_get_gemini_model", return_value=fake),
            patch.object(wiki_ingest, "_update_wiki_index", AsyncMock()),
        ):
            count = asyncio.run(wiki_ingest.process_all_new_raw_files())

        self.assertGreaterEqual(count, 1)
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("GLOBAL_QUOTE", fake.calls[0])
        self.assertTrue((self.wiki / "stocks" / "AAPL.md").exists())

    def test_finnhub_file_is_routed(self) -> None:
        env = RawPayload.build(
            source="finnhub",
            endpoint="quote",
            symbol="MSFT",
            payload={"quote": {"current": 420.0, "percent_change": 1.1}},
        )
        self._write("finnhub_quote_MSFT_20260418.json", env.to_json_dict())

        fake = _FakeGeminiModel()
        with (
            patch.object(wiki_ingest, "_get_gemini_model", return_value=fake),
            patch.object(wiki_ingest, "_update_wiki_index", AsyncMock()),
        ):
            count = asyncio.run(wiki_ingest.process_all_new_raw_files())

        self.assertGreaterEqual(count, 1)
        self.assertIn("Finnhub quote", fake.calls[0])

    def test_unknown_file_is_skipped_not_crashed(self) -> None:
        self._write("totally_unknown_AAPL.json", {"foo": "bar"})

        with patch.object(wiki_ingest, "_update_wiki_index", AsyncMock()):
            count = asyncio.run(wiki_ingest.process_all_new_raw_files())

        # Unknown types log a debug line but don't raise; count will reflect it.
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
