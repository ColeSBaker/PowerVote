import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.parser import parse_all
from tests.raw_data import requires_raw_data


@requires_raw_data
class BallotpediaAttorneyGeneralRollupParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ag_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_attorney_general_raw"
        cls.governor_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_governor_raw"
        cls.ag_general, cls.ag_primary, cls.ag_runoff, cls.ag_archetypes = parse_all(
            cls.ag_dir,
            office="state_attorney_general",
            kalshi_indexes={},
        )
        cls.governor_general, cls.governor_primary, cls.governor_runoff, _ = parse_all(
            cls.governor_dir,
            office="state_governor",
            kalshi_indexes={},
        )

    def test_parse_all_ag_emits_statewide_rows(self):
        general_rows = self.ag_general
        primary_rows = self.ag_primary
        runoff_rows = self.ag_runoff
        archetype_counts = self.ag_archetypes

        self.assertGreater(len(general_rows), 0)
        self.assertGreater(len(primary_rows), 0)
        self.assertIsInstance(runoff_rows, list)
        self.assertEqual(archetype_counts.get("national_overview", 0), 1)
        seats = {str(row.get("seat") or "") for row in general_rows}
        self.assertIn("AL-AG", seats)
        self.assertIn("IA-AG", seats)
        self.assertTrue(any((row.get("district") or "") == "STATEWIDE" for row in general_rows))

    def test_ag_rollup_schema_matches_governor_schema(self):
        governor_general = self.governor_general
        governor_primary = self.governor_primary
        governor_runoff = self.governor_runoff
        ag_general = self.ag_general
        ag_primary = self.ag_primary
        ag_runoff = self.ag_runoff

        self.assertEqual(set(governor_general[0].keys()), set(ag_general[0].keys()))
        self.assertEqual(set(governor_primary[0].keys()), set(ag_primary[0].keys()))
        if governor_runoff and ag_runoff:
            self.assertEqual(set(governor_runoff[0].keys()), set(ag_runoff[0].keys()))

    def test_ag_parse_skips_fec_enrichment(self):
        general_rows = self.ag_general
        self.assertGreater(len(general_rows), 0)
        self.assertTrue(all((row.get("fec_incumbent_name") or "") == "" for row in general_rows))
        self.assertTrue(all((row.get("fec_incumbent_party") or "") == "" for row in general_rows))

    def test_ag_seat_format_uses_ag_suffix(self):
        for row in self.ag_general:
            seat = str(row.get("seat") or "")
            if seat and seat != "NATIONAL":
                self.assertTrue(seat.endswith("-AG"), f"Seat {seat} should end with -AG")

    def test_ag_district_is_always_statewide(self):
        for row in self.ag_general:
            self.assertEqual(row.get("district"), "STATEWIDE")


if __name__ == "__main__":
    unittest.main()
