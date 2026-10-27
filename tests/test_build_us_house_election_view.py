from __future__ import annotations

import importlib.util
import json
import unittest
import tempfile
from pathlib import Path
from tests.raw_data import requires_raw_data


REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_MODULE_PATH = REPO_ROOT / "scripts" / "build_us_house_election_view.py"
view_spec = importlib.util.spec_from_file_location("build_us_house_election_view", VIEW_MODULE_PATH)
build_us_house_election_view = importlib.util.module_from_spec(view_spec)
assert view_spec and view_spec.loader
view_spec.loader.exec_module(build_us_house_election_view)

SEAT_INDEX_MODULE_PATH = REPO_ROOT / "scripts" / "build_us_house_seat_index.py"
seat_spec = importlib.util.spec_from_file_location("build_us_house_seat_index", SEAT_INDEX_MODULE_PATH)
build_us_house_seat_index = importlib.util.module_from_spec(seat_spec)
assert seat_spec and seat_spec.loader
seat_spec.loader.exec_module(build_us_house_seat_index)

PARSE_MODULE_PATH = REPO_ROOT / "scripts" / "parse_ballotpedia_house_text.py"
parse_spec = importlib.util.spec_from_file_location("parse_ballotpedia_house_text", PARSE_MODULE_PATH)
parse_ballotpedia_house_text = importlib.util.module_from_spec(parse_spec)
assert parse_spec and parse_spec.loader
parse_spec.loader.exec_module(parse_ballotpedia_house_text)

FIXTURE_DIR = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "output_house_text"
SEAT_DATA = json.loads((REPO_ROOT / "apps" / "web" / "data" / "us-house-seats.json").read_text(encoding="utf-8"))
SEATS_BY_ID = {seat["seatId"]: seat for seat in SEAT_DATA["seats"]}


def parse_line_candidate(line: str) -> dict:
    candidate = build_us_house_seat_index.parse_ballotpedia_candidate_entry(line)
    if candidate is not None:
        return {"name": candidate["name"], "party": candidate.get("party")}
    return {"name": line, "party": None}


def ballotpedia_input_for(seat_id: str, state_file: str) -> dict:
    records, _ = parse_ballotpedia_house_text.parse_state_file(FIXTURE_DIR / state_file)
    record = next(item for item in records if item["seatId"] == seat_id)
    ballotpedia = record["election"]["ballotpedia"]
    return {
        "seatId": seat_id,
        "notes": ballotpedia["notes"],
        "parseQuality": "low" if "contains_scrape_garbage" in ballotpedia["scrapeQualityFlags"] else "high",
        "generalElectionCandidates": [parse_line_candidate(line) for line in ballotpedia["generalElectionCandidateLines"]],
        "advancedFromPrimary": [parse_line_candidate(line) for line in ballotpedia["advancedFromPrimaryLines"] if not line.startswith("[No ")],
    }


