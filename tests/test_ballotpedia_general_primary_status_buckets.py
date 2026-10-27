import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.parser import parse_all
from tests.raw_data import requires_raw_data


REASON_VALUES = {"", "unopposed", "no_filing", "no_primary_structure", "other"}


def _status_rank(status: str) -> int:
    return {"complete": 4, "runoff": 3, "ongoing": 2, "upcoming": 1, "unknown": 0, "none": -1}.get(status, 0)


@requires_raw_data
class GeneralPrimaryStatusBucketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        general_rows, primary_rows, runoff_rows, _ = parse_all(fixture_dir)
        cls.general_rows = general_rows
        cls.primary_rows = primary_rows
        cls.runoff_rows = runoff_rows
        cls.general_by_seat = {row["seat"]: row for row in general_rows}
        cls.primary_by_id = {row["primary_id"]: row for row in primary_rows}
        cls.runoff_by_id = {row["primary_id"]: row for row in runoff_rows}
        cls.runoff_by_parent = {
            row["parent_primary_id"]: row
            for row in runoff_rows
            if (row.get("parent_primary_id") or "").strip()
        }
        cls.primary_by_seat_party = {}
        for row in primary_rows:
            key = (row["seat"], row["party"])
            existing = cls.primary_by_seat_party.get(key)
            if existing is None or _status_rank(row.get("status", "unknown")) > _status_rank(existing.get("status", "unknown")):
                cls.primary_by_seat_party[key] = row
        cls.runoff_by_seat_party = {}
        for row in runoff_rows:
            key = (row["seat"], row["party"])
            existing = cls.runoff_by_seat_party.get(key)
            if existing is None or _status_rank(row.get("status", "unknown")) > _status_rank(existing.get("status", "unknown")):
                cls.runoff_by_seat_party[key] = row

    @classmethod
    def _resolve_primary_and_runoff(cls, row: dict, lane: str) -> tuple[dict | None, dict | None]:
        lane_lower = lane.lower()
        party = lane.upper()
        primary_id = (row.get(f"primary_id_{lane_lower}") or "").strip()
        primary_row = cls.primary_by_id.get(primary_id)
        runoff_row = cls.runoff_by_id.get(primary_id)

        if primary_row is None:
            if runoff_row is not None:
                parent_id = (runoff_row.get("parent_primary_id") or "").strip()
                if parent_id:
                    primary_row = cls.primary_by_id.get(parent_id)
            if primary_row is None:
                primary_row = cls.primary_by_seat_party.get((row["seat"], party))

        if runoff_row is None and primary_row is not None:
            primary_id_from_row = (primary_row.get("primary_id") or "").strip()
            runoff_id = (primary_row.get("runoff_id") or "").strip()
            if runoff_id:
                runoff_row = cls.runoff_by_id.get(runoff_id)
            if runoff_row is None and primary_id_from_row:
                runoff_row = cls.runoff_by_parent.get(primary_id_from_row)
        if runoff_row is None:
            runoff_row = cls.runoff_by_seat_party.get((row["seat"], party))
        return primary_row, runoff_row

    @classmethod
    def _derive_bucket(cls, row: dict, lane: str) -> str:
        lane_lower = lane.lower()
        status = (row.get(f"primary_status_{lane_lower}") or "").strip().lower()
        reason = (row.get(f"primary_reason_{lane_lower}") or "").strip().lower()
        primary_row, runoff_row = cls._resolve_primary_and_runoff(row, lane)

        if reason == "no_filing":
            return "Canceled (No Filing)"
        if reason == "unopposed":
            return "Canceled (Unopposed)"

        if status == "none":
            return "No Primary (System/Lane Not Held)"

        has_runoff_path = (
            status == "runoff"
            or (primary_row is not None and (primary_row.get("status") == "runoff" or (primary_row.get("runoff_id") or "").strip()))
        )
        if has_runoff_path:
            if runoff_row is not None and (runoff_row.get("status") or "").strip().lower() == "complete":
                return "Runoff (Complete)"
            return "Runoff (Upcoming)"

        if status == "upcoming":
            candidates = list(primary_row.get("candidates") or []) if primary_row is not None else []
            if len(candidates) <= 1 and candidates:
                return "Upcoming (Single Candidate Filed)"
            return "Upcoming (Contested)"

        if status == "complete":
            candidates = list(primary_row.get("candidates") or []) if primary_row is not None else []
            vote_total = primary_row.get("primary_vote_total") if primary_row is not None else None
            if len(candidates) == 1:
                return "Canceled (Unopposed)"
            try:
                if vote_total is not None and float(vote_total) > 0:
                    return "Complete (Votes Cast, Nominated)"
            except (TypeError, ValueError):
                pass
            return "Complete (Votes Cast, Nominated)"

        return "No Primary (System/Lane Not Held)"

    def test_schema_fields_exist_and_are_valid(self):
        self.assertGreater(len(self.general_rows), 0)
        self.assertGreater(len(self.primary_rows), 0)

        for row in self.general_rows:
            self.assertIn("primary_reason_d", row)
            self.assertIn("primary_reason_r", row)
            self.assertIn(str(row.get("primary_reason_d") or "").strip(), REASON_VALUES)
            self.assertIn(str(row.get("primary_reason_r") or "").strip(), REASON_VALUES)

        for row in self.primary_rows:
            self.assertIn("cancellation_reason", row)
            self.assertIn(str(row.get("cancellation_reason") or "").strip(), REASON_VALUES)

    def test_regression_primary_bucket_anchors(self):
        self.assertEqual(self._derive_bucket(self.general_by_seat["AL-7"], "R"), "Canceled (No Filing)")
        self.assertEqual(self._derive_bucket(self.general_by_seat["LA-2"], "R"), "Canceled (No Filing)")
        self.assertIn(
            self._derive_bucket(self.general_by_seat["SC-3"], "R"),
            {"Runoff (Upcoming)", "Upcoming (Single Candidate Filed)"},
        )
        self.assertEqual(self._derive_bucket(self.general_by_seat["TX-23"], "R"), "Runoff (Complete)")
        self.assertEqual(self._derive_bucket(self.general_by_seat["TX-32"], "R"), "Runoff (Complete)")

    def test_reason_buckets_are_not_classified_as_contested(self):
        for row in self.general_rows:
            for lane in ("D", "R"):
                lane_lower = lane.lower()
                reason = (row.get(f"primary_reason_{lane_lower}") or "").strip().lower()
                if reason not in {"no_filing", "unopposed"}:
                    continue
                bucket = self._derive_bucket(row, lane)
                self.assertNotEqual(bucket, "Upcoming (Contested)")

    def test_none_status_always_has_reason(self):
        for row in self.general_rows:
            for lane in ("D", "R"):
                lane_lower = lane.lower()
                status = (row.get(f"primary_status_{lane_lower}") or "").strip().lower()
                reason = (row.get(f"primary_reason_{lane_lower}") or "").strip().lower()
                if status == "none":
                    self.assertIn(reason, {"no_primary_structure", "no_filing", "other"})

    def test_rows_with_primary_ids_resolve_against_primary_or_runoff_rows(self):
        for row in self.general_rows:
            for lane in ("D", "R"):
                lane_lower = lane.lower()
                primary_id = (row.get(f"primary_id_{lane_lower}") or "").strip()
                if not primary_id:
                    continue
                primary_row, runoff_row = self._resolve_primary_and_runoff(row, lane)
                self.assertTrue(primary_row is not None or runoff_row is not None, msg=f"Unresolved primary_id={primary_id}")

                bucket = self._derive_bucket(row, lane)
                if runoff_row is not None and (runoff_row.get("status") or "").strip().lower() == "complete":
                    self.assertEqual(bucket, "Runoff (Complete)")
                elif (primary_row is not None and (primary_row.get("runoff_id") or "").strip()) or (
                    (row.get(f"primary_status_{lane_lower}") or "").strip().lower() == "runoff"
                ):
                    self.assertEqual(bucket, "Runoff (Upcoming)")

    def test_top_two_states_allow_no_primary_lane_buckets(self):
        for seat in ("CA-2", "WA-7", "AK-AL"):
            row = self.general_by_seat[seat]
            self.assertEqual(self._derive_bucket(row, "D"), "No Primary (System/Lane Not Held)")
            self.assertEqual(self._derive_bucket(row, "R"), "No Primary (System/Lane Not Held)")
            self.assertEqual(row.get("primary_reason_d"), "no_primary_structure")
            self.assertEqual(row.get("primary_reason_r"), "no_primary_structure")


if __name__ == "__main__":
    unittest.main()
