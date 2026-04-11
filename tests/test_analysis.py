"""tests/test_analysis.py — tests for analysis agent helpers."""

from __future__ import annotations

import unittest

from agents.analysis_agent import analyze_sentiment, build_prompt


class TestAnalysisAgent(unittest.TestCase):
    def test_build_prompt_includes_question(self) -> None:
        """Prompt builder embeds the user question."""
        prompt = build_prompt("Test question?", [], [], [])
        self.assertIn("Test question?", prompt)
        self.assertIn("CURRENT STOCK PRICES:", prompt)

    def test_sentiment_label_ranges(self) -> None:
        """Sentiment labels map correctly to polarity score ranges."""
        self.assertEqual(analyze_sentiment("amazing profit boom")[0], "positive")
        self.assertEqual(analyze_sentiment("terrible crash disaster")[0], "negative")
        self.assertEqual(analyze_sentiment("the market was open today")[0], "neutral")

    def test_analyze_sentiment_negative(self) -> None:
        label, score = analyze_sentiment("massive losses and bankruptcy fears")
        self.assertEqual(label, "negative")
        self.assertLess(score, 0.0)


if __name__ == "__main__":
    unittest.main()