@requires_raw_data
class BuildUsHouseElectionViewFixtureTests(unittest.TestCase):
    def assert_display(self, seat_id: str, state_file: str, expected_primary_status: str, expected_mode: str, expected_ids: list[str]):
        canonical_candidates = SEATS_BY_ID[seat_id]["election"]["candidates"]
        ballotpedia = ballotpedia_input_for(seat_id, state_file)

        mode, display_candidates, diagnostics = build_us_house_election_view.infer_display_mode(ballotpedia, canonical_candidates)

        self.assertEqual(SEATS_BY_ID[seat_id]["election"]["nominationStatus"]["primaryStatus"], expected_primary_status)
        self.assertEqual(mode, expected_mode)
        self.assertEqual([candidate["candidateId"] for candidate in display_candidates], expected_ids)
        self.assertIsInstance(diagnostics["matchedGeneralElectionCount"], int)

    def test_texas_normal_partisan_primary_district_stays_in_all_filed_mode(self):
        seat = SEATS_BY_ID["TX-07"]
        self.assert_display(
            "TX-07",
            "Texas.txt",
            expected_primary_status="primary_pending_results",
            expected_mode="all_filed_candidates",
            expected_ids=[candidate["candidateId"] for candidate in seat["election"]["candidates"]],
        )

    def test_california_missing_primary_sections_remains_pre_primary(self):
        seat = SEATS_BY_ID["CA-01"]
        self.assert_display(
            "CA-01",
            "California.txt",
            expected_primary_status="pre_primary",
            expected_mode="all_filed_candidates",
            expected_ids=[candidate["candidateId"] for candidate in seat["election"]["candidates"]],
        )

    def test_district_with_none_parsed_general_candidates_keeps_all_filed_candidates(self):
        seat = SEATS_BY_ID["LA-01"]
        self.assert_display(
            "LA-01",
            "Louisiana.txt",
            expected_primary_status="pre_primary",
            expected_mode="all_filed_candidates",
            expected_ids=[candidate["candidateId"] for candidate in seat["election"]["candidates"]],
        )

    def test_low_quality_ballotpedia_scrape_garbage_disables_general_only_pruning(self):
        seat = SEATS_BY_ID["LA-06"]
        self.assert_display(
            "LA-06",
            "Louisiana.txt",
            expected_primary_status="pre_primary",
            expected_mode="all_filed_candidates",
            expected_ids=[candidate["candidateId"] for candidate in seat["election"]["candidates"]],
        )


class CanonicalElectionStatusDisplayTests(unittest.TestCase):
    def test_uses_canonical_statuses_to_hide_active_primary_candidates_from_general_display(self):
        canonical_election = {
            "candidates": [
                {
                    "candidateId": "cand-a",
                    "name": "Alice Example",
                    "partyCode": "DEM",
                    "currentElectionStatus": {"code": "primary-active", "partyCode": "DEM"},
                },
                {
                    "candidateId": "cand-b",
                    "name": "Bob Example",
                    "partyCode": "REP",
                    "currentElectionStatus": {"code": "general-nominated", "partyCode": "REP"},
                },
                {
                    "candidateId": "cand-c",
                    "name": "Carol Example",
                    "partyCode": "IND",
                    "currentElectionStatus": {"code": "general-other", "partyCode": "IND"},
                },
            ],
            "children": [
                {
                    "electionId": "US-HOUSE-2026-CA-01-PRIMARY-DEM",
                    "parentElectionId": "US-HOUSE-2026-CA-01",
                    "electionKind": "primary",
                    "status": "active",
                    "partyCode": "DEM",
                    "partyName": "Democratic",
                    "label": "Primary (DEM)",
                    "candidates": [
                        {
                            "candidateId": "cand-a",
                            "name": "Alice Example",
                            "partyCode": "DEM",
                            "currentElectionStatus": {"code": "primary-active", "partyCode": "DEM"},
                        }
                    ],
                    "nomineeCandidateId": None,
                    "nomineeDisplayName": None,
                }
            ],
        }

        mode, display_candidates, diagnostics = build_us_house_election_view.infer_display_mode({}, canonical_election)

        self.assertEqual(mode, "general_election_only")
        self.assertEqual([candidate["candidateId"] for candidate in display_candidates], ["cand-b", "cand-c"])
        self.assertTrue(diagnostics["usedCanonicalElectionStatuses"])
        self.assertEqual(diagnostics["canonicalPrimaryElectionCount"], 1)

    def test_returns_primary_only_when_no_candidates_have_general_status(self):
        canonical_election = {
            "candidates": [
                {
                    "candidateId": "cand-a",
                    "name": "Alice Example",
                    "partyCode": "DEM",
                    "currentElectionStatus": {"code": "primary-active", "partyCode": "DEM"},
                },
                {
                    "candidateId": "cand-b",
                    "name": "Bob Example",
                    "partyCode": "DEM",
                    "currentElectionStatus": {"code": "primary-active", "partyCode": "DEM"},
                },
            ],
            "children": [
                {
                    "electionId": "US-HOUSE-2026-CA-01-PRIMARY-DEM",
                    "parentElectionId": "US-HOUSE-2026-CA-01",
                    "electionKind": "primary",
                    "status": "active",
                    "partyCode": "DEM",
                    "partyName": "Democratic",
                    "label": "Primary (DEM)",
                    "candidates": [],
                    "nomineeCandidateId": None,
                    "nomineeDisplayName": None,
                }
            ],
        }

        mode, display_candidates, diagnostics = build_us_house_election_view.infer_display_mode({}, canonical_election)

        self.assertEqual(mode, "primary_only")
        self.assertEqual(display_candidates, [])
        self.assertTrue(diagnostics["usedCanonicalElectionStatuses"])


