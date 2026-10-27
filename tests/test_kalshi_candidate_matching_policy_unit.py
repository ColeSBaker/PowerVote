from __future__ import annotations

import unittest
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi_candidate_mapping import (  # noqa: E402
    BallotpediaCandidate,
    build_candidate_match_report,
    match_ballotpedia_candidate,
    normalize_name,
)


class KalshiCandidateMatchingPolicyUnitTests(unittest.TestCase):
    def _pool(self, key: str, names: list[str]) -> dict[str, list[BallotpediaCandidate]]:
        seat, rnd, party = key.split("|")
        return {
            key: [
                BallotpediaCandidate(
                    seat=seat,
                    round_name=rnd,
                    party=party,
                    name=name,
                    source="fixture",
                    normalized=normalize_name(name),
                )
                for name in names
            ]
        }

    def test_exact_and_signature_match_are_tier_a(self):
        pool = self._pool("AK-SEN-C2|general|R", ["Daniel S. Sullivan"])
        out = match_ballotpedia_candidate(
            kalshi_name="Dan Sullivan",
            seat="AK-SEN-C2",
            round_name="general",
            party="R",
            pool_by_key=pool,
        )
        self.assertEqual(out["ballotpedia_match_status"], "matched")
        self.assertEqual(out["match_confidence_tier"], "A")
        self.assertIn(out["match_reason_code"], {"signature_match", "exact_normalized"})

    def test_near_typo_matches_tier_a(self):
        pool = self._pool("AL-05|primary|D", ["Candice Duvieilh"])
        out = match_ballotpedia_candidate(
            kalshi_name="Candice Devieilh",
            seat="AL-05",
            round_name="primary",
            party="D",
            pool_by_key=pool,
        )
        self.assertEqual(out["ballotpedia_match_status"], "matched")
        self.assertEqual(out["match_confidence_tier"], "A")

    def test_last_name_only_conflict_not_auto_matched(self):
        pool = self._pool("SC-01|primary|R", ["Mark Sanford"])
        out = match_ballotpedia_candidate(
            kalshi_name="Joe Sanford",
            seat="SC-01",
            round_name="primary",
            party="R",
            pool_by_key=pool,
        )
        self.assertNotEqual(out["ballotpedia_match_status"], "matched")
        self.assertIn(out["match_confidence_tier"], {"C", "D"})

    def test_no_pool_for_seat_is_needs_source_update(self):
        out = match_ballotpedia_candidate(
            kalshi_name="Brooke Pinto",
            seat="DC-AL",
            round_name="primary",
            party="D",
            pool_by_key={},
        )
        self.assertEqual(out["match_confidence_tier"], "D")
        self.assertEqual(out["match_reason_code"], "no_pool_for_seat")
        self.assertEqual(out["review_recommendation"], "needs_source_update")

    def test_waived_high_impact_unresolved_is_non_blocking(self):
        report = build_candidate_match_report(
            [
                {
                    "seat": "AK-SEN-C2",
                    "round": "primary",
                    "party": "D",
                    "market_ticker": "TICKER1",
                    "kalshi_candidate_name": "Example A",
                    "oddsPercent": 55,
                    "ballotpedia_match_status": "unmatched",
                    "match_confidence_tier": "D",
                    "review_status": "waived",
                    "match_reason_code": "waived_unresolved",
                    "review_recommendation": "source_data_issue",
                },
                {
                    "seat": "AK-SEN-C2",
                    "round": "primary",
                    "party": "D",
                    "market_ticker": "TICKER2",
                    "kalshi_candidate_name": "Example B",
                    "oddsPercent": 51,
                    "ballotpedia_match_status": "unmatched",
                    "match_confidence_tier": "D",
                    "review_status": "pending",
                    "match_reason_code": "no_candidate_above_threshold",
                    "review_recommendation": "pending",
                },
            ],
            office="us_senate",
            market_type="candidate_nominee",
        )
        self.assertEqual(report["waived_issue_count"], 1)
        self.assertEqual(report["blocking_issue_count"], 1)
        self.assertEqual(len(report["waived_examples"]), 1)


if __name__ == "__main__":
    unittest.main()
