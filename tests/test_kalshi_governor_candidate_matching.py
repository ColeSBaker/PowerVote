"""Integration tests for Governor & Lt-Governor Kalshi ↔ Ballotpedia candidate matching.

These read the *real* output files from apps/web/data/ (no fixtures).
They are "canary" tests — if a market stops matching, these fail.
"""
from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "apps" / "web" / "data"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

REQUIRED_CANDIDATE_COLS = {
    "market_ticker",
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
    "seat",
    "round",
    "party",
    "oddsPercent",
    "office",
}
VALID_STATUSES = {"matched", "unmatched", "ambiguous"}
VALID_TIERS = {"A", "B", "C", "D"}


class _CandidateMatchingMixin:
    """Shared helpers for governor and lt-governor matching tests."""

    def _read_csv_rows(self, path: Path) -> List[Dict[str, str]]:
        self.assertTrue(path.exists(), msg=f"Missing artifact: {path}")  # type: ignore[attr-defined]
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def _assert_required_columns(self, rows: List[Dict[str, str]], artifact_name: str) -> None:
        self.assertGreater(len(rows), 0, msg=f"{artifact_name} should have rows")  # type: ignore[attr-defined]
        header = set(rows[0].keys())
        missing = REQUIRED_CANDIDATE_COLS - header
        self.assertFalse(missing, msg=f"{artifact_name} missing columns: {sorted(missing)}")  # type: ignore[attr-defined]

    def _assert_statuses_valid(self, rows: List[Dict[str, str]], artifact_name: str) -> None:
        statuses = {str(row.get("ballotpedia_match_status") or "").strip() for row in rows}
        invalid = statuses - VALID_STATUSES
        self.assertFalse(invalid, msg=f"{artifact_name} has invalid statuses: {sorted(invalid)}")  # type: ignore[attr-defined]

    def _assert_tiers_valid(self, rows: List[Dict[str, str]], artifact_name: str) -> None:
        tiers = {str(row.get("match_confidence_tier") or "").strip() for row in rows}
        invalid = tiers - VALID_TIERS
        self.assertFalse(invalid, msg=f"{artifact_name} has invalid tiers: {sorted(invalid)}")  # type: ignore[attr-defined]

    def _assert_report_matches_rows(self, rows: List[Dict[str, str]], report: dict, report_key: str) -> None:
        block = report.get(report_key) or {}
        self.assertEqual(int(block.get("row_count") or 0), len(rows))  # type: ignore[attr-defined]

        matched = unmatched = ambiguous = 0
        pos_unmatched = pos_ambiguous = 0
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

        self.assertEqual(int(block.get("matched_count") or 0), matched)  # type: ignore[attr-defined]
        self.assertEqual(int(block.get("unmatched_count") or 0), unmatched)  # type: ignore[attr-defined]
        self.assertEqual(int(block.get("ambiguous_count") or 0), ambiguous)  # type: ignore[attr-defined]
        self.assertEqual(int(block.get("positive_odds_unmatched_count") or 0), pos_unmatched)  # type: ignore[attr-defined]
        self.assertEqual(int(block.get("positive_odds_ambiguous_count") or 0), pos_ambiguous)  # type: ignore[attr-defined]
        self.assertIsInstance(block.get("tier_counts"), dict)  # type: ignore[attr-defined]
        self.assertIsInstance(block.get("threshold_tier_counts"), dict)  # type: ignore[attr-defined]
        self.assertIsInstance(block.get("per_seat_unresolved_counts"), dict)  # type: ignore[attr-defined]


# ===========================================================================
# Governor matching tests
# ===========================================================================

