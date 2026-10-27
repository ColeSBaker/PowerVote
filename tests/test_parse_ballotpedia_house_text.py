import importlib.util
import unittest
from pathlib import Path
from tests.raw_data import requires_raw_data


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "parse_ballotpedia_house_text.py"
spec = importlib.util.spec_from_file_location("parse_ballotpedia_house_text", MODULE_PATH)
parse_ballotpedia_house_text = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(parse_ballotpedia_house_text)

FIXTURE_DIR = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "output_house_text"


@requires_raw_data
class ParseBallotpediaHouseTextFixtureTests(unittest.TestCase):
    def parse_district(self, state_file: str, seat_id: str):
        records, state_summary = parse_ballotpedia_house_text.parse_state_file(FIXTURE_DIR / state_file)
        record = next(item for item in records if item["seatId"] == seat_id)
        return record, state_summary

    def test_texas_normal_partisan_primary_district_keeps_expected_sections(self):
        record, state_summary = self.parse_district("Texas.txt", "TX-07")

        ballotpedia = record["election"]["ballotpedia"]
        self.assertEqual(state_summary["scrapeQualityFlags"], [])
        self.assertEqual(ballotpedia["generalElectionCandidateLines"], [
            "Lizzie Pannill Fletcher (Incumbent) (Democratic Party)",
            "Tina Blum Cohen",
            "Alexander Hale",
        ])
        self.assertEqual(ballotpedia["primaryCandidateSections"]["Democratic"], ["Lizzie Pannill Fletcher (Incumbent) ✔"])
        self.assertEqual(
            ballotpedia["primaryCandidateSections"]["Republican"],
            ["Tina Blum Cohen ✔", "Alexander Hale ✔", "Alexander Kalai", "Erin Montgomery", "Espoir Ngabo"],
        )
        self.assertEqual(
            ballotpedia["scrapeQualityFlags"],
            ["advanced_from_primary_missing"],
        )

    def test_district_with_none_parsed_general_candidates_preserves_placeholder(self):
        record, _ = self.parse_district("Louisiana.txt", "LA-01")

        ballotpedia = record["election"]["ballotpedia"]
        self.assertEqual(ballotpedia["generalElectionCandidateLines"], ["[None parsed]"])
        self.assertEqual(
            ballotpedia["primaryCandidateSections"]["Republican"],
            ["Steve Scalise (Incumbent)", "Randall Arrington"],
        )
        self.assertIn("general_candidates_incomplete", ballotpedia["scrapeQualityFlags"])
        self.assertIn("advanced_from_primary_missing", ballotpedia["scrapeQualityFlags"])

    def test_california_district_without_primary_sections_sets_no_primary_flag(self):
        record, _ = self.parse_district("California.txt", "CA-01")

        ballotpedia = record["election"]["ballotpedia"]
        self.assertEqual(ballotpedia["primaryCandidateSections"], {})
        self.assertEqual(ballotpedia["generalElectionCandidateLines"][0], "James Brock (Democratic Party)")
        self.assertEqual(
            ballotpedia["scrapeQualityFlags"],
            ["no_primary_sections", "general_candidates_incomplete", "advanced_from_primary_missing"],
        )

    def test_scrape_garbage_is_removed_from_party_block_but_flagged(self):
        record, _ = self.parse_district("Louisiana.txt", "LA-06")

        ballotpedia = record["election"]["ballotpedia"]
        republican_candidates = ballotpedia["primaryCandidateSections"]["Republican"]
        self.assertEqual(republican_candidates[:4], ["Monique Appeaning", "Larry Davis", "Christian Johnson", "Peter Williams"])
        self.assertIn("contains_scrape_garbage", ballotpedia["scrapeQualityFlags"])
        self.assertNotIn(
            "Safe and Solid ratings indicate that one party has a clear edge and the race is not competitive.",
            republican_candidates,
        )
        self.assertNotIn("Search Google News for this topic", republican_candidates)

    def test_state_file_with_no_district_sections_sets_state_level_flag(self):
        records, state_summary = parse_ballotpedia_house_text.parse_state_file(FIXTURE_DIR / "Washington.txt")

        self.assertEqual(records, [])
        self.assertEqual(state_summary["districtCount"], 0)
        self.assertEqual(state_summary["scrapeQualityFlags"], ["no_district_sections"])


if __name__ == "__main__":
    unittest.main()
