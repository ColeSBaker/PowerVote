import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.extract.district_detail import parse_district_detail_file
from ballotpedia_rollup.extract.state_rollup import parse_state_rollup_file
from ballotpedia_rollup.extract.national_overview import parse_national_incumbent_tables, parse_national_targeting
from ballotpedia_rollup.parser import parse_all, parse_national_incumbent_departures
from ballotpedia_rollup.consolidate import consolidate_primary_rows, split_and_link_primary_rows
from tests.raw_data import requires_raw_data


class BallotpediaRollupParserTests(unittest.TestCase):
    @requires_raw_data
    def test_district_detail_parser_extracts_general_and_primary(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "TX-28.txt").read_text(encoding="utf-8")
        general, primaries = parse_district_detail_file(html, "TX-28.txt")

        self.assertIsNotNone(general)
        assert general is not None
        self.assertEqual(general["seat"], "TX-28")
        self.assertEqual(general["incumbent_name"], "Henry Cuellar")
        self.assertEqual(general["incumbent_party"], "D")
        self.assertEqual(general["nominee_d"], "Henry Cuellar")
        self.assertEqual(general["nominee_r"], "Tano Tijerina")
        self.assertIn("Adriel Ventura Lopez", general["other_general_candidates"])
        self.assertIn(general["primary_status_d"], {"none", "upcoming", "runoff", "complete"})
        self.assertGreaterEqual(len(primaries), 1)

    @requires_raw_data
    def test_state_rollup_parser_extracts_district_rows(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "IL.txt").read_text(encoding="utf-8")
        general_rows, primary_rows = parse_state_rollup_file(html, "IL.txt")

        self.assertGreaterEqual(len(general_rows), 17)
        self.assertGreater(len(primary_rows), 0)
        district_1 = next(row for row in general_rows if row["seat"] == "IL-1")
        self.assertEqual(district_1["incumbent_name"], "Jonathan Jackson")
        self.assertEqual(district_1["incumbent_party"], "D")
        self.assertEqual(district_1["nominee_d"], "Jonathan Jackson")
        self.assertEqual(district_1["nominee_r"], "Christian Maxwell")

    @requires_raw_data
    def test_tx01_dem_primary_extracts_vote_totals_and_candidate_counts(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "TX-1.txt").read_text(encoding="utf-8")
        _, primaries = parse_district_detail_file(html, "TX-1.txt")

        dem_primary = next(row for row in primaries if row["primary_id"] == "TX-1-D-primary-2026")
        self.assertEqual(dem_primary["primary_vote_total"], 35155)
        self.assertEqual(dem_primary["primary_vote_share"].get("Yolanda Prince"), 44.6)
        self.assertEqual(dem_primary["primary_vote_share"].get("Dax Alexander"), 22.0)
        self.assertEqual(dem_primary["primary_vote_count"].get("Yolanda Prince"), 15667)
        self.assertEqual(dem_primary["primary_vote_count"].get("Dax Alexander"), 7717)

    @requires_raw_data
    def test_tx01_extracts_historical_general_and_primary_vote_totals(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "TX-1.txt").read_text(encoding="utf-8")
        general, _ = parse_district_detail_file(html, "TX-1.txt")

        assert general is not None
        self.assertEqual(
            general["historical_general_vote_totals"],
            {"2024": 258523, "2022": 234662, "2020": 302742},
        )
        self.assertEqual(
            general["historical_primary_vote_totals"],
            {
                "2024": {"R": 84442},
                "2022": {"D": 16303, "R": 81444},
                "2020": {"D": 25037, "R": 93546},
            },
        )
        self.assertEqual(general["historical_primary_status"]["2024"]["D"], "none")
        self.assertEqual(general["historical_primary_status"]["2024"]["R"], "complete")
        self.assertEqual(general["historical_primary_reason"]["2024"]["D"], "no_primary_structure")

    @requires_raw_data
    def test_me_districts_extract_realistic_historical_general_vote_totals(self):
        me1_html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "ME-1.txt").read_text(encoding="utf-8")
        me2_html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "ME-2.txt").read_text(encoding="utf-8")

        me1_general, _ = parse_district_detail_file(me1_html, "ME-1.txt")
        me2_general, _ = parse_district_detail_file(me2_html, "ME-2.txt")

        assert me1_general is not None
        assert me2_general is not None
        self.assertEqual(
            me1_general["historical_general_vote_totals"],
            {"2024": 425530, "2022": 349176, "2020": 436027},
        )
        self.assertEqual(
            me2_general["historical_general_vote_totals"],
            {"2024": 391596, "2022": 316382, "2020": 373235},
        )

    @requires_raw_data
    def test_ak_at_large_historical_2022_prefers_regular_general_over_special_general(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "AK-AL.txt").read_text(encoding="utf-8")
        general, _ = parse_district_detail_file(html, "AK-AL.txt")

        assert general is not None
        self.assertEqual(general["historical_general_vote_totals"]["2022"], 264589)

    @requires_raw_data
    def test_state_rollup_rows_include_empty_historical_vote_maps(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "IL.txt").read_text(encoding="utf-8")
        general_rows, _ = parse_state_rollup_file(html, "IL.txt")
        self.assertGreater(len(general_rows), 0)
        row = general_rows[0]
        self.assertEqual(row["historical_general_vote_totals"], {})
        self.assertEqual(row["historical_primary_vote_totals"], {})
        self.assertEqual(row["historical_primary_status"], {})
        self.assertEqual(row["historical_primary_reason"], {})

    @requires_raw_data
    def test_extracts_general_election_race_rating_tags_from_most_recent_poll(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "TX-7.txt").read_text(encoding="utf-8")
        general, _ = parse_district_detail_file(html, "TX-7.txt")

        assert general is not None
        ratings = general["general_election_race_ratings"]
        self.assertEqual(ratings["most_recent_poll_date"], "3/17/2026")
        self.assertEqual(
            ratings["most_recent_poll_tags"],
            [
                "most_recent_poll_the_cook_political_report_with_amy_walter",
                "most_recent_poll_decision_desk_hq_and_the_hill",
                "most_recent_poll_inside_elections_with_nathan_l_gonzales",
                "most_recent_poll_larry_j_sabatos_crystal_ball",
            ],
        )
        outlet_ratings = {item["outlet"]: item["rating"] for item in ratings["outlet_ratings"]}
        self.assertEqual(outlet_ratings["The Cook Political Report with Amy Walter"], "Solid Democratic")
        self.assertEqual(outlet_ratings["Decision Desk HQ and The Hill"], "Pending")
        self.assertEqual(outlet_ratings["Inside Elections with Nathan L. Gonzales"], "Solid Democratic")
        self.assertEqual(outlet_ratings["Larry J. Sabato's Crystal Ball"], "Safe Democratic")

    @requires_raw_data
    def test_runoff_is_split_and_linked_to_parent_primary(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "TX-9.txt").read_text(encoding="utf-8")
        _, primaries = parse_district_detail_file(html, "TX-9.txt")

        consolidated = consolidate_primary_rows(primaries)
        primary_rows, runoff_rows = split_and_link_primary_rows(consolidated)

        republican_primary = next(row for row in primary_rows if row["primary_id"] == "TX-9-R-primary-2026")
        republican_runoff = next(row for row in runoff_rows if row["primary_id"] == "TX-9-R-runoff-2026")

        self.assertEqual(republican_primary["status"], "runoff")
        self.assertEqual(republican_primary["runoff_id"], republican_runoff["primary_id"])
        self.assertEqual(republican_primary["runoff_candidate_1"], "Briscoe Cain")
        self.assertEqual(republican_primary["runoff_candidate_2"], "Alex Mealer")
        self.assertEqual(republican_runoff["parent_primary_id"], republican_primary["primary_id"])

    @requires_raw_data
    def test_national_overview_parser_extracts_party_target_flags(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "National.txt").read_text(encoding="utf-8")
        targets, plan = parse_national_targeting(html)

        self.assertTrue(targets["AZ-1"]["dccc_target"])
        self.assertFalse(targets["AZ-1"]["nrcc_target"])
        self.assertNotIn("AZ-01", targets)
        self.assertTrue(targets["CA-47"]["nrcc_target"])
        self.assertEqual(plan["tables"]["dccc"]["expectedColumns"], ["District", "Incumbent", "Winner", "2024 margin"])

    def test_national_overview_parser_extracts_dscc_nrsc_senate_targets(self):
        html = """
        <h2><span id="DSCC_targets">DSCC targets</span></h2>
        <table>
          <tr><th>State</th></tr>
          <tr><td>Florida Class III (special election)</td></tr>
        </table>
        <h2><span id="NRSC_targets">NRSC targets</span></h2>
        <table>
          <tr><th>State</th></tr>
          <tr><td>Ohio Class III (special election)</td></tr>
        </table>
        """
        targets, plan = parse_national_targeting(html)

        self.assertTrue(targets["FL-SEN-C3-SPL"]["dscc_target"])
        self.assertFalse(targets["FL-SEN-C3-SPL"]["nrsc_target"])
        self.assertTrue(targets["OH-SEN-C3-SPL"]["nrsc_target"])
        self.assertFalse(targets["OH-SEN-C3-SPL"]["dscc_target"])
        self.assertEqual(plan["tables"]["dscc"]["headlineId"], "DSCC_targets")
        self.assertEqual(plan["tables"]["nrsc"]["headlineId"], "NRSC_targets")

    @requires_raw_data
    def test_national_overview_parser_extracts_incumbent_departure_tables(self):
        html = (REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw" / "National.txt").read_text(encoding="utf-8")
        by_seat, departures = parse_national_incumbent_tables(html, "https://ballotpedia.org/United_States_House_of_Representatives_elections,_2026")

        self.assertGreater(len(departures), 0)
        tx23 = by_seat["TX-23"]
        self.assertEqual(tx23["incumbent_status"], "defeated_primary")
        self.assertEqual(tx23["incumbent_name"], "Tony Gonzales")
        self.assertEqual(tx23["incumbent_party"], "R")
        self.assertIn("CA-48", by_seat)
        self.assertIn(by_seat["CA-48"]["incumbent_status"], {"retiring", "seeking_other_office", "defeated_primary", "defeated_general"})

    @requires_raw_data
    def test_parse_all_applies_target_flags_to_all_election_rows(self):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        general_rows, primary_rows, runoff_rows, _ = parse_all(fixture_dir)

        ca47_general = next(row for row in general_rows if row["seat"] == "CA-47")
        ca47_primary = next(row for row in primary_rows if row["seat"] == "CA-47")

        self.assertIn("targeting_parse_plan", ca47_general)
        self.assertFalse(ca47_general["dccc_target"])
        self.assertTrue(ca47_general["nrcc_target"])
        self.assertFalse(ca47_primary["dccc_target"])
        self.assertTrue(ca47_primary["nrcc_target"])
        self.assertIsInstance(runoff_rows, list)

    @requires_raw_data
    def test_parse_all_captures_no_filing_primary_reasons(self):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        general_rows, _, _, _ = parse_all(fixture_dir)
        by_seat = {row["seat"]: row for row in general_rows}

        self.assertEqual(by_seat["AL-7"]["primary_reason_r"], "no_filing")
        self.assertEqual(by_seat["AL-7"]["primary_status_r"], "none")
        self.assertEqual(by_seat["LA-2"]["primary_reason_r"], "no_filing")
        self.assertEqual(by_seat["LA-2"]["primary_status_r"], "none")

    @requires_raw_data
    def test_parse_all_enriches_incumbent_and_fec_fields(self):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        general_rows, _, _, _ = parse_all(fixture_dir)
        self.assertEqual(len(general_rows), 435)

        valid_statuses = {
            "running",
            "retiring",
            "seeking_other_office",
            "defeated_primary",
            "defeated_general",
            "vacant_or_unknown",
        }
        for row in general_rows:
            self.assertTrue((row.get("incumbent_name") or "").strip())
            self.assertTrue((row.get("incumbent_party") or "").strip())
            self.assertIn((row.get("incumbent_status") or "").strip(), valid_statuses)
            self.assertIn("fec_incumbent_name", row)
            self.assertIn("fec_incumbent_party", row)
            self.assertIn("fec_incumbent_conflict", row)

    @requires_raw_data
    def test_parse_all_includes_historical_vote_total_maps(self):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        general_rows, _, _, _ = parse_all(fixture_dir)
        tx1 = next(row for row in general_rows if row["seat"] == "TX-1")
        self.assertEqual(set((tx1.get("historical_general_vote_totals") or {}).keys()), {"2024", "2022", "2020"})
        self.assertEqual(set((tx1.get("historical_primary_status") or {}).keys()), {"2024", "2022", "2020"})

    @requires_raw_data
    def test_historical_primary_status_and_totals_are_consistent(self):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        general_rows, _, _, _ = parse_all(fixture_dir)
        allowed_none_reasons = {"no_primary_structure", "no_filing", "unknown"}
        for row in general_rows:
            totals_by_year = row.get("historical_primary_vote_totals") or {}
            status_by_year = row.get("historical_primary_status") or {}
            reason_by_year = row.get("historical_primary_reason") or {}
            for year in ("2024", "2022", "2020"):
                status_map = status_by_year.get(year) or {}
                reason_map = reason_by_year.get(year) or {}
                total_map = totals_by_year.get(year) or {}
                for party in ("D", "R"):
                    status = str(status_map.get(party) or "")
                    if status == "complete":
                        self.assertIn(
                            party,
                            total_map,
                            msg=f"{row.get('seat')} {year} {party} marked complete without total",
                        )
                        self.assertIsInstance(total_map.get(party), int)
                    if status == "none":
                        self.assertNotIn(
                            party,
                            total_map,
                            msg=f"{row.get('seat')} {year} {party} marked none but has total",
                        )
                        reason = str(reason_map.get(party) or "")
                        self.assertIn(
                            reason,
                            allowed_none_reasons,
                            msg=f"{row.get('seat')} {year} {party} none missing valid reason",
                        )

    @requires_raw_data
    def test_parse_national_incumbent_departures_from_fixture_dir(self):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        departures = parse_national_incumbent_departures(fixture_dir)
        self.assertGreater(len(departures), 0)
        self.assertTrue(any((row.get("departure_reason") or "") == "retiring" for row in departures))


if __name__ == "__main__":
    unittest.main()
