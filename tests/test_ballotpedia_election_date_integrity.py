import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.parser import parse_all
from tests.raw_data import requires_raw_data


def _parse_date(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


@requires_raw_data
class BallotpediaElectionDateIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        cls.general_rows, cls.primary_rows, cls.runoff_rows, _ = parse_all(fixture_dir)
        override = os.environ.get("POWERVOTE_VALIDATION_DATE", "").strip()
        cls.validation_date = datetime.strptime(override, "%Y-%m-%d").date() if override else date.today()

    def test_primary_votes_require_past_or_present_primary_date(self):
        errors = []
        for row in self.primary_rows:
            total_votes = row.get("primary_vote_total")
            if total_votes in (None, "", 0, "0"):
                continue
            try:
                if float(total_votes) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            primary_date = _parse_date(str(row.get("primary_date") or ""))
            if primary_date is None or primary_date > self.validation_date:
                errors.append((row.get("primary_id"), row.get("seat"), total_votes, row.get("primary_date")))
        self.assertEqual(errors, [], msg=f"Primary rows with votes before election date validation: {errors[:40]}")

    def test_runoff_votes_require_past_or_present_runoff_date(self):
        errors = []
        for row in self.runoff_rows:
            total_votes = row.get("primary_vote_total")
            if total_votes in (None, "", 0, "0"):
                continue
            try:
                if float(total_votes) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            runoff_date = _parse_date(str(row.get("runoff_date") or ""))
            if runoff_date is None or runoff_date > self.validation_date:
                errors.append((row.get("primary_id"), row.get("seat"), total_votes, row.get("runoff_date")))
        self.assertEqual(errors, [], msg=f"Runoff rows with votes before election date validation: {errors[:40]}")

    def test_general_votes_require_past_or_present_general_date(self):
        errors = []
        for row in self.general_rows:
            total_votes = row.get("general_vote_total")
            if total_votes in (None, "", 0, "0"):
                continue
            try:
                if float(total_votes) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            general_date = _parse_date(str(row.get("general_date") or ""))
            if general_date is None or general_date > self.validation_date:
                errors.append((row.get("seat"), total_votes, row.get("general_date")))
        self.assertEqual(errors, [], msg=f"General rows with votes before election date validation: {errors[:40]}")

    def test_fl1_regression_guardrails(self):
        fl1_r = next(row for row in self.primary_rows if row.get("primary_id") == "FL-1-R-primary-2026")
        self.assertEqual((fl1_r.get("status") or "").strip(), "upcoming")
        self.assertIn("2026-08-18", str(fl1_r.get("primary_date") or ""))
        self.assertNotIn("Matt Gaetz", list(fl1_r.get("candidates") or []))
        total_votes = fl1_r.get("primary_vote_total")
        self.assertTrue(total_votes in (None, "", 0, "0"))


if __name__ == "__main__":
    unittest.main()