class KalshiGovernorCandidateMatchingTests(_CandidateMatchingMixin, unittest.TestCase):

    # -----------------------------------------------------------------------
    # CSV column validation
    # -----------------------------------------------------------------------

    def test_governor_candidate_winner_csv_columns(self) -> None:
        rows = self._read_csv_rows(DATA_DIR / "kalshi-governor-candidate-winner.csv")
        self._assert_required_columns(rows, "governor winner")

    def test_governor_candidate_nominee_csv_columns(self) -> None:
        rows = self._read_csv_rows(DATA_DIR / "kalshi-governor-candidate-nominee.csv")
        self._assert_required_columns(rows, "governor nominee")

    # -----------------------------------------------------------------------
    # Status / tier validation
    # -----------------------------------------------------------------------

    def test_governor_match_statuses_valid(self) -> None:
        for name in ("kalshi-governor-candidate-winner.csv", "kalshi-governor-candidate-nominee.csv"):
            rows = self._read_csv_rows(DATA_DIR / name)
            self._assert_statuses_valid(rows, name)

    def test_governor_match_tiers_valid(self) -> None:
        for name in ("kalshi-governor-candidate-winner.csv", "kalshi-governor-candidate-nominee.csv"):
            rows = self._read_csv_rows(DATA_DIR / name)
            self._assert_tiers_valid(rows, name)

    # -----------------------------------------------------------------------
    # Match report structure & reconciliation
    # -----------------------------------------------------------------------

    def test_governor_match_report_keys_present(self) -> None:
        report_path = DATA_DIR / "kalshi-governor-candidate-match-report.json"
        self.assertTrue(report_path.exists(), msg="Missing governor match report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for key in ("office", "blocking_issue_count", "candidate_winner", "candidate_nominee", "top_unresolved_examples"):
            self.assertIn(key, report, msg=f"Missing key '{key}' in governor match report")

    def test_governor_report_counts_match_csv_winner(self) -> None:
        winner_rows = self._read_csv_rows(DATA_DIR / "kalshi-governor-candidate-winner.csv")
        report = json.loads((DATA_DIR / "kalshi-governor-candidate-match-report.json").read_text(encoding="utf-8"))
        self._assert_report_matches_rows(winner_rows, report, "candidate_winner")

    def test_governor_report_counts_match_csv_nominee(self) -> None:
        nominee_rows = self._read_csv_rows(DATA_DIR / "kalshi-governor-candidate-nominee.csv")
        report = json.loads((DATA_DIR / "kalshi-governor-candidate-match-report.json").read_text(encoding="utf-8"))
        self._assert_report_matches_rows(nominee_rows, report, "candidate_nominee")

    def test_governor_unresolved_examples_have_required_fields(self) -> None:
        report = json.loads((DATA_DIR / "kalshi-governor-candidate-match-report.json").read_text(encoding="utf-8"))
        required = {"market_ticker", "seat", "kalshi_candidate_name", "oddsPercent", "ballotpedia_match_status", "match_confidence_tier"}
        for example in report.get("top_unresolved_examples") or []:
            missing = required - set(example.keys())
            self.assertFalse(missing, msg=f"Unresolved example missing fields: {sorted(missing)}")

    # -----------------------------------------------------------------------
    # Party winner / candidate winner separation
    # -----------------------------------------------------------------------

    def test_governor_no_candidate_in_party_winner(self) -> None:
        """Party-winner CSV should only have party entities, not individual candidates."""
        path = DATA_DIR / "kalshi-governor-party-winner.csv"
        if not path.exists():
            self.skipTest("kalshi-governor-party-winner.csv not found")
        rows = self._read_csv_rows(path)
        party_entities = {"democratic party", "republican party", "democratic", "republican"}
        for row in rows:
            entity = str(row.get("entityName") or row.get("yes_sub_title") or "").strip().lower()
            mtype = str(row.get("market_type") or "").strip()
            if mtype == "party_winner" and entity and entity not in party_entities:
                self.fail(f"Individual candidate '{entity}' found in party_winner CSV (ticker={row.get('market_ticker')})")

    def test_governor_mike_duggan_in_candidate_winner(self) -> None:
        winner_rows = self._read_csv_rows(DATA_DIR / "kalshi-governor-candidate-winner.csv")
        winner_tickers = {str(row.get("market_ticker") or "").strip() for row in winner_rows}
        self.assertIn("GOVPARTYMI-26-MD", winner_tickers, msg="Mike Duggan (GOVPARTYMI-26-MD) should be in candidate-winner")

        party_path = DATA_DIR / "kalshi-governor-party-winner.csv"
        if party_path.exists():
            party_rows = self._read_csv_rows(party_path)
            party_tickers = {str(row.get("market_ticker") or "").strip() for row in party_rows}
            self.assertNotIn("GOVPARTYMI-26-MD", party_tickers, msg="Mike Duggan should NOT be in party-winner")

    # -----------------------------------------------------------------------
    # Coverage summary
    # -----------------------------------------------------------------------

    def test_governor_coverage_summary_structure(self) -> None:
        path = DATA_DIR / "kalshi-governor-coverage-summary.json"
        self.assertTrue(path.exists(), msg="Missing governor coverage summary")
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("counts", "byRound", "byMarketType"):
            self.assertIn(key, data, msg=f"Missing key '{key}' in coverage summary")
        self.assertGreater(data["counts"].get("general_contests", 0), 0, msg="Expected at least 1 general contest")

    # -----------------------------------------------------------------------
    # Violations file
    # -----------------------------------------------------------------------

    def test_governor_violations_file_parseable(self) -> None:
        path = DATA_DIR / "kalshi-us-governor-contest-integrity-violations.json"
        self.assertTrue(path.exists(), msg="Missing governor violations JSON")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("count", data)
        self.assertIn("violations", data)
        self.assertIsInstance(data["violations"], list)

    # -----------------------------------------------------------------------
    # Unmatched threshold canary
    # -----------------------------------------------------------------------

    def test_governor_unmatched_markets_above_threshold_in_report(self) -> None:
        report = json.loads((DATA_DIR / "kalshi-governor-candidate-match-report.json").read_text(encoding="utf-8"))
        examples = report.get("top_unresolved_examples") or []
        high_odds = [e for e in examples if float(e.get("oddsPercent") or 0) > 2.0]
        if high_odds:
            for section_key in ("candidate_winner", "candidate_nominee"):
                block = report.get(section_key) or {}
                per_seat = block.get("per_seat_unresolved_counts") or {}
                if per_seat:
                    return
            self.fail(
                f"Found {len(high_odds)} unresolved examples above 2% odds "
                f"but no per_seat_unresolved_counts in report"
            )


# ===========================================================================
# Lt-Governor matching tests
# ===========================================================================

class KalshiLtGovCandidateMatchingTests(_CandidateMatchingMixin, unittest.TestCase):

    # -----------------------------------------------------------------------
    # CSV column validation
    # -----------------------------------------------------------------------

    def test_ltgov_candidate_winner_csv_columns(self) -> None:
        rows = self._read_csv_rows(DATA_DIR / "kalshi-lt-governor-candidate-winner.csv")
        self._assert_required_columns(rows, "lt-governor winner")

    def test_ltgov_candidate_nominee_csv_columns(self) -> None:
        rows = self._read_csv_rows(DATA_DIR / "kalshi-lt-governor-candidate-nominee.csv")
        self._assert_required_columns(rows, "lt-governor nominee")

    # -----------------------------------------------------------------------
    # Status / tier validation
    # -----------------------------------------------------------------------

    def test_ltgov_match_statuses_valid(self) -> None:
        for name in ("kalshi-lt-governor-candidate-winner.csv", "kalshi-lt-governor-candidate-nominee.csv"):
            rows = self._read_csv_rows(DATA_DIR / name)
            self._assert_statuses_valid(rows, name)

    def test_ltgov_match_tiers_valid(self) -> None:
        for name in ("kalshi-lt-governor-candidate-winner.csv", "kalshi-lt-governor-candidate-nominee.csv"):
            rows = self._read_csv_rows(DATA_DIR / name)
            self._assert_tiers_valid(rows, name)

    # -----------------------------------------------------------------------
    # Match report structure & reconciliation
    # -----------------------------------------------------------------------

    def test_ltgov_match_report_keys_present(self) -> None:
        report_path = DATA_DIR / "kalshi-lt-governor-candidate-match-report.json"
        self.assertTrue(report_path.exists(), msg="Missing lt-governor match report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for key in ("office", "blocking_issue_count", "candidate_winner", "candidate_nominee", "top_unresolved_examples"):
            self.assertIn(key, report, msg=f"Missing key '{key}' in lt-governor match report")

    def test_ltgov_report_counts_match_csv(self) -> None:
        report = json.loads((DATA_DIR / "kalshi-lt-governor-candidate-match-report.json").read_text(encoding="utf-8"))
        winner_rows = self._read_csv_rows(DATA_DIR / "kalshi-lt-governor-candidate-winner.csv")
        nominee_rows = self._read_csv_rows(DATA_DIR / "kalshi-lt-governor-candidate-nominee.csv")
        self._assert_report_matches_rows(winner_rows, report, "candidate_winner")
        self._assert_report_matches_rows(nominee_rows, report, "candidate_nominee")

    def test_ltgov_unresolved_examples_have_required_fields(self) -> None:
        report = json.loads((DATA_DIR / "kalshi-lt-governor-candidate-match-report.json").read_text(encoding="utf-8"))
        required = {"market_ticker", "seat", "kalshi_candidate_name", "oddsPercent", "ballotpedia_match_status", "match_confidence_tier"}
        for example in report.get("top_unresolved_examples") or []:
            missing = required - set(example.keys())
            self.assertFalse(missing, msg=f"Unresolved example missing fields: {sorted(missing)}")

    # -----------------------------------------------------------------------
    # Violations file
    # -----------------------------------------------------------------------

    def test_ltgov_violations_file_parseable(self) -> None:
        path = DATA_DIR / "kalshi-us-lt-governor-contest-integrity-violations.json"
        self.assertTrue(path.exists(), msg="Missing lt-governor violations JSON")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("count", data)
        self.assertIn("violations", data)
        self.assertIsInstance(data["violations"], list)

    # -----------------------------------------------------------------------
    # KXGA1ROUND exclusion check
    # -----------------------------------------------------------------------

    def test_ltgov_kxga1round_not_in_any_contest(self) -> None:
        path = DATA_DIR / "kalshi-us-lt-governor-contest-index.json"
        self.assertTrue(path.exists(), msg="Missing lt-governor contest index JSON")
        data = json.loads(path.read_text(encoding="utf-8"))
        contests = data.get("contests") or []
        for c in contests:
            self.assertNotEqual(
                str(c.get("market_ticker") or "").strip(),
                "KXGA1ROUND-26NOV03-LTGOV",
                msg="KXGA1ROUND meta market should not appear in contest index",
            )


if __name__ == "__main__":
    unittest.main()
