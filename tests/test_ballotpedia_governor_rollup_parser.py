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
class BallotpediaGovernorRollupParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.governor_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_governor_raw"
        cls.senate_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_senate_raw"
        cls.governor_general, cls.governor_primary, cls.governor_runoff, cls.governor_archetypes = parse_all(
            cls.governor_dir,
            office="state_governor",
            kalshi_indexes={},
        )
        cls.ltgov_general, cls.ltgov_primary, cls.ltgov_runoff, cls.ltgov_archetypes = parse_all(
            cls.governor_dir,
            office="state_lieutenant_governor",
            kalshi_indexes={},
        )
        cls.senate_general, cls.senate_primary, cls.senate_runoff, _ = parse_all(
            cls.senate_dir,
            office="us_senate",
            kalshi_indexes={},
        )

    def test_parse_all_governor_emits_statewide_rows(self):
        general_rows = self.governor_general
        primary_rows = self.governor_primary
        runoff_rows = self.governor_runoff
        archetype_counts = self.governor_archetypes

        self.assertGreater(len(general_rows), 0)
        self.assertGreater(len(primary_rows), 0)
        self.assertIsInstance(runoff_rows, list)
        self.assertEqual(archetype_counts.get("national_overview", 0), 1)
        seats = {str(row.get("seat") or "") for row in general_rows}
        self.assertIn("AL-GOV", seats)
        self.assertIn("IA-GOV", seats)
        self.assertTrue(any((row.get("district") or "") == "STATEWIDE" for row in general_rows))

    def test_parse_all_ltgovernor_emits_statewide_rows(self):
        general_rows = self.ltgov_general
        primary_rows = self.ltgov_primary
        runoff_rows = self.ltgov_runoff
        archetype_counts = self.ltgov_archetypes

        self.assertGreater(len(general_rows), 0)
        self.assertGreater(len(primary_rows), 0)
        self.assertIsInstance(runoff_rows, list)
        self.assertEqual(archetype_counts.get("national_overview", 0), 1)
        seats = {str(row.get("seat") or "") for row in general_rows}
        self.assertIn("AL-LTGOV", seats)
        self.assertIn("IA-LTGOV", seats)
        self.assertTrue(any((row.get("district") or "") == "STATEWIDE" for row in general_rows))

    def test_governor_rollup_schema_matches_house_schema(self):
        senate_general = self.senate_general
        senate_primary = self.senate_primary
        senate_runoff = self.senate_runoff
        governor_general = self.governor_general
        governor_primary = self.governor_primary
        governor_runoff = self.governor_runoff

        self.assertEqual(set(senate_general[0].keys()), set(governor_general[0].keys()))
        self.assertEqual(set(senate_primary[0].keys()), set(governor_primary[0].keys()))
        if senate_runoff and governor_runoff:
            self.assertEqual(set(senate_runoff[0].keys()), set(governor_runoff[0].keys()))

    def test_governor_parse_skips_fec_enrichment(self):
        general_rows = self.governor_general
        self.assertGreater(len(general_rows), 0)
        self.assertTrue(all((row.get("fec_incumbent_name") or "") == "" for row in general_rows))
        self.assertTrue(all((row.get("fec_incumbent_party") or "") == "" for row in general_rows))


if __name__ == "__main__":
    unittest.main()
