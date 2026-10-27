import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup import archetypes
from ballotpedia_rollup.ids import make_primary_id
from ballotpedia_rollup.seat import parse_seat_from_filename


class BallotpediaRollupRoutingTests(unittest.TestCase):
    def test_parse_seat_from_filename(self):
        self.assertEqual(parse_seat_from_filename("TX-28.txt"), ("TX", "28", "TX-28"))
        self.assertEqual(parse_seat_from_filename("TX.txt"), ("TX", "STATE_ROLLUP", "TX"))
        self.assertEqual(parse_seat_from_filename("National.txt"), ("US", "NATIONAL", "NATIONAL"))
        self.assertEqual(
            parse_seat_from_filename("AZ-GOV.txt", office="state_governor"),
            ("AZ", "STATEWIDE", "AZ-GOV"),
        )
        self.assertEqual(
            parse_seat_from_filename("IA-LTGOV.txt", office="state_lieutenant_governor"),
            ("IA", "STATEWIDE", "IA-LTGOV"),
        )

    def test_make_primary_id(self):
        self.assertEqual(make_primary_id("TX-28", "D", "primary"), "TX-28-D-primary-2026")

    def test_archetype_detection(self):
        district_html = '<div id="Candidates_and_election_results"></div><div class="votebox"></div>'
        state_html = '<div id="Candidates"></div><h3 id="District_1">District 1</h3>'
        national_html = '<title>United States House of Representatives elections, 2026 - Ballotpedia</title>'
        governor_national_html = '<title>Gubernatorial elections, 2026 - Ballotpedia</title>'

        self.assertEqual(archetypes.detect_archetype(district_html).value, "district_detail")
        self.assertEqual(archetypes.detect_archetype(state_html).value, "state_rollup")
        self.assertEqual(archetypes.detect_archetype(national_html).value, "national_overview")
        self.assertEqual(
            archetypes.detect_archetype(governor_national_html, office="state_governor").value,
            "national_overview",
        )


if __name__ == "__main__":
    unittest.main()
