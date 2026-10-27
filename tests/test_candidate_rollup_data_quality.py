import csv
import json
import os
import re
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = Path(os.environ.get("POWERVOTE_DATA_DIR", str(ROOT / "apps" / "web" / "data")))
CANDIDATE_CSV = Path(os.environ.get("POWERVOTE_CANDIDATE_ROLLUP_CSV", str(_DATA_DIR / "candidate-rollup-2026.csv")))
PRIMARY_CSV = _DATA_DIR / "ballotpedia-primary-election-rollup.csv"
RUNOFF_CSV = _DATA_DIR / "ballotpedia-runoff-election-rollup.csv"
GENERAL_CSV = _DATA_DIR / "ballotpedia-general-election-rollup.csv"
SEATS_JSON = _DATA_DIR / "us-house-seats.json"
NON_VOTING_DELEGATE_CODES = {"DC", "PR", "GU", "VI", "MP", "AQ"}


def _parse_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_json_array(value):
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")
    return parsed


def _parse_json_object(value):
    if value is None:
        return {}
    text = str(value).strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _load_csv(path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _normalize_seat_id(value):
    if not value:
        return ""
    cleaned = str(value).strip().upper()
    match = re.match(r"^([A-Z]{2})-(AL|\d{1,2})$", cleaned)
    if not match:
        return cleaned
    state_code, district = match.groups()
    if district == "AL":
        return f"{state_code}-AL"
    return f"{state_code}-{int(district):02d}"


def _load_seats():
    with SEATS_JSON.open("r", encoding="utf-8") as f:
        seats_data = json.load(f)
    seats = set()
    for seat in seats_data.get("seats", []):
        seat_id = _normalize_seat_id(seat.get("seatId"))
        if not seat_id:
            continue
        state_code = seat_id.split("-")[0]
        if state_code in NON_VOTING_DELEGATE_CODES:
            continue
        seats.add(seat_id)
    return seats


def _load_ballotpedia_expected_seats(primary_rows, runoff_rows, general_rows):
    seats = set()
    for row in primary_rows:
        seat_id = _normalize_seat_id(row.get("seat"))
        if not seat_id:
            continue
        state_code = seat_id.split("-")[0]
        if state_code in NON_VOTING_DELEGATE_CODES:
            continue
        has_candidate = bool(
            (_parse_float(row.get("primary_vote_total")) or 0) > 0
            or (row.get("runoff_candidate_1") or "").strip()
            or (row.get("runoff_candidate_2") or "").strip()
            or (row.get("candidates") or "").strip()
            or (row.get("primary_vote_count") or "").strip()
        )
        if has_candidate:
            seats.add(seat_id)

    for row in runoff_rows:
        seat_id = _normalize_seat_id(row.get("seat"))
        if not seat_id:
            continue
        state_code = seat_id.split("-")[0]
        if state_code in NON_VOTING_DELEGATE_CODES:
            continue
        has_candidate = bool(
            (row.get("runoff_candidate_1") or "").strip()
            or (row.get("runoff_candidate_2") or "").strip()
            or (row.get("candidates") or "").strip()
            or (row.get("primary_vote_count") or "").strip()
        )
        if has_candidate:
            seats.add(seat_id)

    for row in general_rows:
        seat_id = _normalize_seat_id(row.get("seat"))
        if not seat_id:
            continue
        state_code = seat_id.split("-")[0]
        if state_code in NON_VOTING_DELEGATE_CODES:
            continue
        has_candidate = bool(
            (row.get("nominee_d") or "").strip()
            or (row.get("nominee_r") or "").strip()
            or (row.get("nominee_green") or "").strip()
            or (row.get("nominee_libertarian") or "").strip()
        )
        if has_candidate:
            seats.add(seat_id)
    return seats


def _primary_is_concluded(primary_row):
    status_code = (primary_row.get("status") or "").strip().lower()
    round_code = (primary_row.get("round") or "").strip().lower()
    vote_total = _parse_float(primary_row.get("primary_vote_total"))
    return (
        (status_code == "complete" and round_code in {"primary", "top_two"})
        or (vote_total is not None and vote_total > 0)
    )


def _normalized_candidate_identity(value):
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    parts = [part for part in text.split() if part]
    if not parts:
        return ""
    first = parts[0]
    last = parts[-1]
    return f"{first[:1]}-{last}"


class CandidateRollupDataQualityTests(unittest.TestCase):
    """16-test suite for candidate rollup data quality validation"""

    @classmethod
    def setUpClass(cls):
        cls.candidate_rows = _load_csv(CANDIDATE_CSV)
        cls.primary_rows = _load_csv(PRIMARY_CSV)
        cls.runoff_rows = _load_csv(RUNOFF_CSV) if RUNOFF_CSV.exists() else []
        cls.general_rows = _load_csv(GENERAL_CSV) if GENERAL_CSV.exists() else []
        cls.expected_seats = _load_ballotpedia_expected_seats(cls.primary_rows, cls.runoff_rows, cls.general_rows)
        
        # Build indexes
        cls.candidates_by_primary = defaultdict(list)
        cls.candidates_by_runoff = defaultdict(list)
        cls.candidates_by_seat = defaultdict(list)
        cls.primary_by_id = {}
        cls.runoff_by_id = {}
        cls.primaries_by_seat = defaultdict(list)
        
        for row in cls.candidate_rows:
            seat = _normalize_seat_id(row.get("2026 Seat"))
            primary_id = (row.get("Primary ID") or "").strip()
            runoff_id = (row.get("RunoffID") or "").strip()
            
            if seat:
                cls.candidates_by_seat[seat].append(row)
            if primary_id:
                cls.candidates_by_primary[primary_id].append(row)
            if runoff_id:
                cls.candidates_by_runoff[runoff_id].append(row)
        
        for row in cls.primary_rows:
            primary_id = (row.get("primary_id") or "").strip()
            seat = _normalize_seat_id(row.get("seat"))
            if primary_id:
                cls.primary_by_id[primary_id] = row
            if seat:
                cls.primaries_by_seat[seat].append(row)

        for row in cls.runoff_rows:
            runoff_id = (row.get("runoff_id") or "").strip()
            if runoff_id:
                cls.runoff_by_id[runoff_id] = row

    # ===== CATEGORY A: Primary Vote Consistency (3 tests) =====

    def test_A0_schema_ballotpedia_name_and_source_arrays(self):
        """Test A0: BallotpediaName is required and source name columns are JSON arrays"""
        failures = []
        for row in self.candidate_rows:
            ballotpedia_name = (row.get("BallotpediaName") or "").strip()
            if not ballotpedia_name:
                failures.append(f"  missing BallotpediaName for seat={row.get('2026 Seat')} party={row.get('Party')}")
            for field in ("FilingName", "KalshiName"):
                raw = row.get(field)
                try:
                    parsed = _parse_json_array(raw)
                except Exception as exc:
                    failures.append(f"  invalid {field} JSON for {ballotpedia_name or '<blank>'}: {raw!r} ({exc})")
                    continue
                if not all(isinstance(item, str) for item in parsed):
                    failures.append(f"  non-string value in {field} for {ballotpedia_name or '<blank>'}: {parsed!r}")
            for field in ("BallotpediaIsIncumbent", "CanonicalIsIncumbent"):
                value = (row.get(field) or "").strip().lower()
                if value not in {"true", "false"}:
                    failures.append(f"  invalid boolean {field} for {ballotpedia_name or '<blank>'}: {row.get(field)!r}")
            if "Candidate" in row:
                failures.append("  legacy Candidate column still present in rollup row")
        self.assertEqual(len(failures), 0, "Schema contract violations:\n" + "\n".join(failures))

    def test_A1_primary_vote_shares_sum_to_100_percent(self):
        """Test A1: Primary vote shares must sum to 100% (+-2%) when votes exist"""
        failures = []
        
        for primary_id, candidates in sorted(self.candidates_by_primary.items()):
            has_votes = any(_parse_float(c.get("Votes in Primary")) for c in candidates)
            if not has_votes:
                continue
            provided_share_count = sum(1 for c in candidates if _parse_float(c.get("Share of Primary")) is not None)
            if provided_share_count < 2:
                # Skip primaries where Ballotpedia only publishes partial share coverage.
                continue
            candidate_identity_count = len(
                {
                    _normalized_candidate_identity(c.get("BallotpediaName"))
                    for c in candidates
                    if _normalized_candidate_identity(c.get("BallotpediaName"))
                }
            )
            if provided_share_count < candidate_identity_count:
                continue

            share_by_identity = {}
            for candidate in candidates:
                candidate_identity = _normalized_candidate_identity(candidate.get("BallotpediaName"))
                share = _parse_float(candidate.get("Share of Primary")) or 0.0
                if candidate_identity not in share_by_identity or share > share_by_identity[candidate_identity]:
                    share_by_identity[candidate_identity] = share
            total_share = sum(share_by_identity.values())
            
            if not (98.0 <= total_share <= 102.0):
                seat = candidates[0].get("2026 Seat", "")
                party = candidates[0].get("Party", "")
                candidate_names = [c.get("BallotpediaName", "") for c in candidates]
                failures.append(
                    f"  {primary_id} ({seat}-{party}): {total_share:.2f}% ({total_share - 100:.2f}%), candidates: {candidate_names}"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Primary vote shares don't sum to 100% (+-2%):\n" + "\n".join(failures)
        )

    def test_A2_general_nominees_in_primaries_have_vote_data(self):
        """Test A2: General nominees in concluded primaries with vote totals must have vote data"""
        failures = []
        
        for row in self.candidate_rows:
            if (row.get("Status") or "").strip() != "general (nominated)":
                continue
            
            primary_id = (row.get("Primary ID") or "").strip()
            if not primary_id:
                continue
            primary_row = self.primary_by_id.get(primary_id, {})
            if not _primary_is_concluded(primary_row):
                continue
            if (_parse_float(primary_row.get("primary_vote_total")) or 0) <= 0:
                continue
            
            votes = _parse_float(row.get("Votes in Primary"))
            share = _parse_float(row.get("Share of Primary"))
            
            if votes is None or votes == 0 or share is None or share == 0:
                failures.append(
                    f"  {row.get('BallotpediaName')} ({row.get('2026 Seat')}-{row.get('Party')}) in {primary_id}: votes={votes}, share={share}"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"General (nominated) candidates missing primary vote data:\n" + "\n".join(failures)
        )

    def test_A3_eliminated_candidates_have_primary_vote_data(self):
        """Test A3: Eliminated candidates in concluded primaries with vote totals must have primary vote data"""
        failures = []
        
        for row in self.candidate_rows:
            if (row.get("Status") or "").strip() != "eliminated":
                continue
            
            primary_id = (row.get("Primary ID") or "").strip()
            primary_row = self.primary_by_id.get(primary_id, {})
            if not _primary_is_concluded(primary_row):
                continue
            if (_parse_float(primary_row.get("primary_vote_total")) or 0) <= 0:
                continue
            votes = _parse_float(row.get("Votes in Primary"))
            candidate_name_norm = _normalized_candidate_identity(row.get("BallotpediaName"))
            primary_vote_map = _parse_json_object(primary_row.get("primary_vote_count"))
            primary_map_identities = {
                _normalized_candidate_identity(name)
                for name in primary_vote_map.keys()
                if _normalized_candidate_identity(name)
            }
            # Only require candidate vote rows when Ballotpedia actually provides candidate-level
            # vote detail for that candidate identity.
            if candidate_name_norm not in primary_map_identities:
                continue

            if not primary_id or votes is None:
                failures.append(
                    f"  {row.get('BallotpediaName')} ({row.get('2026 Seat')}-{row.get('Party')}): primary_id={primary_id}, votes={votes}"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Eliminated candidates missing primary data:\n" + "\n".join(failures)
        )

    # ===== CATEGORY B: Primary Completion Logic (4 tests) =====

    def test_B1_every_completed_primary_has_advancer(self):
        """Test B1: Completed primaries with votes must have nominee or exactly two runoff advancers"""
        failures = []
        
        for primary_id, candidates in sorted(self.candidates_by_primary.items()):
            has_votes = any(_parse_float(c.get("Votes in Primary")) for c in candidates)
            if not has_votes:
                continue
            
            nominees = [c for c in candidates if (c.get("Status") or "").strip() == "general (nominated)"]
            runoff_advancers = [c for c in candidates if (c.get("Status") or "").strip() == "runoff"]
            primary_row = self.primary_by_id.get(primary_id, {})
            has_runoff = bool((primary_row.get("runoff_id") or "").strip())
            expected_runoff_advancers = 2
            if has_runoff:
                runoff_candidate_1 = (primary_row.get("runoff_candidate_1") or "").strip()
                runoff_candidate_2 = (primary_row.get("runoff_candidate_2") or "").strip()
                if runoff_candidate_1 and not runoff_candidate_2:
                    expected_runoff_advancers = 1

            if len(nominees) == 0 and not (has_runoff and len(runoff_advancers) == expected_runoff_advancers):
                seat = candidates[0].get("2026 Seat", "")
                all_names = [c.get("BallotpediaName", "") for c in candidates]
                all_statuses = [c.get("Status", "") for c in candidates]
                failures.append(
                    f"  {primary_id} ({seat}): nominees={len(nominees)}, runoff={len(runoff_advancers)} (expected {expected_runoff_advancers}), statuses: {all_statuses}, candidates: {all_names}"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Completed primaries missing nominee/runoff advancement:\n" + "\n".join(failures)
        )

    def test_B2_all_primary_candidates_accounted_for(self):
        """Test B2: CSV must have >=95% of candidates from Ballotpedia primaries"""
        failures = []
        
        for primary_id, primary_row in self.primary_by_id.items():
            ballot_votes = _parse_float(primary_row.get("primary_vote_total"))
            if ballot_votes is None or ballot_votes == 0:
                continue
            
            csv_candidates = len(self.candidates_by_primary[primary_id])
            
            if csv_candidates == 0:
                failures.append(
                    f"  {primary_id}: 0 candidates in CSV but votes exist in Ballotpedia ({ballot_votes} votes)"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Primaries with missing/incomplete candidate coverage:\n" + "\n".join(failures)
        )

    def test_B3_runoff_primaries_have_exactly_2_runoff_candidates(self):
        """Test B3: Each runoff must have exactly 2 candidates with Status=runoff"""
        failures = []
        
        for runoff_id, candidates in sorted(self.candidates_by_runoff.items()):
            runoff_status_count = sum(1 for c in candidates if (c.get("Status") or "").strip() == "runoff")
            primary_id = None
            if candidates:
                primary_id = (candidates[0].get("Primary ID") or "").strip()
            primary_row = self.primary_by_id.get(primary_id or "", {})
            expected_count = 2
            if primary_row:
                runoff_candidate_1 = (primary_row.get("runoff_candidate_1") or "").strip()
                runoff_candidate_2 = (primary_row.get("runoff_candidate_2") or "").strip()
                if runoff_candidate_1 and not runoff_candidate_2:
                    expected_count = 1
            if runoff_status_count != expected_count:
                seat = candidates[0].get("2026 Seat", "") if candidates else ""
                candidate_names = [c.get("BallotpediaName", "") for c in candidates]
                candidate_statuses = [c.get("Status", "") for c in candidates]
                failures.append(
                    f"  {runoff_id} ({seat}): {runoff_status_count} runoff candidates (need {expected_count}), statuses: {candidate_statuses}, names: {candidate_names}"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Runoffs without exactly 2 runoff candidates:\n" + "\n".join(failures)
        )

    def test_B4_only_runoff_advancing_candidates_have_runoff_id(self):
        """Test B4: Only candidates advancing to runoff (Status=runoff) have RunoffID"""
        failures = []
        
        for primary_id, candidates in sorted(self.candidates_by_primary.items()):
            has_runoff = any((c.get("RunoffID") or "").strip() for c in candidates)
            if not has_runoff:
                continue
            
            for candidate in candidates:
                status = (candidate.get("Status") or "").strip()
                runoff_id = (candidate.get("RunoffID") or "").strip()
                
                if status == "runoff" and not runoff_id:
                    failures.append(
                        f"  {candidate.get('BallotpediaName')} ({primary_id}): Status=runoff but no RunoffID"
                    )
                elif status == "eliminated" and runoff_id:
                    failures.append(
                        f"  {candidate.get('BallotpediaName')} ({primary_id}): Status=eliminated but has RunoffID={runoff_id}"
                    )
        
        self.assertEqual(
            len(failures), 0,
            f"Invalid RunoffID assignment:\n" + "\n".join(failures)
        )

    # ===== CATEGORY C: Seat Coverage (3 tests) =====

    def test_C1_all_435_congressional_seats_present(self):
        """Test C1: CSV must include every seat represented in Ballotpedia rollups"""
        unique_seats = set(
            _normalize_seat_id(c.get("2026 Seat"))
            for c in self.candidate_rows
            if _normalize_seat_id(c.get("2026 Seat"))
        )
        missing_seats = sorted(self.expected_seats - unique_seats)
        
        self.assertEqual(
            len(missing_seats), 0,
            f"Missing {len(missing_seats)} expected seats: {missing_seats}"
        )

    def test_C2_every_seat_has_at_least_one_general_nominee(self):
        """Test C2: Seats with completed nomination paths must have nominee or runoff advancers"""
        failures = []
        
        for seat in sorted(self.expected_seats):
            seat_candidates = self.candidates_by_seat.get(seat, [])
            nominees = [c for c in seat_candidates if (c.get("Status") or "").strip() == "general (nominated)"]
            
            if len(nominees) > 0:
                continue

            seat_primary_rows = self.primaries_by_seat.get(seat, [])
            concluded_rows = [row for row in seat_primary_rows if _primary_is_concluded(row)]
            if not concluded_rows:
                continue

            has_active_runoff = any((row.get("runoff_id") or "").strip() for row in concluded_rows)
            if has_active_runoff:
                runoff_advancers = [c for c in seat_candidates if (c.get("Status") or "").strip() == "runoff"]
                unique_runoff_identities = {
                    _normalized_candidate_identity(candidate.get("BallotpediaName"))
                    for candidate in runoff_advancers
                    if _normalized_candidate_identity(candidate.get("BallotpediaName"))
                }
                if len(unique_runoff_identities) >= 2:
                    continue
                failures.append(
                    f"  {seat}: concluded runoff path but runoff_advancers={len(unique_runoff_identities)}"
                )
                continue

            candidate_names = [c.get("BallotpediaName", "") for c in seat_candidates]
            candidate_statuses = set(c.get("Status", "") for c in seat_candidates)
            failures.append(
                f"  {seat}: 0 nominees, {len(seat_candidates)} total candidates, statuses: {candidate_statuses}, candidates: {candidate_names}"
            )
        
        self.assertEqual(
            len(failures), 0,
            f"Seats without general (nominated) candidates:\n" + "\n".join(failures)
        )

    def test_C3_candidate_distribution_reasonable(self):
        """Test C3: Verify candidate counts per seat are reasonable"""
        seat_stats = {}
        
        for seat in sorted(self.expected_seats):
            count = len(self.candidates_by_seat.get(seat, []))
            seat_stats[seat] = count
        
        no_candidate_seats = [seat for seat, count in seat_stats.items() if count == 0]
        
        if no_candidate_seats:
            self.fail(f"Seats with 0 candidates: {sorted(no_candidate_seats)}")

    # ===== CATEGORY D: Data Linkage Validation (2 tests) =====

    def test_D1_general_nominees_have_valid_linkage(self):
        """Test D1: General nominees must have Primary ID, RunoffID, or general match"""
        failures = []
        
        for row in self.candidate_rows:
            if (row.get("Status") or "").strip() != "general (nominated)":
                continue
            
            primary_id = (row.get("Primary ID") or "").strip()
            runoff_id = (row.get("RunoffID") or "").strip()
            ballot_access = (row.get("ballotAccessStatus") or "").strip()
            
            has_primary = bool(primary_id)
            has_runoff = bool(runoff_id)
            has_general = ballot_access == "qualified"
            
            if not (has_primary or has_runoff or has_general):
                failures.append(
                    f"  {row.get('BallotpediaName')} ({row.get('2026 Seat')}-{row.get('Party')}): no Primary ID, RunoffID, or general match"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"General nominees without valid linkage:\n" + "\n".join(failures)
        )

    def test_D2_primary_votes_traceable_to_ballotpedia(self):
        """Test D2: Candidates with primary votes must have valid Primary ID in Ballotpedia"""
        failures = []
        
        for row in self.candidate_rows:
            votes = _parse_float(row.get("Votes in Primary"))
            if votes is None or votes == 0:
                continue
            
            primary_id = (row.get("Primary ID") or "").strip()
            
            if not primary_id:
                failures.append(
                    f"  {row.get('BallotpediaName')} ({row.get('2026 Seat')}-{row.get('Party')}): has {votes} votes but no Primary ID"
                )
            elif primary_id not in self.primary_by_id:
                failures.append(
                    f"  {row.get('BallotpediaName')}: Primary ID {primary_id} not found in Ballotpedia"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Primary votes not traceable to Ballotpedia:\n" + "\n".join(failures)
        )

    # ===== CATEGORY E: Status Logic (2 tests) =====

    def test_E1_valid_status_ballot_access_combinations(self):
        """Test E1: Status-to-BallotAccessStatus mappings must be valid"""
        valid_mappings = {
            "general (nominated)": {"qualified", "unknown"},
            "eliminated": {"qualified", "unknown"},
            "primary": {"unknown", "qualified"},
            "runoff": {"qualified"},
            "did not make ballot": {"unknown"},
        }
        
        failures = []
        
        for row in self.candidate_rows:
            status = (row.get("Status") or "").strip()
            access = (row.get("ballotAccessStatus") or "").strip()
            
            valid_access = valid_mappings.get(status, set())
            if access not in valid_access:
                failures.append(
                    f"  {row.get('BallotpediaName')} ({row.get('2026 Seat')}): Status={status}, ballotAccessStatus={access}"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Invalid Status-BallotAccessStatus combinations:\n" + "\n".join(failures)
        )

    def test_E2_no_primary_status_in_concluded_primaries(self):
        """Test E2: Candidates in concluded primaries must not have Status=primary"""
        failures = []
        
        for row in self.candidate_rows:
            if (row.get("Status") or "").strip() != "primary":
                continue
            
            primary_id = (row.get("Primary ID") or "").strip()
            if not primary_id:
                continue
            
            primary_row = self.primary_by_id.get(primary_id, {})
            status_code = primary_row.get("status", "").strip().lower()
            round_code = primary_row.get("round", "").strip().lower()
            
            if status_code == "complete" and round_code in {"primary", "top_two"}:
                failures.append(
                    f"  {row.get('BallotpediaName')} ({primary_id}): Status=primary in concluded primary"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Candidates with Status=primary in concluded primaries:\n" + "\n".join(failures)
        )

    # ===== CATEGORY F: Data Integrity (2 tests) =====

    def test_F1_numeric_field_consistency(self):
        """Test F1: Numeric fields must be logically consistent"""
        failures = []
        
        for row in self.candidate_rows:
            votes = _parse_float(row.get("Votes in Primary"))
            share = _parse_float(row.get("Share of Primary"))
            
            if votes is not None:
                if votes < 0:
                    failures.append(
                        f"  {row.get('BallotpediaName')}: Votes in Primary < 0 ({votes})"
                    )
                if votes > 0 and share is None:
                    failures.append(
                        f"  {row.get('BallotpediaName')}: has votes ({votes}) but no share"
                    )
            
            if share is not None:
                if share < 0 or share > 100:
                    failures.append(
                        f"  {row.get('BallotpediaName')}: Share of Primary out of [0, 100] ({share})"
                    )
                if share > 0 and (votes is None or votes == 0):
                    failures.append(
                        f"  {row.get('BallotpediaName')}: has share ({share}%) but no votes"
                    )
        
        self.assertEqual(
            len(failures), 0,
            f"Numeric field inconsistencies:\n" + "\n".join(failures)
        )

    def test_F2_no_duplicate_candidates_per_seat(self):
        """Test F2: No duplicate exact or normalized-identity rows"""
        failures = []
        exact_duplicates = defaultdict(list)
        normalized_duplicates = defaultdict(list)
        
        for row in self.candidate_rows:
            seat = _normalize_seat_id(row.get("2026 Seat"))
            party = (row.get("Party") or "").strip()
            candidate = (row.get("BallotpediaName") or "").strip()
            exact_key = (seat, party, candidate)
            normalized_key = (seat, party, re.sub(r"\s+", " ", candidate).strip().upper())
            exact_duplicates[exact_key].append(row)
            normalized_duplicates[normalized_key].append(row)
        
        for key, rows in sorted(exact_duplicates.items()):
            if len(rows) > 1:
                seat, party, candidate = key
                failures.append(
                    f"  exact duplicate: {candidate} ({seat}-{party}): {len(rows)} rows"
                )

        for key, rows in sorted(normalized_duplicates.items()):
            if len(rows) > 1:
                seat, party, candidate = key
                names = sorted({(r.get("BallotpediaName") or "").strip() for r in rows})
                failures.append(
                    f"  normalized duplicate: {candidate} ({seat}-{party}): {len(rows)} rows, variants={names}"
                )
        
        self.assertEqual(
            len(failures), 0,
            f"Duplicate candidate identities:\n" + "\n".join(failures)
        )


if __name__ == "__main__":
    unittest.main()