class NormalizeBallotpediaPayloadTests(unittest.TestCase):
    def test_accepts_districts_by_seat_id_payload_and_flattens_nested_election_data(self):
        payload = {
            "generatedAt": "2026-03-19T00:00:00Z",
            "districtCount": 1,
            "stateFiles": ["California.json"],
            "districtsBySeatId": {
                "CA-01": {
                    "seatId": "CA-01",
                    "stateCode": "CA",
                    "districtNumber": 1,
                    "districtLabel": "District 1",
                    "source": {"sourceStateFile": "California.json"},
                    "election": {
                        "ballotpedia": {
                            "generalElectionCandidates": [
                                {"name": "Alice Example", "party": "Democratic"},
                                {"name": "Bob Example", "party": "Republican"},
                            ],
                            "notes": ["Candidate list complete."],
                        }
                    },
                }
            },
        }

        normalized = build_us_house_election_view.normalize_ballotpedia_payload(payload)

        self.assertEqual(list(normalized), ["CA-01"])
        self.assertEqual(normalized["CA-01"]["districtLabel"], "District 1")
        self.assertEqual(normalized["CA-01"]["source"]["sourceStateFile"], "California.json")
        self.assertEqual(
            [candidate["name"] for candidate in normalized["CA-01"]["generalElectionCandidates"]],
            ["Alice Example", "Bob Example"],
        )

    def test_accepts_list_payloads_and_normalizes_seat_id_from_state_and_district(self):
        payload = {
            "districts": [
                {
                    "stateCode": "AK",
                    "districtNumber": 0,
                    "generalElectionCandidates": [{"name": "At Large Example", "party": "Independent"}],
                }
            ]
        }

        normalized = build_us_house_election_view.normalize_ballotpedia_payload(payload)

        self.assertEqual(list(normalized), ["AK-AL"])
        self.assertEqual(normalized["AK-AL"]["generalElectionCandidates"][0]["name"], "At Large Example")


