import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "build_us_house_seat_debug_view.py"
spec = importlib.util.spec_from_file_location("build_us_house_seat_debug_view", MODULE_PATH)
build_us_house_seat_debug_view = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(build_us_house_seat_debug_view)


class BuildUsHouseSeatDebugViewTests(unittest.TestCase):
    def build_fixture_payloads(self) -> tuple[dict, dict, dict]:
        canonical_payload = {
            "seats": [
                {
                    "seatId": "CA-01",
                    "stateCode": "CA",
                    "districtNumber": 1,
                    "districtCode": "01",
                    "displayName": "California District 1",
                    "districtLabel": "District 1",
                    "election": {
                        "office": "U.S. House",
                        "electionId": "US-HOUSE-2026-CA-01",
                        "electionKind": "general",
                        "status": "active",
                        "candidates": [
                            {
                                "candidateId": "cand-a",
                                "name": "Alice Example",
                                "partyCode": "DEM",
                                "currentElectionStatus": {"code": "general-nominated", "partyCode": "DEM"},
                            },
                            {
                                "candidateId": "cand-b",
                                "name": "Bob Example",
                                "partyCode": "REP",
                                "currentElectionStatus": {"code": "primary-active", "partyCode": "REP"},
                            },
                            {
                                "candidateId": "cand-e",
                                "name": "Eve Example",
                                "partyCode": "REP",
                                "currentElectionStatus": {"code": "primary-active", "partyCode": "REP"},
                            },
                            {
                                "candidateId": "cand-i",
                                "name": "Indy Example",
                                "partyCode": "IND",
                                "currentElectionStatus": {"code": "general-other", "partyCode": "IND"},
                            },
                        ],
                        "children": [
                            {
                                "electionId": "US-HOUSE-2026-CA-01-PRIMARY-DEM",
                                "parentElectionId": "US-HOUSE-2026-CA-01",
                                "electionKind": "primary",
                                "status": "concluded",
                                "partyCode": "DEM",
                                "partyName": "Democratic",
                                "label": "Primary (DEM)",
                                "nomineeCandidateId": "cand-a",
                                "nomineeDisplayName": "Alice Example",
                                "candidates": [
                                    {
                                        "candidateId": "cand-a",
                                        "name": "Alice Example",
                                        "partyCode": "DEM",
                                        "currentElectionStatus": {"code": "general-nominated", "partyCode": "DEM"},
                                    },
                                    {
                                        "candidateId": "cand-f",
                                        "name": "Fran Example",
                                        "partyCode": "DEM",
                                        "currentElectionStatus": {"code": "primary-lost", "partyCode": "DEM"},
                                    },
                                ],
                            },
                            {
                                "electionId": "US-HOUSE-2026-CA-01-PRIMARY-REP",
                                "parentElectionId": "US-HOUSE-2026-CA-01",
                                "electionKind": "primary",
                                "status": "active",
                                "partyCode": "REP",
                                "partyName": "Republican",
                                "label": "Primary (REP)",
                                "nomineeCandidateId": None,
                                "nomineeDisplayName": None,
                                "candidates": [
                                    {
                                        "candidateId": "cand-b",
                                        "name": "Bob Example",
                                        "partyCode": "REP",
                                        "currentElectionStatus": {"code": "primary-active", "partyCode": "REP"},
                                    },
                                    {
                                        "candidateId": "cand-e",
                                        "name": "Eve Example",
                                        "partyCode": "REP",
                                        "currentElectionStatus": {"code": "primary-active", "partyCode": "REP"},
                                    },
                                ],
                            },
                        ],
                    },
                },
                {
                    "seatId": "CA-02",
                    "stateCode": "CA",
                    "districtNumber": 2,
                    "districtCode": "02",
                    "displayName": "California District 2",
                    "districtLabel": "District 2",
                    "election": {
                        "office": "U.S. House",
                        "candidates": [
                            {"candidateId": "cand-c", "name": "Carol Example", "partyCode": "DEM"}
                        ],
                    },
                },
                {
                    "seatId": "CA-03",
                    "stateCode": "CA",
                    "districtNumber": 3,
                    "districtCode": "03",
                    "displayName": "California District 3",
                    "districtLabel": "District 3",
                    "election": {
                        "office": "U.S. House",
                        "candidates": [
                            {"candidateId": "cand-d", "name": "Dana Example", "partyCode": "REP"}
                        ],
                    },
                },
            ]
        }

        ballotpedia_payload = {
            "districtsBySeatId": {
                "CA-01": {
                    "seatId": "CA-01",
                    "stateCode": "CA",
                    "stateName": "California",
                    "districtNumber": 1,
                    "districtLabel": "District 1",
                    "source": {
                        "sourceStateFile": "ballotpedia/california.json",
                        "statePageUrl": "https://example.test/ballotpedia/california",
                    },
                    "election": {
                        "ballotpedia": {
                            "sourceStateFile": "ballotpedia/california.json",
                            "statePageUrl": "https://example.test/ballotpedia/california",
                            "generalElectionCandidateLines": ["Alice Example", "Bob Example"],
                            "advancedFromPrimaryLines": ["Alice Example", "Eve Unmapped"],
                            "generalElectionCandidates": [
                                {"name": "Alice Example", "party": "Democratic"},
                                {"name": "Bob Example", "party": "Republican"},
                            ],
                            "advancedFromPrimary": [
                                {"name": "Alice Example", "party": "Democratic"},
                                {"name": "Eve Unmapped", "party": "Independent"},
                            ],
                        }
                    },
                },
                "CA-99": {
                    "seatId": "CA-99",
                    "stateCode": "CA",
                    "stateName": "California",
                    "districtNumber": 99,
                    "districtLabel": "District 99",
                    "source": {
                        "sourceStateFile": "ballotpedia/extra.json",
                        "statePageUrl": "https://example.test/ballotpedia/extra",
                    },
                    "election": {
                        "ballotpedia": {
                            "generalElectionCandidateLines": ["Orphan Candidate"],
                            "advancedFromPrimaryLines": [],
                        }
                    },
                },
            }
        }

        market_index_payload = {
            "districts": [
                {
                    "seatId": "CA-01",
                    "stateCode": "CA",
                    "districtNumber": 1,
                    "districtCode": "01",
                    "displayName": "California District 1",
                    "districtLabel": "District 1",
                    "marketCount": 1,
                    "markets": [
                        {
                            "ticker": "KXCA01-YES",
                            "sourceFile": "market/ca-01.json",
                            "status": "active",
                        }
                    ],
                },
                {
                    "seatId": "CA-98",
                    "stateCode": "CA",
                    "districtNumber": 98,
                    "districtCode": "98",
                    "displayName": "California District 98",
                    "districtLabel": "District 98",
                    "marketCount": 1,
                    "markets": [
                        {
                            "ticker": "KXCA98-YES",
                            "sourceFile": "market/ca-98.json",
                            "status": "active",
                        }
                    ],
                },
            ]
        }
        return canonical_payload, ballotpedia_payload, market_index_payload

    def build_output(self) -> dict:
        canonical_payload, ballotpedia_payload, market_index_payload = self.build_fixture_payloads()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seat_index_file = root / "us-house-seats.json"
            ballotpedia_input_file = root / "us-house-ballotpedia.json"
            market_index_input_file = root / "us-house-market-index.json"
            output_file = root / "us-house-seat-debug-view.json"

            seat_index_file.write_text(json.dumps(canonical_payload), encoding="utf-8")
            ballotpedia_input_file.write_text(json.dumps(ballotpedia_payload), encoding="utf-8")
            market_index_input_file.write_text(json.dumps(market_index_payload), encoding="utf-8")

            payload = build_us_house_seat_debug_view.build_us_house_seat_debug_view(
                seat_index_file=seat_index_file,
                ballotpedia_input_file=ballotpedia_input_file,
                market_index_input_file=market_index_input_file,
                output_file=output_file,
            )

            written_payload = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(payload, written_payload)
            return payload

    def test_emits_all_canonical_seats_even_when_secondary_sources_are_missing(self):
        payload = self.build_output()

        self.assertEqual(payload["seatCount"], 3)
        self.assertEqual([seat["seatId"] for seat in payload["seats"]], ["CA-01", "CA-02", "CA-03"])

        seats_by_id = {seat["seatId"]: seat for seat in payload["seats"]}
        self.assertIsNotNone(seats_by_id["CA-01"]["sources"]["ballotpedia"])
        self.assertIsNotNone(seats_by_id["CA-01"]["sources"]["kalshi"])
        self.assertIsNone(seats_by_id["CA-02"]["sources"]["ballotpedia"])
        self.assertIsNone(seats_by_id["CA-02"]["sources"]["kalshi"])
        self.assertIsNone(seats_by_id["CA-03"]["sources"]["ballotpedia"])
        self.assertIsNone(seats_by_id["CA-03"]["sources"]["kalshi"])

    def test_populates_source_projections_from_matching_inputs(self):
        payload = self.build_output()
        seat = next(seat for seat in payload["seats"] if seat["seatId"] == "CA-01")

        self.assertEqual(seat["sources"]["congressionalFilings"], seat["election"])
        self.assertEqual(
            seat["sources"]["ballotpedia"]["source"]["sourceStateFile"],
            "ballotpedia/california.json",
        )
        self.assertEqual(
            seat["sources"]["kalshi"]["markets"][0]["ticker"],
            "KXCA01-YES",
        )

    def test_debug_subelections_list_general_and_primary_entries(self):
        payload = self.build_output()
        seat = next(seat for seat in payload["seats"] if seat["seatId"] == "CA-01")

        subelections = seat["debug"]["subelections"]
        self.assertEqual([entry["label"] for entry in subelections], ["General", "Primary (DEM)", "Primary (REP)"])
        self.assertEqual(subelections[0]["status"], "active")
        self.assertEqual(
            [candidate["candidateId"] for candidate in subelections[0]["candidates"]],
            ["cand-a", "cand-i"],
        )

    def test_debug_subelections_put_primary_nominee_first_when_concluded(self):
        payload = self.build_output()
        seat = next(seat for seat in payload["seats"] if seat["seatId"] == "CA-01")

        dem_primary = next(entry for entry in seat["debug"]["subelections"] if entry["label"] == "Primary (DEM)")
        rep_primary = next(entry for entry in seat["debug"]["subelections"] if entry["label"] == "Primary (REP)")

        self.assertEqual(dem_primary["status"], "concluded")
        self.assertEqual(dem_primary["nomineeDisplayName"], "Alice Example")
        self.assertEqual(
            [candidate["candidateId"] for candidate in dem_primary["candidates"]],
            ["cand-a", "cand-f"],
        )
        self.assertEqual(rep_primary["status"], "active")
        self.assertIsNone(rep_primary["nomineeDisplayName"])

    def test_diagnostics_capture_source_presence_and_candidate_mismatches(self):
        payload = self.build_output()
        seats_by_id = {seat["seatId"]: seat for seat in payload["seats"]}

        ca_01_diagnostics = seats_by_id["CA-01"]["diagnostics"]
        self.assertEqual(
            ca_01_diagnostics["sourcePresence"],
            {
                "hasCanonicalElectionData": True,
                "hasBallotpediaData": True,
                "hasKalshiMarketData": True,
            },
        )
        self.assertEqual(
            ca_01_diagnostics["candidateMismatchSummary"]["canonicalCandidateNames"],
            ["Alice Example", "Bob Example", "Eve Example", "Indy Example"],
        )
        self.assertEqual(
            ca_01_diagnostics["candidateMismatchSummary"]["ballotpediaCandidateNames"]["parsedCandidateNames"],
            ["Alice Example", "Bob Example", "Alice Example", "Eve Unmapped"],
        )
        self.assertEqual(
            ca_01_diagnostics["candidateMismatchSummary"]["unmatchedBallotpediaNames"],
            ["Eve Unmapped"],
        )
        self.assertTrue(ca_01_diagnostics["hasIssues"])
        self.assertEqual(ca_01_diagnostics["issueCount"], 1)

        ca_02_presence = seats_by_id["CA-02"]["diagnostics"]["sourcePresence"]
        self.assertEqual(
            ca_02_presence,
            {
                "hasCanonicalElectionData": True,
                "hasBallotpediaData": False,
                "hasKalshiMarketData": False,
            },
        )

    def test_unmapped_ballotpedia_and_kalshi_records_are_retained(self):
        payload = self.build_output()

        ballotpedia_unmapped = payload["unmappedRecords"]["ballotpedia"]
        kalshi_unmapped = payload["unmappedRecords"]["kalshi"]

        self.assertEqual([record["seatId"] for record in ballotpedia_unmapped], ["CA-99"])
        self.assertEqual(ballotpedia_unmapped[0]["sourceStateFile"], "ballotpedia/extra.json")
        self.assertEqual(ballotpedia_unmapped[0]["diagnosticsNote"], "canonical seat missing")

        self.assertEqual([record["seatId"] for record in kalshi_unmapped], ["CA-98"])
        self.assertEqual(kalshi_unmapped[0]["marketTickers"], ["KXCA98-YES"])
        self.assertEqual(kalshi_unmapped[0]["marketSourceFiles"], ["market/ca-98.json"])
        self.assertEqual(kalshi_unmapped[0]["diagnosticsNote"], "canonical seat missing")

    def test_normalize_ballotpedia_districts_accepts_list_payloads(self):
        normalized = build_us_house_seat_debug_view.normalize_ballotpedia_districts({
            "districts": [
                {"stateCode": "AK", "districtNumber": 0, "districtLabel": "At-Large"},
                {"seatId": "CA-01", "stateCode": "CA", "districtNumber": 1, "districtLabel": "District 1"},
            ]
        })

        self.assertEqual(sorted(normalized["records"]), ["AK-AL", "CA-01"])
        self.assertEqual(normalized["records"]["AK-AL"]["districtLabel"], "At-Large")
        self.assertEqual(normalized["malformed"], [])
        self.assertEqual(normalized["missing_seat_id"], [])

    def test_output_json_top_level_shape_is_stable(self):
        payload = self.build_output()

        self.assertEqual(
            sorted(payload.keys()),
            [
                "generatedAt",
                "normalizationIssues",
                "seatCount",
                "seats",
                "sourceFiles",
                "unmappedRecords",
            ],
        )
        self.assertEqual(
            sorted(payload["sourceFiles"].keys()),
            ["ballotpedia", "marketIndex", "output", "seatIndex"],
        )
        self.assertEqual(
            sorted(payload["unmappedRecords"].keys()),
            ["ballotpedia", "kalshi"],
        )
        self.assertEqual(
            sorted(payload["normalizationIssues"].keys()),
            ["ballotpedia", "marketIndex"],
        )
        self.assertEqual(
            sorted(payload["normalizationIssues"]["ballotpedia"].keys()),
            ["duplicateSourceRecords", "malformedSourceRecords", "missingSeatId"],
        )
        self.assertEqual(
            sorted(payload["normalizationIssues"]["marketIndex"].keys()),
            ["duplicateSourceRecords", "malformedSourceRecords", "missingSeatId"],
        )


if __name__ == "__main__":
    unittest.main()
