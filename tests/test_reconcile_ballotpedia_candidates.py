import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "candidates" / "reconcile_ballotpedia_candidates.py"
spec = importlib.util.spec_from_file_location("reconcile_ballotpedia_candidates", MODULE_PATH)
reconcile_ballotpedia_candidates = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(reconcile_ballotpedia_candidates)


class ReconcileBallotpediaCandidatesTests(unittest.TestCase):
    def test_alias_reconciliation_matches_lizzie_fletcher_to_elizabeth_fletcher(self):
        result = reconcile_ballotpedia_candidates.reconcile_ballotpedia_candidate(
            "Lizzie Pannill Fletcher (Incumbent) (Democratic Party)",
            [
                {
                    "candidateId": "H8TX07140",
                    "name": "ELIZABETH FLETCHER",
                    "kalshiName": None,
                    "aliases": ["Lizzie Fletcher", "Lizzie Pannill Fletcher"],
                    "partyCode": "DEM",
                    "seatId": "TX-07",
                }
            ],
            "TX-07",
        )

        self.assertEqual(result["matchStrategy"], "alias")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["matchedCandidate"]["candidateId"], "H8TX07140")
        self.assertEqual(result["likelyPartyCode"], "DEM")

    def test_reconcile_uses_conservative_fuzzy_match_within_seat_and_party(self):
        result = reconcile_ballotpedia_candidates.reconcile_ballotpedia_candidate(
            "Steve Toth (Republican Party)",
            [
                {
                    "candidateId": "cand-1",
                    "name": "Steven Toth",
                    "kalshiName": None,
                    "aliases": [],
                    "partyCode": "REP",
                    "seatId": "TX-02",
                },
                {
                    "candidateId": "cand-2",
                    "name": "Stephen Toth",
                    "kalshiName": None,
                    "aliases": [],
                    "partyCode": "DEM",
                    "seatId": "TX-02",
                },
                {
                    "candidateId": "cand-3",
                    "name": "Steve Toth",
                    "kalshiName": None,
                    "aliases": [],
                    "partyCode": "REP",
                    "seatId": "TX-03",
                },
            ],
            "TX-02",
        )

        self.assertEqual(result["matchStrategy"], "fuzzy_seat_party")
        self.assertEqual(result["matchedCandidate"]["candidateId"], "cand-1")

    def test_reconcile_matches_compound_alias_with_middle_name_and_nickname(self):
        result = reconcile_ballotpedia_candidates.reconcile_ballotpedia_candidate(
            "Sam Forstag (Democratic Party)",
            [
                {
                    "candidateId": "cand-4",
                    "name": "SAMUEL KELLEY FORSTAG",
                    "kalshiName": "Sam Forstag",
                    "aliases": ["Sam Forstag"],
                    "partyCode": "DEM",
                    "seatId": "MT-01",
                }
            ],
            "MT-01",
        )

        self.assertEqual(result["matchStrategy"], "alias")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["matchedCandidate"]["candidateId"], "cand-4")

    def test_low_confidence_seat_keeps_pruning_disabled_and_needs_review(self):
        payload = reconcile_ballotpedia_candidates.reconcile_ballotpedia_candidates_by_seat(
            {"TX-07": ["Mystery Candidate", "Lizzie Pannill Fletcher (Incumbent) (Democratic Party)"]},
            {
                "TX-07": [
                    {
                        "candidateId": "H8TX07140",
                        "name": "ELIZABETH FLETCHER",
                        "kalshiName": None,
                        "aliases": ["Lizzie Pannill Fletcher"],
                        "partyCode": "DEM",
                        "seatId": "TX-07",
                    }
                ]
            },
        )

        self.assertEqual(payload["TX-07"]["confidence"], "low")
        self.assertTrue(payload["TX-07"]["needsReview"])
        self.assertFalse(payload["TX-07"]["pruningEnabled"])
        self.assertEqual(payload["TX-07"]["sourceCandidates"][0]["unmatchedSourceName"], "Mystery Candidate")
        self.assertEqual(payload["TX-07"]["sourceCandidates"][1]["matchedCandidate"]["candidateId"], "H8TX07140")


if __name__ == "__main__":
    unittest.main()
