import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "apps" / "web" / "data"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi.kalshi_senate_mapping import build_kalshi_us_senate_contest_index


REQUIRED_COLUMNS = {
    "kalshi_candidate_name",
    "ballotpedia_candidate_name",
    "ballotpedia_match_status",
    "ballotpedia_match_strategy",
    "ballotpedia_match_score",
    "ballotpedia_match_source",
    "ballotpedia_candidate_pool_key",
    "match_confidence_tier",
    "match_reason_code",
    "review_status",
    "candidate_name_kalshi",
    "candidate_name_ballotpedia",
    "market_ticker",
    "oddsPercent",
}


class KalshiCandidateNameMappingReportTests(unittest.TestCase):
    def _read_csv_rows(self, path: Path) -> List[Dict[str, str]]:
        self.assertTrue(path.exists(), msg=f"Missing artifact: {path}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def _assert_required_columns(self, rows: List[Dict[str, str]], artifact_name: str) -> None:
        self.assertGreater(len(rows), 0, msg=f"{artifact_name} should have rows")
        header = set(rows[0].keys())
        self.assertTrue(REQUIRED_COLUMNS.issubset(header), msg=f"{artifact_name} missing required columns")

    def _assert_statuses_valid(self, rows: List[Dict[str, str]], artifact_name: str) -> None:
        valid = {"matched", "unmatched", "ambiguous"}
        statuses = {str(row.get("ballotpedia_match_status") or "").strip() for row in rows}
        self.assertTrue(statuses.issubset(valid), msg=f"{artifact_name} has invalid statuses: {sorted(statuses - valid)}")

    def _assert_report_matches_rows(self, rows: List[Dict[str, str]], report: dict, report_key: str) -> None:
        block = report.get(report_key) or {}
        self.assertEqual(int(block.get("row_count") or 0), len(rows))

        matched = 0
        unmatched = 0
        ambiguous = 0
        pos_unmatched = 0
        pos_ambiguous = 0
        for row in rows:
            status = str(row.get("ballotpedia_match_status") or "").strip()
            try:
                odds = float(row.get("oddsPercent") or 0)
            except (TypeError, ValueError):
                odds = 0.0
            if status == "matched":
                matched += 1
            elif status == "ambiguous":
                ambiguous += 1
                if odds > 0:
                    pos_ambiguous += 1
            else:
                unmatched += 1
                if odds > 0:
                    pos_unmatched += 1

        self.assertEqual(int(block.get("matched_count") or 0), matched)
        self.assertEqual(int(block.get("unmatched_count") or 0), unmatched)
        self.assertEqual(int(block.get("ambiguous_count") or 0), ambiguous)
        self.assertEqual(int(block.get("positive_odds_unmatched_count") or 0), pos_unmatched)
        self.assertEqual(int(block.get("positive_odds_ambiguous_count") or 0), pos_ambiguous)
        self.assertIsInstance(block.get("tier_counts"), dict)
        self.assertIsInstance(block.get("threshold_tier_counts"), dict)
        self.assertIsInstance(block.get("per_seat_unresolved_counts"), dict)

    def test_senate_candidate_mapping_artifacts_and_report(self):
        winner_rows = self._read_csv_rows(DATA_DIR / "kalshi-senate-candidate-winner.csv")
        nominee_rows = self._read_csv_rows(DATA_DIR / "kalshi-senate-candidate-nominee.csv")
        self._assert_required_columns(winner_rows, "senate winner")
        self._assert_required_columns(nominee_rows, "senate nominee")
        self._assert_statuses_valid(winner_rows, "senate winner")
        self._assert_statuses_valid(nominee_rows, "senate nominee")

        report_path = DATA_DIR / "kalshi-senate-candidate-match-report.json"
        self.assertTrue(report_path.exists(), msg="Missing senate match report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self._assert_report_matches_rows(winner_rows, report, "candidate_winner")
        self._assert_report_matches_rows(nominee_rows, report, "candidate_nominee")

    def test_senate_known_name_variants_match_when_present(self):
        output_root = Path(tempfile.mkdtemp(prefix="kalshi_senate_match_test_", dir=str(REPO_ROOT / "tmp_test_runtime")))
        build_kalshi_us_senate_contest_index(
            output_json=output_root / "index.json",
            output_csv=output_root / "index.csv",
            output_violations_csv=output_root / "violations.csv",
            output_violations_json=output_root / "violations.json",
            output_candidate_winner_json=output_root / "winner.json",
            output_candidate_winner_csv=output_root / "winner.csv",
            output_party_winner_json=output_root / "party.json",
            output_party_winner_csv=output_root / "party.csv",
            output_candidate_nominee_json=output_root / "nominee.json",
            output_candidate_nominee_csv=output_root / "nominee.csv",
            output_excluded_csv=output_root / "excluded.csv",
            output_unmapped_csv=output_root / "unmapped.csv",
            output_ambiguous_csv=output_root / "ambiguous.csv",
            output_coverage_json=output_root / "coverage.json",
            output_candidate_match_report_json=output_root / "match_report.json",
            output_candidate_match_report_csv=output_root / "match_report.csv",
            strict=False,
        )
        winner_rows = self._read_csv_rows(output_root / "winner.csv")
        by_name = {str(row.get("kalshi_candidate_name") or "").strip(): row for row in winner_rows}

        if "Mary Peltola" in by_name:
            row = by_name["Mary Peltola"]
            self.assertEqual(str(row.get("ballotpedia_match_status") or "").strip(), "matched")
            self.assertEqual(str(row.get("ballotpedia_candidate_name") or "").strip(), "Mary Peltola")

        if "Dan Sullivan" in by_name:
            row = by_name["Dan Sullivan"]
            self.assertEqual(str(row.get("ballotpedia_match_status") or "").strip(), "matched")
            self.assertEqual(str(row.get("ballotpedia_candidate_name") or "").strip(), "Daniel S. Sullivan")

    def test_house_candidate_mapping_artifacts_and_report(self):
        winner_rows = self._read_csv_rows(DATA_DIR / "kalshi-house-candidate-winner.csv")
        nominee_rows = self._read_csv_rows(DATA_DIR / "kalshi-house-candidate-nominee.csv")
        self._assert_required_columns(winner_rows, "house winner")
        self._assert_required_columns(nominee_rows, "house nominee")
        self._assert_statuses_valid(winner_rows, "house winner")
        self._assert_statuses_valid(nominee_rows, "house nominee")

        report_path = DATA_DIR / "kalshi-house-candidate-match-report.json"
        self.assertTrue(report_path.exists(), msg="Missing house match report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self._assert_report_matches_rows(winner_rows, report, "candidate_winner")
        self._assert_report_matches_rows(nominee_rows, report, "candidate_nominee")


if __name__ == "__main__":
    unittest.main()
