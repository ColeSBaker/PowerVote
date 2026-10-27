from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from senate_fec_linkage import link_senate_candidates_with_fec


class SenateFecLinkageTests(unittest.TestCase):
    def test_exact_state_party_name_match(self) -> None:
        senate_rows = [
            {"BallotpediaName": "Jane Doe", "2026 Seat": "TX-SEN-C2", "Party": "D"},
        ]
        fec_rows = [
            {
                "Cand_Office": "S",
                "Cand_Office_St": "TX",
                "Cand_Party_Affiliation": "DEM",
                "Cand_Name": "DOE, JANE",
                "Cand_Id": "S6TX00001",
                "Total_Receipt": "1200000",
                "Cash_On_Hand_COP": "450000",
                "Coverage_End_Date": "03/31/2026",
            }
        ]
        enriched, audit, conflicts = link_senate_candidates_with_fec(senate_rows, fec_rows)
        self.assertEqual(enriched[0]["FEC Candidate ID"], "S6TX00001")
        self.assertEqual(enriched[0]["FEC Match Strategy"], "state_party_name_exact")
        self.assertEqual(conflicts, [])
        self.assertEqual(audit[0]["match_strategy"], "state_party_name_exact")

    def test_fallback_match_surfaces_party_conflict(self) -> None:
        senate_rows = [
            {"BallotpediaName": "Alex Smith", "2026 Seat": "OH-SEN-C3-SPL", "Party": "D"},
        ]
        fec_rows = [
            {
                "Cand_Office": "S",
                "Cand_Office_St": "OH",
                "Cand_Party_Affiliation": "REP",
                "Cand_Name": "SMITH, ALEX",
                "Cand_Id": "S6OH00077",
                "Total_Receipt": "500000",
                "Cash_On_Hand_COP": "110000",
                "Coverage_End_Date": "03/31/2026",
            }
        ]
        enriched, audit, conflicts = link_senate_candidates_with_fec(senate_rows, fec_rows)
        self.assertEqual(enriched[0]["FEC Candidate ID"], "S6OH00077")
        self.assertEqual(enriched[0]["FEC Match Strategy"], "state_name_fallback")
        self.assertEqual(enriched[0]["FEC Conflict"], "party_mismatch_fallback")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(audit[0]["conflict"], "party_mismatch_fallback")


if __name__ == "__main__":
    unittest.main()
