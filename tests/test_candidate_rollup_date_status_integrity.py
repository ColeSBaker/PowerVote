import csv
import json
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_CSV = ROOT / "apps" / "web" / "data" / "candidate-rollup-2026.csv"
PRIMARY_CSV = ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.csv"
RUNOFF_CSV = ROOT / "apps" / "web" / "data" / "ballotpedia-runoff-election-rollup.csv"
GENERAL_CSV = ROOT / "apps" / "web" / "data" / "ballotpedia-general-election-rollup.csv"
SNAPSHOT_DATE_FILE = ROOT / "apps" / "web" / "data" / "rollup-snapshot-date.txt"


def _load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_int(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_date(value: str | None):
    text = (value or "").strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


def _parse_map(value: str | None) -> dict[str, int]:
    text = (value or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        return {}
    output = {}
    for k, v in parsed.items():
        try:
            output[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return output


def _normalize_name(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    return "".join(ch if ch.isalnum() else " " for ch in text).split()


class CandidateRollupDateStatusIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate_rows = _load_csv(CANDIDATE_CSV)
        cls.primary_rows = _load_csv(PRIMARY_CSV)
        cls.runoff_rows = _load_csv(RUNOFF_CSV)
        cls.general_rows = _load_csv(GENERAL_CSV)
        cls.snapshot_date = _parse_date(SNAPSHOT_DATE_FILE.read_text(encoding="utf-8").strip())
        cls.primary_by_id = {(row.get("primary_id") or "").strip(): row for row in cls.primary_rows if (row.get("primary_id") or "").strip()}
        cls.runoff_by_id = {(row.get("primary_id") or "").strip(): row for row in cls.runoff_rows if (row.get("primary_id") or "").strip()}
        cls.general_by_seat = {(row.get("seat") or "").strip(): row for row in cls.general_rows if (row.get("seat") or "").strip()}

    def _primary_concluded(self, primary_row: dict | None) -> bool:
        if not primary_row:
            return False
        primary_status = (primary_row.get("status") or "").strip().lower()
        primary_round = (primary_row.get("round") or "").strip().lower()
        primary_date = _parse_date(primary_row.get("primary_date"))
        if not primary_date or primary_date > self.snapshot_date:
            return False
        if primary_status == "runoff":
            return True
        if primary_status == "complete" and primary_round in {"primary", "top_two"}:
            return True
        primary_vote_total = _parse_int(primary_row.get("primary_vote_total")) or 0
        return primary_vote_total > 0

    def test_snapshot_date_is_repo_controlled(self):
        self.assertIsNotNone(self.snapshot_date)

    def test_candidate_round_dates_propagate_from_rollups(self):
        failures = []
        for row in self.candidate_rows:
            primary_id = (row.get("Primary ID") or "").strip()
            runoff_id = (row.get("RunoffID") or "").strip()
            seat = (row.get("2026 Seat") or "").strip()

            if primary_id:
                primary_row = self.primary_by_id.get(primary_id)
                if primary_row:
                    expected = (primary_row.get("primary_date") or "").strip()
                    observed = (row.get("primaryDate") or "").strip()
                    if expected != observed:
                        failures.append(f"{primary_id}: expected primaryDate={expected}, got {observed}")
            if runoff_id:
                runoff_row = self.runoff_by_id.get(runoff_id)
                expected = (runoff_row.get("runoff_date") or "").strip() if runoff_row else ""
                observed = (row.get("runoffDate") or "").strip()
                if expected and expected != observed:
                    failures.append(f"{runoff_id}: expected runoffDate={expected}, got {observed}")
            general_row = self.general_by_seat.get(seat)
            if general_row:
                expected_general = (general_row.get("general_date") or "").strip()
                observed_general = (row.get("generalDate") or "").strip()
                if expected_general and expected_general != observed_general:
                    failures.append(f"{seat}: expected generalDate={expected_general}, got {observed_general}")

        self.assertEqual([], failures, "Candidate round dates do not match rollup dates:\n" + "\n".join(failures[:80]))

    def test_no_primary_votes_before_primary_date(self):
        failures = []
        for row in self.candidate_rows:
            votes = _parse_int(row.get("Votes in Primary"))
            if votes is None:
                continue
            primary_date = _parse_date(row.get("primaryDate"))
            if primary_date is None or primary_date > self.snapshot_date:
                failures.append(f"{row.get('BallotpediaName')} ({row.get('Primary ID')}): votes={votes}, primaryDate={row.get('primaryDate')}")
        self.assertEqual([], failures, "Primary votes present before primary date:\n" + "\n".join(failures[:80]))

    def test_no_runoff_votes_before_runoff_date(self):
        failures = []
        for row in self.candidate_rows:
            votes = _parse_int(row.get("Votes in Runoff"))
            if votes is None:
                continue
            runoff_date = _parse_date(row.get("runoffDate"))
            if runoff_date is None or runoff_date > self.snapshot_date:
                failures.append(f"{row.get('BallotpediaName')} ({row.get('RunoffID')}): votes={votes}, runoffDate={row.get('runoffDate')}")
        self.assertEqual([], failures, "Runoff votes present before runoff date:\n" + "\n".join(failures[:80]))

    def test_primary_vote_counts_exactly_match_primary_rollup(self):
        failures = []
        for row in self.candidate_rows:
            primary_id = (row.get("Primary ID") or "").strip()
            if not primary_id:
                continue
            primary_row = self.primary_by_id.get(primary_id)
            if not primary_row:
                continue
            votes_map = _parse_map(primary_row.get("primary_vote_count"))
            candidate_votes = _parse_int(row.get("Votes in Primary"))
            candidate_name = (row.get("BallotpediaName") or "").strip()
            normalized_target = " ".join(_normalize_name(candidate_name))

            expected = None
            for map_name, map_votes in votes_map.items():
                if " ".join(_normalize_name(map_name)) == normalized_target:
                    expected = int(map_votes)
                    break

            if expected is None and candidate_votes is not None:
                failures.append(f"{candidate_name} ({primary_id}) has synthetic votes={candidate_votes} with no primary_vote_count entry")
            if expected is not None and candidate_votes != expected:
                failures.append(f"{candidate_name} ({primary_id}) expected votes={expected}, got {candidate_votes}")

        self.assertEqual([], failures, "Primary vote parity mismatch:\n" + "\n".join(failures[:80]))

    def test_status_is_coherent_with_primary_lifecycle(self):
        failures = []
        for row in self.candidate_rows:
            primary_id = (row.get("Primary ID") or "").strip()
            if not primary_id:
                continue
            primary_row = self.primary_by_id.get(primary_id)
            if not primary_row:
                continue
            status = (row.get("Status") or "").strip()
            concluded = self._primary_concluded(primary_row)
            cancellation_reason = (primary_row.get("cancellation_reason") or "").strip().lower()

            if not concluded:
                if status == "eliminated":
                    failures.append(f"{row.get('BallotpediaName')} ({primary_id}) is eliminated before primary concluded")
                if status == "runoff":
                    failures.append(f"{row.get('BallotpediaName')} ({primary_id}) is runoff before primary concluded")
                if status == "general (nominated)" and cancellation_reason != "unopposed":
                    failures.append(
                        f"{row.get('BallotpediaName')} ({primary_id}) nominated before primary concluded without unopposed cancellation"
                    )
            else:
                if status == "primary":
                    failures.append(f"{row.get('BallotpediaName')} ({primary_id}) remains primary after conclusion")

        self.assertEqual([], failures, "Candidate status/primary-lifecycle mismatch:\n" + "\n".join(failures[:120]))


if __name__ == "__main__":
    unittest.main()
