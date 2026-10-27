import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.archetypes import Archetype, detect_archetype
from ballotpedia_rollup.extract.national_overview import parse_national_incumbent_tables
from ballotpedia_rollup.parser import parse_all
from ballotpedia_rollup.seat import parse_seat_from_filename
from tests.raw_data import requires_raw_data


@requires_raw_data
class BallotpediaSenateRollupParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.senate_fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_senate_raw"
        cls.house_fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        cls.senate_general, cls.senate_primary, cls.senate_runoff, cls.senate_archetype_counts = parse_all(
            cls.senate_fixture_dir,
            office="us_senate",
            kalshi_indexes={},
        )
        cls.house_general, cls.house_primary, cls.house_runoff, _ = parse_all(
            cls.house_fixture_dir,
            office="us_house",
            kalshi_indexes={},
        )

    def test_parse_national_senate_pre_election_incumbents(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_senate_raw" / "National.txt").read_text(encoding="utf-8")
        by_seat, departures = parse_national_incumbent_tables(
            html,
            "https://ballotpedia.org/United_States_Senate_elections,_2026",
            office="us_senate",
        )
        self.assertGreater(len(departures), 0)
        self.assertEqual(by_seat["AL-SEN-C2"]["incumbent_name"], "Tommy Tuberville")
        self.assertEqual(by_seat["AL-SEN-C2"]["incumbent_party"], "R")
        self.assertEqual(by_seat["AL-SEN-C2"]["incumbent_status"], "seeking_other_office")
        self.assertEqual(by_seat["CO-SEN-C2"]["incumbent_party"], "D")

    def test_parse_seat_from_filename_senate_shapes(self):
        self.assertEqual(
            parse_seat_from_filename("AK.txt", office="us_senate"),
            ("AK", "STATEWIDE", "AK-SEN-C2"),
        )
        self.assertEqual(
            parse_seat_from_filename("FL-SPECIAL.txt", office="us_senate"),
            ("FL", "STATEWIDE", "FL-SEN-C3-SPL"),
        )
        self.assertEqual(
            parse_seat_from_filename("OH-SPECIAL.txt", office="us_senate"),
            ("OH", "STATEWIDE", "OH-SEN-C3-SPL"),
        )

    def test_detect_archetype_senate_national(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_senate_raw" / "National.txt").read_text(encoding="utf-8")
        self.assertEqual(detect_archetype(html, office="us_senate"), Archetype.NATIONAL_OVERVIEW)

    def test_parse_all_senate_emits_expected_seat_count_and_specials(self):
        general_rows = self.senate_general
        primary_rows = self.senate_primary
        runoff_rows = self.senate_runoff
        archetype_counts = self.senate_archetype_counts

        self.assertGreater(len(primary_rows), 0)
        self.assertIsInstance(runoff_rows, list)
        self.assertEqual(archetype_counts.get("national_overview", 0), 1)
        self.assertEqual(len(general_rows), 35)

        seats = {row.get("seat") for row in general_rows}
        self.assertIn("FL-SEN-C3-SPL", seats)
        self.assertIn("OH-SEN-C3-SPL", seats)
        self.assertIn("AK-SEN-C2", seats)
        self.assertTrue(all(row.get("district") == "STATEWIDE" for row in general_rows))
        regular_rows = [row for row in general_rows if str(row.get("seat") or "").endswith("-SEN-C2")]
        unknown_regular = [row for row in regular_rows if str(row.get("incumbent_name") or "").strip().lower() in {"", "unknown"}]
        self.assertLessEqual(len(unknown_regular), 2)
        backfilled = [row for row in regular_rows if "incumbent_from_national_backfill" in str(row.get("parser_notes") or "")]
        self.assertGreater(len(backfilled), 0)

    def test_senate_rollup_schema_matches_house_schema(self):
        house_general = self.house_general
        house_primary = self.house_primary
        house_runoff = self.house_runoff
        senate_general = self.senate_general
        senate_primary = self.senate_primary
        senate_runoff = self.senate_runoff

        self.assertEqual(set(house_general[0].keys()), set(senate_general[0].keys()))
        self.assertEqual(set(house_primary[0].keys()), set(senate_primary[0].keys()))
        self.assertEqual(set(house_runoff[0].keys()), set(senate_runoff[0].keys()))


if __name__ == "__main__":
    unittest.main()