class BuildUsHouseElectionViewIntegrationTests(unittest.TestCase):
    def test_build_reads_current_ballotpedia_export_shape(self):
        canonical_payload = {
            "seats": [
                {
                    "seatId": "CA-01",
                    "election": {
                        "candidates": [
                            {
                                "candidateId": "cand-a",
                                "name": "Alice Example",
                                "partyCode": "DEM",
                                "currentElectionStatus": {"code": "primary-active", "partyCode": "DEM"},
                            },
                            {
                                "candidateId": "cand-b",
                                "name": "Bob Example",
                                "partyCode": "REP",
                                "currentElectionStatus": {"code": "general-nominated", "partyCode": "REP"},
                            },
                            {
                                "candidateId": "cand-c",
                                "name": "Carol Example",
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
                                    }
                                ],
                            }
                        ],
                    },
                }
            ]
        }
        ballotpedia_payload = {
            "generatedAt": "2026-03-19T00:00:00Z",
            "districtCount": 1,
            "stateFiles": ["California.json"],
            "districtsBySeatId": {
                "CA-01": {
                    "seatId": "CA-01",
                    "stateCode": "CA",
                    "districtNumber": 1,
                    "districtLabel": "District 1",
                    "source": {"sourceStateFile": "California.json"},
                    "election": {
                        "ballotpedia": {
                            "generalElectionCandidates": [
                                {"name": "Alice Example", "party": "Democratic"},
                                {"name": "Bob Example", "party": "Republican"},
                            ]
                        }
                    },
                }
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seat_index_file = root / "us-house-seats.json"
            ballotpedia_input_file = root / "us-house-ballotpedia.json"
            output_file = root / "us-house-election-view.json"
            seat_index_file.write_text(json.dumps(canonical_payload), encoding="utf-8")
            ballotpedia_input_file.write_text(json.dumps(ballotpedia_payload), encoding="utf-8")

            payload = build_us_house_election_view.build_us_house_election_view(
                seat_index_file=seat_index_file,
                ballotpedia_input_file=ballotpedia_input_file,
                output_file=output_file,
            )

        seat = payload["seats"][0]
        self.assertEqual(payload["ballotpediaInputFile"], str(ballotpedia_input_file))
        self.assertEqual(seat["election"]["displayMode"], "general_election_only")
        self.assertEqual(
            [candidate["candidateId"] for candidate in seat["election"]["displayCandidates"]],
            ["cand-b", "cand-c"],
        )
        self.assertEqual(seat["election"]["ballotpedia"]["sourceFile"], "California.json")
        self.assertEqual(seat["election"]["primaryElections"][0]["label"], "Primary (DEM)")
        self.assertEqual(seat["election"]["primaryElections"][0]["displayCandidates"][0]["candidateId"], "cand-a")

    def test_build_backfills_primary_elections_from_primary_rollup_when_canonical_children_missing(self):
        canonical_payload = {
            "seats": [
                {
                    "seatId": "CA-01",
                    "election": {
                        "candidates": [
                            {
                                "candidateId": "cand-a",
                                "name": "Alice Example",
                                "partyCode": "DEM",
                                "currentElectionStatus": {"code": "primary-active", "partyCode": "DEM"},
                            }
                        ],
                        "children": [],
                    },
                }
            ]
        }
        ballotpedia_payload = {"districtsBySeatId": {}}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seat_index_file = root / "us-house-seats.json"
            ballotpedia_input_file = root / "us-house-ballotpedia.json"
            primary_rollup_file = root / "ballotpedia-primary-election-rollup.csv"
            output_file = root / "us-house-election-view.json"
            seat_index_file.write_text(json.dumps(canonical_payload), encoding="utf-8")
            ballotpedia_input_file.write_text(json.dumps(ballotpedia_payload), encoding="utf-8")
            primary_rollup_file.write_text(
                "\n".join(
                    [
                        "seat,party,primary_id,status,candidates,candidate_party_map",
                        'CA-1,NPA,CA-1-NP-primary-2026,upcoming,"[""Alice Example"",""Bob Example""]","{""Alice Example"":""DEM"",""Bob Example"":""REP""}"',
                    ]
                ),
                encoding="utf-8",
            )

            payload = build_us_house_election_view.build_us_house_election_view(
                seat_index_file=seat_index_file,
                ballotpedia_input_file=ballotpedia_input_file,
                primary_rollup_file=primary_rollup_file,
                output_file=output_file,
            )

        seat = payload["seats"][0]
        self.assertEqual(len(seat["election"]["primaryElections"]), 1)
        primary = seat["election"]["primaryElections"][0]
        self.assertEqual(primary["electionId"], "CA-1-NP-primary-2026")
        self.assertEqual(primary["partyCode"], "NPA")
        self.assertEqual(primary["candidateCount"], 2)
        self.assertEqual(primary["displayCandidates"][0]["name"], "Alice Example")


if __name__ == "__main__":
    unittest.main()
