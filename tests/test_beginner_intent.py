"""tests/test_beginner_intent.py — rule-based onboarding intent detector."""

from __future__ import annotations

import unittest

from core.wiki import detect_beginner_intent


class TestBeginnerIntent(unittest.TestCase):
    def test_matches_classic_beginner_phrases(self) -> None:
        cases = [
            "How do I get started and where should I invest?",
            "I'm new to investing, can you help?",
            "I know nothing about finance, please teach me",
            "Explain the basics of the stock market",
            "First time investor here — what do I do?",
            "What is a stock?",
            "What are bonds and how do they work?",
            "What is an ETF?",
            "How does the stock market work?",
            "I'm completely new, just starting out",
        ]
        for q in cases:
            self.assertTrue(
                detect_beginner_intent(q),
                msg=f"Expected beginner intent for: {q!r}",
            )

    def test_does_not_fire_on_specific_market_questions(self) -> None:
        cases = [
            "What's AAPL trading at right now?",
            "Summarise the last 10-K for NVDA",
            "How did the S&P close yesterday?",
            "Compare JPM vs V over the last quarter",
        ]
        for q in cases:
            self.assertFalse(
                detect_beginner_intent(q),
                msg=f"Did not expect beginner intent for: {q!r}",
            )


if __name__ == "__main__":
    unittest.main()
