import csv
import os
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = Path(os.environ.get("POWERVOTE_DATA_DIR", str(ROOT / "apps" / "web" / "data")))
CANDIDATE_CSV = Path(os.environ.get("POWERVOTE_CANDIDATE_ROLLUP_CSV", str(_DATA_DIR / "candidate-rollup-2026.csv")))
PRIMARY_CSV = _DATA_DIR / "ballotpedia-primary-election-rollup.csv"



def _parse_float(value: str):
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return float(text)


class CandidatePrimaryConsistencyTests(unittest.TestCase):
    def test_primary_share_totals_are_near_100_when_votes_exist(self):
        with CANDIDATE_CSV.open(newline="", encoding="utf-8") as candidate_file:
            candidate_rows = list(csv.DictReader(candidate_file))

        with PRIMARY_CSV.open(newline="", encoding="utf-8") as primary_file:
            primary_rows = list(csv.DictReader(primary_file))

        candidates_by_primary = defaultdict(list)
        for row in candidate_rows:
            primary_id = (row.get("Primary ID") or "").strip()
            if primary_id:
                candidates_by_primary[primary_id].append(row)

        primary_by_id = {}
        for row in primary_rows:
            primary_id = (row.get("primary_id") or "").strip()
            if primary_id:
                primary_by_id[primary_id] = row

        all_primary_ids = sorted(set(candidates_by_primary) | set(primary_by_id))

        for primary_id in all_primary_ids:
            primary_row = primary_by_id.get(primary_id, {})
            candidate_group = candidates_by_primary.get(primary_id, [])

            total_share = 0.0
            parsed_share_count = 0
            has_candidate_primary_votes = False
            candidate_names = []

            for candidate_row in candidate_group:
                candidate_names.append((candidate_row.get("BallotpediaName") or "").strip())

                raw_votes = candidate_row.get("Votes in Primary", "")
                try:
                    parsed_votes = _parse_float(raw_votes)
                except ValueError as exc:
                    self.fail(
                        f"Non-numeric Votes in Primary for primary_id={primary_id}, "
                        f"seat={primary_row.get('seat', candidate_row.get('2026 Seat', ''))}, "
                        f"party={primary_row.get('party', candidate_row.get('Party', ''))}, "
                        f"candidate={candidate_row.get('BallotpediaName', '')!r}, value={raw_votes!r}: {exc}"
                    )
                if parsed_votes is not None:
                    has_candidate_primary_votes = True

                raw_share = candidate_row.get("Share of Primary", "")
                if (raw_share or "").strip():
                    try:
                        parsed_share = float(raw_share)
                    except ValueError as exc:
                        self.fail(
                            f"Share of Primary not parseable as float for primary_id={primary_id}, "
                            f"seat={primary_row.get('seat', candidate_row.get('2026 Seat', ''))}, "
                            f"party={primary_row.get('party', candidate_row.get('Party', ''))}, "
                            f"candidate={candidate_row.get('BallotpediaName', '')!r}, value={raw_share!r}: {exc}"
                        )

                    self.assertGreaterEqual(
                        parsed_share,
                        0.0,
                        msg=(
                            f"Share of Primary < 0 for primary_id={primary_id}, "
                            f"seat={primary_row.get('seat', candidate_row.get('2026 Seat', ''))}, "
                            f"party={primary_row.get('party', candidate_row.get('Party', ''))}, "
                            f"candidate={candidate_row.get('BallotpediaName', '')!r}, value={parsed_share}"
                        ),
                    )
                    self.assertLessEqual(
                        parsed_share,
                        100.0,
                        msg=(
                            f"Share of Primary > 100 for primary_id={primary_id}, "
                            f"seat={primary_row.get('seat', candidate_row.get('2026 Seat', ''))}, "
                            f"party={primary_row.get('party', candidate_row.get('Party', ''))}, "
                            f"candidate={candidate_row.get('BallotpediaName', '')!r}, value={parsed_share}"
                        ),
                    )

                    total_share += parsed_share
                    parsed_share_count += 1

            primary_vote_total = primary_row.get("primary_vote_total", "")
            try:
                parsed_primary_total = _parse_float(primary_vote_total)
            except ValueError as exc:
                self.fail(
                    f"Non-numeric primary_vote_total for primary_id={primary_id}, "
                    f"seat={primary_row.get('seat', '')}, party={primary_row.get('party', '')}, "
                    f"value={primary_vote_total!r}: {exc}"
                )

            has_primary_total_votes = parsed_primary_total is not None and parsed_primary_total > 0
            has_counted_vote_evidence = has_primary_total_votes or has_candidate_primary_votes

            if has_counted_vote_evidence and parsed_share_count:
                if parsed_share_count < 2:
                    continue
                candidate_identity_count = len(
                    {
                        (row.get("BallotpediaName") or "").strip().upper()
                        for row in candidate_group
                        if (row.get("BallotpediaName") or "").strip()
                    }
                )
                if parsed_share_count < candidate_identity_count:
                    continue
                seat = primary_row.get("seat", "") or (candidate_group[0].get("2026 Seat", "") if candidate_group else "")
                party = primary_row.get("party", "") or (candidate_group[0].get("Party", "") if candidate_group else "")
                self.assertLessEqual(
                    abs(total_share - 100.0),
                    2.0,
                    msg=(
                        f"Share of Primary sum out of tolerance for primary_id={primary_id}, "
                        f"seat={seat}, party={party}, computed_sum={total_share:.4f}, "
                        f"candidates={candidate_names}"
                    ),
                )

    def test_runoff_candidates_match_top_two_primary_vote_getters(self):
        with CANDIDATE_CSV.open(newline="", encoding="utf-8") as candidate_file:
            candidate_rows = list(csv.DictReader(candidate_file))
        with PRIMARY_CSV.open(newline="", encoding="utf-8") as primary_file:
            primary_rows = list(csv.DictReader(primary_file))
        primary_by_id = {}
        for row in primary_rows:
            primary_id = (row.get("primary_id") or "").strip()
            if primary_id:
                primary_by_id[primary_id] = row

        candidates_by_primary = defaultdict(list)
        for row in candidate_rows:
            primary_id = (row.get("Primary ID") or "").strip()
            if primary_id:
                candidates_by_primary[primary_id].append(row)

        for primary_id, candidate_group in sorted(candidates_by_primary.items()):
            seat = (candidate_group[0].get("2026 Seat") or "").strip() if candidate_group else ""
            party = (candidate_group[0].get("Party") or "").strip() if candidate_group else ""

            runoff_candidates = [row for row in candidate_group if (row.get("RunoffID") or "").strip()]
            runoff_display = [
                {
                    "candidate": (row.get("BallotpediaName") or "").strip(),
                    "candidate_id": (row.get("CandidateID") or "").strip(),
                    "runoff_id": (row.get("RunoffID") or "").strip(),
                }
                for row in runoff_candidates
            ]

            self.assertLessEqual(
                len(runoff_candidates),
                2,
                msg=(
                    "Expected at most 2 runoff candidates per primary group; "
                    f"primary_id={primary_id}, seat={seat}, party={party}, runoff_list={runoff_display}"
                ),
            )

            vote_rows = []
            for row in candidate_group:
                raw_votes = row.get("Votes in Primary", "")
                try:
                    parsed_votes = _parse_float(raw_votes)
                except ValueError as exc:
                    self.fail(
                        f"Non-numeric Votes in Primary for primary_id={primary_id}, seat={seat}, "
                        f"party={party}, candidate={row.get('BallotpediaName', '')!r}, value={raw_votes!r}: {exc}"
                    )

                if parsed_votes is not None:
                    vote_rows.append(
                        {
                            "candidate": (row.get("BallotpediaName") or "").strip(),
                            "candidate_id": (row.get("CandidateID") or "").strip(),
                            "votes": parsed_votes,
                        }
                    )

            if runoff_candidates and len(vote_rows) >= 2:
                actual_runoff = {
                    ((row.get("BallotpediaName") or "").strip(), (row.get("CandidateID") or "").strip())
                    for row in runoff_candidates
                }

                primary_row = primary_by_id.get(primary_id, {})
                runoff_candidate_1 = (primary_row.get("runoff_candidate_1") or "").strip()
                runoff_candidate_2 = (primary_row.get("runoff_candidate_2") or "").strip()
                expected_from_source = {(name, "") for name in (runoff_candidate_1, runoff_candidate_2) if name}
                if expected_from_source:
                    actual_names = {(name, "") for name, _ in actual_runoff}
                    self.assertSetEqual(
                        actual_names,
                        expected_from_source,
                        msg=(
                            "Runoff candidates do not match Ballotpedia runoff fields; "
                            f"primary_id={primary_id}, seat={seat}, party={party}, "
                            f"runoff_list={runoff_display}, expected={sorted(expected_from_source)}"
                        ),
                    )
                    continue

                sorted_vote_rows = sorted(vote_rows, key=lambda item: item["votes"], reverse=True)
                if len(sorted_vote_rows) >= 3 and sorted_vote_rows[1]["votes"] == sorted_vote_rows[2]["votes"]:
                    self.fail(
                        "Tie detected for runoff qualification boundary (rank 2 and rank 3); "
                        "explicit tie policy required. "
                        f"primary_id={primary_id}, seat={seat}, party={party}, "
                        f"runoff_list={runoff_display}, sorted_votes={sorted_vote_rows}"
                    )

                expected_top_two = {
                    (sorted_vote_rows[0]["candidate"], sorted_vote_rows[0]["candidate_id"]),
                    (sorted_vote_rows[1]["candidate"], sorted_vote_rows[1]["candidate_id"]),
                }
                self.assertSetEqual(
                    actual_runoff,
                    expected_top_two,
                    msg=(
                        "Runoff candidates do not match top two primary vote-getters; "
                        f"primary_id={primary_id}, seat={seat}, party={party}, "
                        f"runoff_list={runoff_display}, sorted_votes={sorted_vote_rows}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
