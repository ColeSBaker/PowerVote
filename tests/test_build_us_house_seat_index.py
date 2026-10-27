import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_us_house_seat_index.py"
spec = importlib.util.spec_from_file_location("build_us_house_seat_index", MODULE_PATH)
build_us_house_seat_index = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(build_us_house_seat_index)


class BuildUsHouseSeatIndexTests(unittest.TestCase):
    def test_build_candidate_object_initializes_kalshi_name(self):
        candidate = build_us_house_seat_index.build_candidate_object(
            {
                "Cand_Office": "H",
                "Cand_Office_St": "TX",
                "Cand_Office_Dist": "07",
                "Cand_Party_Affiliation": "REP",
                "Cand_Id": "H0TX07000",
                "Cand_Name": "Example, Alice",
            }
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["name"], "Alice Example")
        self.assertIsNone(candidate["kalshiName"])
        self.assertEqual(candidate["aliases"], [])

    def test_classify_candidate_alias_supports_middle_initial_honorific_and_nickname(self):
        self.assertEqual(
            build_us_house_seat_index.classify_candidate_alias("MARLIN A STUTZMAN", "Marlin Stutzman"),
            "middle_initial_only",
        )
        self.assertEqual(
            build_us_house_seat_index.classify_candidate_alias("THOMAS DR. FISHER", "Thomas Fisher"),
            "honorific_or_suffix",
        )
        self.assertEqual(
            build_us_house_seat_index.classify_candidate_alias("JEFFREY HURD", "Jeff Hurd"),
            "nickname",
        )
        self.assertEqual(
            build_us_house_seat_index.classify_candidate_alias("SAMUEL KELLEY FORSTAG", "Sam Forstag"),
            "compound_variation",
        )

    def test_enrich_candidates_with_market_aliases_populates_aliases_and_kalshi_name(self):
        candidates_by_seat = {
            "IN-03": [
                {
                    "candidateId": "1",
                    "name": "MARLIN A STUTZMAN",
                    "kalshiName": None,
                    "aliases": [],
                    "partyCode": "REP",
                    "partyName": "Republican",
                    "seatId": "IN-03",
                    "electionId": "US-HOUSE-2026-IN-03",
                }
            ],
            "CO-03": [
                {
                    "candidateId": "2",
                    "name": "JEFFREY HURD",
                    "kalshiName": None,
                    "aliases": [],
                    "partyCode": "REP",
                    "partyName": "Republican",
                    "seatId": "CO-03",
                    "electionId": "US-HOUSE-2026-CO-03",
                }
            ],
            "MT-01": [
                {
                    "candidateId": "3",
                    "name": "SAMUEL KELLEY FORSTAG",
                    "kalshiName": None,
                    "aliases": [],
                    "partyCode": "DEM",
                    "partyName": "Democratic",
                    "seatId": "MT-01",
                    "electionId": "US-HOUSE-2026-MT-01",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            market_dir = Path(temp_dir) / "market"
            market_dir.mkdir()
            (market_dir / "market_IN03.json").write_text(
                json.dumps(
                    {
                        "event_ticker": "KXINPRIMARY-03R26",
                        "ticker": "KXINPRIMARY-03R26-MSTU",
                        "title": "Will Marlin Stutzman be the Republican nominee for IN-03?",
                        "yes_sub_title": "Marlin Stutzman",
                        "custom_strike": {"Candidate": "Marlin Stutzman", "Party": "Republican"},
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_CO03.json").write_text(
                json.dumps(
                    {
                        "event_ticker": "KXCO03R",
                        "ticker": "KXCO03R-26-JHUR",
                        "title": "Will Jeff Hurd be the Republican nominee for CO-03?",
                        "yes_sub_title": "Jeff Hurd",
                        "custom_strike": {"Candidate": "Jeff Hurd", "Party": "Republican"},
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_MT01.json").write_text(
                json.dumps(
                    {
                        "event_ticker": "KXMT01D",
                        "ticker": "KXMT01D-26-SFOR",
                        "title": "Will Sam Forstag be the Democratic nominee for MT-01?",
                        "yes_sub_title": "Sam Forstag",
                        "custom_strike": {"Candidate": "Sam Forstag", "Party": "Democratic"},
                    }
                ),
                encoding="utf-8",
            )

            enriched = build_us_house_seat_index.enrich_candidates_with_market_aliases(candidates_by_seat, market_dir)

        self.assertEqual(enriched["IN-03"][0]["kalshiName"], "Marlin Stutzman")
        self.assertEqual(enriched["IN-03"][0]["aliases"], ["Marlin Stutzman"])
        self.assertEqual(enriched["CO-03"][0]["kalshiName"], "Jeff Hurd")
        self.assertEqual(enriched["CO-03"][0]["aliases"], ["Jeff Hurd"])
        self.assertEqual(enriched["MT-01"][0]["kalshiName"], "Sam Forstag")
        self.assertEqual(enriched["MT-01"][0]["aliases"], ["Sam Forstag"])

    def test_build_seat_object_normalizes_numbered_and_at_large_districts(self):
        numbered = build_us_house_seat_index.build_seat_object(
            {
                "STATE": "Washington",
                "STATEFP": "53",
                "CD118FP": "02",
                "GEOID": "5302",
                "NAMELSAD": "Congressional District 2",
                "INTPTLAT": "+48.12345",
                "INTPTLON": "-122.12345",
            },
            Path("test_data/maps/Congressional/example.csv"),
        )
        self.assertEqual(numbered["seatId"], "WA-02")
        self.assertEqual(numbered["districtNumber"], 2)
        self.assertFalse(numbered["isAtLarge"])
        self.assertEqual(numbered["marketSeatIdAliases"], ["WA-02"])
        self.assertEqual(numbered["election"]["contentionLabel"], "No Election")

        at_large = build_us_house_seat_index.build_seat_object(
            {
                "STATE": "Vermont",
                "STATEFP": "50",
                "DISTRICT": "AL",
                "GEOID": "5000",
                "NAME": "Vermont At-Large",
            },
            Path("test_data/maps/Congressional/example.csv"),
        )
        self.assertEqual(at_large["seatId"], "VT-AL")
        self.assertTrue(at_large["isAtLarge"])
        self.assertEqual(at_large["marketSeatIdAliases"], ["VT-AL", "VT-REP"])

    def test_build_seat_object_attaches_candidates_and_contention(self):
        seat = build_us_house_seat_index.build_seat_object(
            {
                "STATE": "Texas",
                "STATEFP": "48",
                "CD118FP": "07",
                "GEOID": "4807",
                "NAMELSAD": "Congressional District 7",
            },
            Path("test_data/maps/Congressional/example.csv"),
            {
                "TX-07": [
                    {"candidateId": "1", "name": "Alice Example", "partyCode": "REP", "partyName": "Republican"},
                    {"candidateId": "2", "name": "Bob Example", "partyCode": "REP", "partyName": "Republican"},
                ]
            },
        )

        self.assertEqual(seat["election"]["candidateCount"], 2)
        self.assertEqual(seat["election"]["contentionBucket"], "contested_primary_only")
        self.assertEqual(seat["election"]["candidatesByParty"][0]["partyCode"], "REP")
        self.assertEqual(seat["election"]["nominationStatus"]["primarySystem"], "partisan")
        self.assertEqual(seat["election"]["nominationStatus"]["primaryStatus"], "primary_pending_results")
        self.assertFalse(seat["election"]["nominationStatus"]["pruneToGeneralElectionCandidates"])
        self.assertFalse(seat["election"]["nominationStatus"]["parties"]["REP"]["nomineeKnown"])
        self.assertEqual(seat["election"]["electionKind"], "general")
        self.assertEqual(seat["election"]["status"], "active")
        self.assertEqual(len(seat["election"]["children"]), 1)
        self.assertEqual(seat["election"]["children"][0]["label"], "Primary (REP)")
        self.assertEqual(seat["election"]["children"][0]["status"], "active")
        self.assertEqual(
            [candidate["currentElectionStatus"]["code"] for candidate in seat["election"]["candidates"]],
            ["primary-active", "primary-active"],
        )

    def test_build_seat_object_derives_general_only_nomination_status_conservatively(self):
        seat = build_us_house_seat_index.build_seat_object(
            {
                "STATE": "Texas",
                "STATEFP": "48",
                "CD118FP": "07",
                "GEOID": "4807",
                "NAMELSAD": "Congressional District 7",
            },
            Path("test_data/maps/Congressional/example.csv"),
            {
                "TX-07": [
                    {"candidateId": "1", "name": "Alice Example", "partyCode": "DEM", "partyName": "Democratic"},
                    {"candidateId": "2", "name": "Bob Example", "partyCode": "REP", "partyName": "Republican"},
                ]
            },
        )

        nomination_status = seat["election"]["nominationStatus"]
        self.assertEqual(nomination_status["primaryStatus"], "general_only")
        self.assertEqual(nomination_status["parties"]["DEM"]["nomineeCandidateId"], "1")
        self.assertEqual(nomination_status["parties"]["DEM"]["nomineeDisplayName"], "Alice Example")
        self.assertEqual(nomination_status["parties"]["DEM"]["sourceConfidence"], "low")
        self.assertFalse(nomination_status["parties"]["DEM"]["nominationComplete"])
        self.assertFalse(nomination_status["pruneToGeneralElectionCandidates"])
        self.assertEqual([child["label"] for child in seat["election"]["children"]], ["Primary (DEM)", "Primary (REP)"])
        self.assertEqual([child["status"] for child in seat["election"]["children"]], ["concluded", "concluded"])
        self.assertEqual(
            [candidate["currentElectionStatus"]["code"] for candidate in seat["election"]["candidates"]],
            ["general-nominated", "general-nominated"],
        )
        self.assertEqual(seat["election"]["children"][0]["nomineeDisplayName"], "Alice Example")

    def test_build_seat_object_uses_nonpartisan_branch_for_top_two_states(self):
        seat = build_us_house_seat_index.build_seat_object(
            {
                "STATE": "California",
                "STATEFP": "06",
                "CD118FP": "12",
                "GEOID": "0612",
                "NAMELSAD": "Congressional District 12",
            },
            Path("test_data/maps/Congressional/example.csv"),
            {
                "CA-12": [
                    {"candidateId": "1", "name": "Alice Example", "partyCode": "DEM", "partyName": "Democratic"},
                    {"candidateId": "2", "name": "Bob Example", "partyCode": "REP", "partyName": "Republican"},
                ]
            },
        )

        nomination_status = seat["election"]["nominationStatus"]
        self.assertEqual(nomination_status["primarySystem"], "top_two")
        self.assertEqual(nomination_status["primaryStatus"], "pre_primary")
        self.assertFalse(nomination_status["parties"]["DEM"]["nomineeKnown"])
        self.assertEqual(nomination_status["parties"]["DEM"]["sourceConfidence"], "not_applicable")
        self.assertFalse(nomination_status["pruneToGeneralElectionCandidates"])
        self.assertEqual(seat["election"]["children"], [])
        self.assertEqual(
            [candidate["currentElectionStatus"]["code"] for candidate in seat["election"]["candidates"]],
            ["general-other", "general-other"],
        )

    def test_build_seat_object_only_lists_primary_children_when_party_has_evidence(self):
        seat = build_us_house_seat_index.build_seat_object(
            {
                "STATE": "Texas",
                "STATEFP": "48",
                "CD118FP": "08",
                "GEOID": "4808",
                "NAMELSAD": "Congressional District 8",
            },
            Path("test_data/maps/Congressional/example.csv"),
            {
                "TX-08": [
                    {"candidateId": "1", "name": "Alice Example", "partyCode": "DEM", "partyName": "Democratic"},
                    {"candidateId": "2", "name": "Bob Example", "partyCode": "DEM", "partyName": "Democratic"},
                    {"candidateId": "3", "name": "Indy Example", "partyCode": "IND", "partyName": "Independent"},
                ]
            },
        )

        self.assertEqual([child["label"] for child in seat["election"]["children"]], ["Primary (DEM)"])
        self.assertEqual(
            [candidate["currentElectionStatus"]["code"] for candidate in seat["election"]["candidates"]],
            ["primary-active", "primary-active", "general-other"],
        )

    def test_build_seat_index_reads_csv_and_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "test_data" / "maps" / "Congressional"
            source_dir.mkdir(parents=True)
            source_file = source_dir / "NTAD_Congressional_Districts_-128469763264767056.csv"
            output_file = root / "apps" / "web" / "data" / "us-house-seats.json"

            with source_file.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["STATE", "STATEFP", "CD118FP", "GEOID", "NAMELSAD", "INTPTLAT", "INTPTLON"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "STATE": "Alabama",
                        "STATEFP": "01",
                        "CD118FP": "01",
                        "GEOID": "0101",
                        "NAMELSAD": "Congressional District 1",
                        "INTPTLAT": "+31.0000",
                        "INTPTLON": "-87.0000",
                    }
                )
                writer.writerow(
                    {
                        "STATE": "Delaware",
                        "STATEFP": "10",
                        "CD118FP": "AL",
                        "GEOID": "10AL",
                        "NAMELSAD": "Congressional District At-Large",
                        "INTPTLAT": "+39.0000",
                        "INTPTLON": "-75.0000",
                    }
                )

            payload = build_us_house_seat_index.build_seat_index(
                source_dir=source_dir,
                output_file=output_file,
                candidate_source_file=root / "missing-candidates.csv",
            )
            self.assertEqual(payload["seatCount"], 2)
            self.assertEqual(payload["seats"][0]["seatId"], "AL-01")
            self.assertEqual(payload["seats"][1]["seatId"], "DE-AL")

            written = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(written["seatType"], "US-REP")
            self.assertEqual(written["sourceFile"], str(source_file))
            self.assertEqual(written["seats"][1]["marketSeatIdAliases"], ["DE-AL", "DE-REP"])
            self.assertEqual(written["seats"][0]["election"]["contentionLabel"], "No Election")




    def test_merge_ballotpedia_candidates_respects_top_two_and_low_confidence_states(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ballotpedia_dir = root / "ballotpedia"
            ballotpedia_dir.mkdir()
            (ballotpedia_dir / "California.txt").write_text(
                """State: California
District 1
----------
Notes:
  - Note: The candidate list in this election may not be complete.
General election candidates:
  - Alice Adams (Democratic Party)
  - Bob Brown (Republican Party)
Primary candidates:
  - [No primary sections parsed]
Advanced from primary:
  - [No 'advanced from the primary' text found]
""",
                encoding="utf-8",
            )
            (ballotpedia_dir / "Washington.txt").write_text(
                """State: Washington
No district sections were parsed.
""",
                encoding="utf-8",
            )

            merged = build_us_house_seat_index.merge_ballotpedia_candidates(
                {
                    "CA-01": [
                        {"candidateId": "1", "name": "Alice Adams", "partyCode": "DEM", "partyName": "Democratic"},
                        {"candidateId": "2", "name": "Bob Brown", "partyCode": "REP", "partyName": "Republican"},
                        {"candidateId": "3", "name": "Cara Cruz", "partyCode": "DEM", "partyName": "Democratic"},
                    ],
                    "WA-01": [
                        {"candidateId": "4", "name": "Will West", "partyCode": "DEM", "partyName": "Democratic"},
                    ],
                },
                ballotpedia_dir=ballotpedia_dir,
            )

            self.assertEqual(len(merged["CA-01"]), 3)
            self.assertEqual(merged["WA-01"][0]["name"], "Will West")

    def test_merge_ballotpedia_candidates_prunes_partisan_and_louisiana_cautiously(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ballotpedia_dir = root / "ballotpedia"
            ballotpedia_dir.mkdir()
            (ballotpedia_dir / "Texas.txt").write_text(
                """State: Texas
District 7
----------
Notes:
General election candidates:
  - Alice Adams (Democratic Party)
  - Bob Brown (Republican Party)
Primary candidates:
  Democratic:
    - Alice Adams
    - Carla Cole
  Republican:
    - Bob Brown
    - David Dale
Advanced from primary:
  - Alice Adams (Democratic Party)
  - Bob Brown (Republican Party)
""",
                encoding="utf-8",
            )
            (ballotpedia_dir / "Louisiana.txt").write_text(
                """State: Louisiana
District 3
----------
Notes:
  - Note: The list of general election candidates is incomplete pending results from the primary.
General election candidates:
  - Clay Higgins (Republican Party)
Primary candidates:
  Democratic:
    - Caleb Walker
  Republican:
    - Clay Higgins ✔
Advanced from primary:
  - [No 'advanced from the primary' text found]
""",
                encoding="utf-8",
            )

            merged = build_us_house_seat_index.merge_ballotpedia_candidates(
                {
                    "TX-07": [
                        {"candidateId": "1", "name": "Alice Adams", "partyCode": "DEM", "partyName": "Democratic"},
                        {"candidateId": "2", "name": "Carla Cole", "partyCode": "DEM", "partyName": "Democratic"},
                        {"candidateId": "3", "name": "Bob Brown", "partyCode": "REP", "partyName": "Republican"},
                        {"candidateId": "4", "name": "David Dale", "partyCode": "REP", "partyName": "Republican"},
                    ],
                    "LA-03": [
                        {"candidateId": "5", "name": "Caleb Walker", "partyCode": "DEM", "partyName": "Democratic"},
                        {"candidateId": "6", "name": "Clay Higgins", "partyCode": "REP", "partyName": "Republican"},
                    ],
                },
                ballotpedia_dir=ballotpedia_dir,
            )

            self.assertEqual([candidate["name"] for candidate in merged["TX-07"]], ["Alice Adams", "Bob Brown"])
            self.assertEqual(sorted(candidate["name"] for candidate in merged["LA-03"]), ["Caleb Walker", "Clay Higgins"])

if __name__ == "__main__":
    unittest.main()
