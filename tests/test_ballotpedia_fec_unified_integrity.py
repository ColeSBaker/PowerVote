import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.fec_matching import FecCandidate, build_fec_matcher, match_candidate
from ballotpedia_rollup.parser import build_rollup_context
from ballotpedia_rollup.fec_matching import load_fec_rows
from tests.raw_data import requires_raw_data


@requires_raw_data
class BallotpediaFecUnifiedIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fec_rows = load_fec_rows()
        cls.house_context = build_rollup_context(
            REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw",
            office="us_house",
            fec_rows=fec_rows,
            kalshi_indexes={},
        )
        cls.senate_context = build_rollup_context(
            REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_senate_raw",
            office="us_senate",
            fec_rows=fec_rows,
            kalshi_indexes={},
        )

    def test_every_fec_incumbent_has_ballotpedia_candidate_match_house(self):
        metrics = self.house_context.fec_match_metrics["us_house"]
        failures = [row for row in self.house_context.fec_match_audit if row.get("is_incumbent") and not row.get("matched_ballotpedia_name")]
        self.assertEqual(
            int(metrics["incumbent_hard_failures"]),
            0,
            msg=f"House FEC incumbent hard failures: {failures[:20]} (total={len(failures)})",
        )

    def test_every_fec_incumbent_has_ballotpedia_candidate_match_senate(self):
        metrics = self.senate_context.fec_match_metrics["us_senate"]
        failures = [row for row in self.senate_context.fec_match_audit if row.get("is_incumbent") and not row.get("matched_ballotpedia_name")]
        self.assertEqual(
            int(metrics["incumbent_hard_failures"]),
            0,
            msg=f"Senate FEC incumbent hard failures: {failures[:20]} (total={len(failures)})",
        )

    def test_fec_declared_unmatched_rate_house_below_threshold(self):
        metrics = self.house_context.fec_match_metrics["us_house"]
        self.assertLessEqual(
            float(metrics["declared_unmatched_rate"]),
            0.05,
            msg=f"House unmatched-rate gate failed: {metrics}",
        )

    def test_fec_declared_unmatched_rate_senate_below_threshold(self):
        metrics = self.senate_context.fec_match_metrics["us_senate"]
        self.assertLessEqual(
            float(metrics["declared_unmatched_rate"]),
            0.05,
            msg=f"Senate unmatched-rate gate failed: {metrics}",
        )

    def test_unified_audit_has_expected_schema_and_sorted_order(self):
        required = {
            "office",
            "seat",
            "fec_candidate_id",
            "fec_name",
            "fec_party",
            "is_incumbent",
            "matched_ballotpedia_name",
            "match_strategy",
            "match_score",
            "reason_unmatched",
        }
        for context in (self.house_context, self.senate_context):
            rows = context.fec_match_audit
            self.assertGreater(len(rows), 0)
            for row in rows[:50]:
                self.assertTrue(required.issubset(set(row.keys())))
            expected = sorted(
                rows,
                key=lambda item: (
                    str(item.get("seat") or ""),
                    str(item.get("fec_party") or ""),
                    str(item.get("fec_name") or ""),
                    str(item.get("fec_candidate_id") or ""),
                ),
            )
            self.assertEqual(rows, expected)


class FecMatchingBehaviorTests(unittest.TestCase):
    def test_seat_party_exact_beats_fuzzy(self):
        candidates = [
            FecCandidate(seat="TX-01", party="D", name="Jane Doe", candidate_id="H1", coverage_end_date="03/31/2026"),
            FecCandidate(seat="TX-01", party="D", name="Janet Doey", candidate_id="H2", coverage_end_date="03/31/2026"),
        ]
        matcher = build_fec_matcher(candidates)
        candidate_id, strategy, _score = match_candidate("TX-01", "D", "Jane Doe", candidates, matcher=matcher)
        self.assertEqual(candidate_id, "H1")
        self.assertEqual(strategy, "exact")

    def test_party_relaxed_seat_exact_is_allowed(self):
        candidates = [
            FecCandidate(seat="TX-02", party="R", name="Alex Smith", candidate_id="H3", coverage_end_date="03/31/2026"),
        ]
        matcher = build_fec_matcher(candidates)
        candidate_id, strategy, _score = match_candidate("TX-02", "D", "Alex Smith", candidates, matcher=matcher)
        self.assertEqual(candidate_id, "H3")
        self.assertIn(strategy, {"exact", "seat_exact_party_relaxed"})

    def test_cross_seat_fuzzy_requires_explicit_global_fallback(self):
        candidates = [
            FecCandidate(seat="CA-12", party="D", name="Jordan Adams", candidate_id="H4", coverage_end_date="03/31/2026"),
        ]
        matcher = build_fec_matcher(candidates)
        candidate_id, strategy, _score = match_candidate("NY-10", "D", "Jordan Adams", candidates, matcher=matcher)
        self.assertIn(strategy, {"global_exact_no_seat", "global_fuzzy_no_seat_high_confidence", "no_seat_candidates"})
        if strategy == "no_seat_candidates":
            self.assertEqual(candidate_id, "")

    def test_ambiguous_multi_candidate_match_is_deterministically_unresolved(self):
        candidates = [
            FecCandidate(seat="WA-01", party="D", name="Chris Lee", candidate_id="H5", coverage_end_date="03/31/2026"),
            FecCandidate(seat="WA-01", party="D", name="Charles Lee", candidate_id="H6", coverage_end_date="03/31/2026"),
        ]
        matcher = build_fec_matcher(candidates)
        candidate_id, strategy, _score = match_candidate("WA-01", "D", "C. Lee", candidates, matcher=matcher)
        self.assertEqual(candidate_id, "")
        self.assertEqual(strategy, "ambiguous_fuzzy")


if __name__ == "__main__":
    unittest.main()
