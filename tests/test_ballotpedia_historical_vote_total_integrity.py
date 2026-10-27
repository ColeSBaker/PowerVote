import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.parser import (
    HISTORICAL_GENERAL_LOW_TOTAL_THRESHOLD,
    HISTORICAL_GENERAL_REQUIRED_YEARS,
    collect_historical_vote_total_violations,
    parse_all,
)
from tests.raw_data import requires_raw_data


@requires_raw_data
class BallotpediaHistoricalVoteTotalIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        cls.general_rows, _primary_rows, _runoff_rows, _ = parse_all(fixture_dir)

    def test_required_historical_general_vote_totals_exist_for_all_seats(self):
        violations = collect_historical_vote_total_violations(self.general_rows)
        missing = [item for item in violations if item.get("type") == "missing_historical_general_vote_total"]
        self.assertEqual([], missing, msg=f"Missing historical general vote totals: {missing[:25]}")

    def test_low_historical_general_vote_totals_fail_without_allowlist(self):
        violations = collect_historical_vote_total_violations(self.general_rows)
        low = [item for item in violations if item.get("type") == "low_historical_general_vote_total"]
        self.assertEqual([], low, msg=f"Unexpected low historical general vote totals: {low[:25]}")

    def test_violation_rows_include_required_debug_fields(self):
        rows = [
            {
                "seat": "ZZ-1",
                "historical_general_vote_totals": {"2024": 9000, "2022": 120000},
            }
        ]
        violations = collect_historical_vote_total_violations(
            rows,
            required_years=HISTORICAL_GENERAL_REQUIRED_YEARS,
            low_total_threshold=HISTORICAL_GENERAL_LOW_TOTAL_THRESHOLD,
            low_total_allowlist=set(),
        )
        self.assertGreater(len(violations), 0)
        for item in violations:
            for key in ("seat", "year", "value", "max_other_year", "reason", "type"):
                self.assertIn(key, item)


if __name__ == "__main__":
    unittest.main()
