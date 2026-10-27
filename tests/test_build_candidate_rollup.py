import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

MODULE_PATH = SCRIPTS_DIR / "build_candidate_rollup.py"
spec = importlib.util.spec_from_file_location("build_candidate_rollup", MODULE_PATH)
build_candidate_rollup = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = build_candidate_rollup
spec.loader.exec_module(build_candidate_rollup)


class BuildCandidateRollupTests(unittest.TestCase):
    def test_normalize_name_removes_honorific_tokens(self):
        self.assertEqual(
            build_candidate_rollup.normalize_name("TRACY DR. ANDRUS"),
            build_candidate_rollup.normalize_name("Tracy Andrus"),
        )
        self.assertEqual(
            build_candidate_rollup.normalize_name("STEVE I MR. COHEN"),
            build_candidate_rollup.normalize_name("Steve Cohen"),
        )

    def test_normalize_name_keeps_distinguishing_tokens(self):
        self.assertNotEqual(
            build_candidate_rollup.normalize_name("YOLANDA RENA PRINCE"),
            build_candidate_rollup.normalize_name("YOLANDA PRINCE"),
        )

    def test_build_identity_metadata_merges_kalshi_and_fec_aliases_and_candidate_ids(self):
        candidate = {
            "candidateId": "H0TX01000",
            "kalshiName": "Lizzie Fletcher",
            "aliases": ["Lizzie Pannill Fletcher"],
        }
        finance_match = build_candidate_rollup.MatchResult(
            record={"candidateId": "H0TX01000", "name": "FLETCHER, ELIZABETH"},
            strategy="candidateId_exact",
            score=1.0,
        )

        metadata = build_candidate_rollup.build_identity_metadata(candidate, finance_match)

        self.assertEqual(
            metadata["aliases"],
            ["Lizzie Fletcher", "Lizzie Pannill Fletcher", "FLETCHER, ELIZABETH"],
        )
        self.assertEqual(metadata["sourceAliases"]["kalshi"], ["Lizzie Fletcher", "Lizzie Pannill Fletcher"])
        self.assertEqual(metadata["sourceAliases"]["fec"], ["FLETCHER, ELIZABETH"])
        self.assertEqual(metadata["candidateIds"], ["H0TX01000"])

    def test_build_rollup_includes_identity_fields(self):
        candidates = [
            {
                "candidateId": "H0TX01000",
                "name": "Elizabeth Fletcher",
                "seatId": "TX-07",
                "partyCode": "DEM",
                "aliases": ["Lizzie Pannill Fletcher"],
                "kalshiName": "Lizzie Fletcher",
                "currentElectionStatus": {"code": "primary-active"},
                "incumbentStatus": "Incumbent",
            }
        ]
        finance_rows = [
            {
                "Cand_Office": "H",
                "Cand_Office_St": "TX",
                "Cand_Office_Dist": "7",
                "Cand_Party_Affiliation": "DEM",
                "Cand_Name": "FLETCHER, ELIZABETH",
                "Cand_Id": "H0TX01000",
                "Total_Receipt": "1000",
                "Total_Disbursement": "900",
                "Cash_On_Hand_COP": "300",
                "Coverage_End_Date": "12/31/2025",
            }
        ]

        rows = build_candidate_rollup.build_rollup(
            candidates=candidates,
            primary_rows=[],
            runoff_rows=[],
            general_rows=[],
            finance_rows=finance_rows,
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["aliases"], ["Lizzie Fletcher", "Lizzie Pannill Fletcher", "FLETCHER, ELIZABETH"])
        self.assertEqual(row["sourceAliases"]["kalshi"], ["Lizzie Fletcher", "Lizzie Pannill Fletcher"])
        self.assertEqual(row["sourceAliases"]["fec"], ["FLETCHER, ELIZABETH"])
        self.assertEqual(row["candidateIds"], ["H0TX01000"])

    def test_reconciliation_dedupes_tx1_identity_and_suppresses_duplicate_own_rows(self):
        candidates = [
            {
                "candidateId": "H8TX01023",
                "name": "Nathaniel Moran",
                "seatId": "TX-1",
                "partyCode": "REP",
                "aliases": ["Nate Moran"],
                "kalshiName": None,
                "currentElectionStatus": {"code": "general-nominated"},
                "incumbentStatus": "Incumbent",
            },
            {
                "candidateId": None,
                "name": "Nate Moran",
                "seatId": "TX-1",
                "partyCode": "OWN",
                "aliases": [],
                "kalshiName": None,
                "currentElectionStatus": {"code": "general-other"},
                "incumbentStatus": "",
            },
        ]
        finance_rows = [
            {
                "Cand_Office": "H",
                "Cand_Office_St": "TX",
                "Cand_Office_Dist": "1",
                "Cand_Party_Affiliation": "REP",
                "Cand_Name": "MORAN, NATHANIEL",
                "Cand_Id": "H8TX01023",
                "Total_Receipt": "2000",
                "Total_Disbursement": "1500",
                "Cash_On_Hand_COP": "500",
                "Coverage_End_Date": "12/31/2025",
            }
        ]

        reconciled = build_candidate_rollup.reconcile_candidates(candidates, finance_rows)
        rows = build_candidate_rollup.build_rollup(
            candidates=reconciled,
            primary_rows=[],
            runoff_rows=[],
            general_rows=[],
            finance_rows=finance_rows,
        )

        tx1_moran_rows = [row for row in rows if row["2026 Seat"] == "TX-01" and row["CandidateID"] == "H8TX01023"]
        self.assertGreaterEqual(len(tx1_moran_rows), 1)
        self.assertIn("REP", {row["Party"] for row in tx1_moran_rows})
        self.assertNotIn("OWN", {row["Party"] for row in tx1_moran_rows})
        self.assertNotIn(
            "OWN",
            [row["Party"] for row in rows if row["2026 Seat"] == "TX-01" and "moran" in row["BallotpediaName"].lower()],
        )


if __name__ == "__main__":
    unittest.main()
