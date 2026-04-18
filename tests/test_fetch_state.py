"""tests/test_fetch_state.py — SQLite-backed fetch cadence tracker."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from core.fetch_state import (
    record_attempt,
    record_failure,
    record_success,
    should_fetch,
)
from core.models import FetchRun, init_db


class TestFetchState(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = init_db("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)

    def test_should_fetch_true_when_no_prior_run(self) -> None:
        with self.Session() as s:
            self.assertTrue(should_fetch(s, "finnhub", interval_hours=1))

    def test_should_fetch_false_right_after_success(self) -> None:
        with self.Session() as s:
            record_success(s, "finnhub", content_hash="abc")
            self.assertFalse(should_fetch(s, "finnhub", interval_hours=1))

    def test_should_fetch_true_when_interval_elapsed(self) -> None:
        with self.Session() as s:
            record_success(s, "sec")
            # Manually age the row.
            row = s.query(FetchRun).filter_by(source="sec").one()
            row.last_success_at = datetime.utcnow() - timedelta(hours=48)
            s.commit()
            self.assertTrue(should_fetch(s, "sec", interval_hours=24))

    def test_record_failure_does_not_clear_last_success(self) -> None:
        with self.Session() as s:
            record_success(s, "fred", content_hash="123")
            record_failure(s, "fred", error="rate-limited")
            row = s.query(FetchRun).filter_by(source="fred").one()
            self.assertIsNotNone(row.last_success_at)
            self.assertEqual(row.last_error, "rate-limited")

    def test_record_attempt_creates_row_if_missing(self) -> None:
        with self.Session() as s:
            record_attempt(s, "alpha_vantage")
            row = s.query(FetchRun).filter_by(source="alpha_vantage").one()
            self.assertIsNotNone(row.last_attempt_at)
            self.assertIsNone(row.last_success_at)


if __name__ == "__main__":
    unittest.main()
