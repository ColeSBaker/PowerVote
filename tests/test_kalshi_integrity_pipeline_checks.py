import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.kalshi_integrity import (
    INTEGRITY_ISSUES,
    evaluate_kalshi_row_integrity,
    issue_column_name,
)
from ballotpedia_rollup.parser import parse_all
from tests.raw_data import requires_raw_data


@requires_raw_data
class KalshiIntegrityPipelineChecksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        cls.general_rows, cls.primary_rows, cls.runoff_rows, _ = parse_all(fixture_dir)

    def test_evaluate_kalshi_row_integrity_flags_out_of_band_sum(self):
        row = {
            "kalshi_general_odds_map": {"Democratic Party": 55.0, "Republican Party": 25.0},
            "kalshi_join_audit": {"sum_status": "out_of_band", "odds_map_sum": 80.0},
        }
        result = evaluate_kalshi_row_integrity(row, row_type="general")
        self.assertFalse(result.passed)
        self.assertIn("odds_map_sum_out_of_band", result.issues)

    def test_parse_all_rows_include_split_integrity_issue_columns(self):
        self.assertGreater(len(self.general_rows), 0)
        issue_columns = [issue_column_name(issue) for issue in INTEGRITY_ISSUES]
        for row, row_type in [
            *[(item, "general") for item in self.general_rows],
            *[(item, "primary") for item in self.primary_rows],
            *[(item, "runoff") for item in self.runoff_rows],
        ]:
            self.assertIn("kalshi_integrity_passed", row)
            self.assertIn("kalshi_integrity_status", row)
            self.assertIn("kalshi_integrity_issue_count", row)
            self.assertNotIn("kalshi_integrity_issues", row)
            for column in issue_columns:
                self.assertIn(column, row)
                self.assertIsInstance(row[column], bool)

            evaluated = evaluate_kalshi_row_integrity(row, row_type=row_type)
            self.assertEqual(row["kalshi_integrity_passed"], evaluated.passed)
            self.assertEqual(row["kalshi_integrity_status"], evaluated.status)
            self.assertEqual(row["kalshi_integrity_issue_count"], len(evaluated.issues))
            for issue in INTEGRITY_ISSUES:
                self.assertEqual(row[issue_column_name(issue)], issue in evaluated.issues)


if __name__ == "__main__":
    unittest.main()
