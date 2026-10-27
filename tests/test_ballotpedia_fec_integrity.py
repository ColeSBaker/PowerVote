import csv
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.parser import parse_all
from tests.raw_data import requires_raw_data


@requires_raw_data
class BallotpediaFecIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        cls.general_rows, cls.primary_rows, cls.runoff_rows, _ = parse_all(fixture_dir)
        departures_path = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-incumbent-departures.csv"
        cls.departure_rows = []
        if departures_path.exists():
            with departures_path.open(newline="", encoding="utf-8-sig") as handle:
                cls.departure_rows = list(csv.DictReader(handle))
        cls.departure_seats = {row.get("seat") for row in cls.departure_rows if (row.get("seat") or "").strip()}

    def test_every_ballotpedia_candidate_has_fec_id(self):
        unresolved = []
        ambiguous = 0
        total = 0
        for row in self.primary_rows + self.runoff_rows:
            candidate_names = list(row.get("candidates") or [])
            id_map = row.get("candidate_fec_id_map") or {}
            strategy_map = row.get("candidate_fec_match_strategy_map") or {}
            for name in candidate_names:
                total += 1
                if (id_map.get(name) or "").strip():
                    continue
                if str(strategy_map.get(name) or "") == "ambiguous_fuzzy":
                    ambiguous += 1
                    continue
                unresolved.append((row.get("seat"), row.get("party"), row.get("primary_id"), name, strategy_map.get(name)))
        denominator = max(total - ambiguous, 1)
        unresolved_rate = len(unresolved) / denominator
        self.assertLessEqual(
            unresolved_rate,
            0.05,
            msg=f"Ballotpedia candidates unresolved against FEC exceed threshold: rate={unresolved_rate:.4f}, unresolved={unresolved[:40]} (total={len(unresolved)}, ambiguous={ambiguous}, denominator={denominator})",
        )

    def test_running_or_primary_defeated_incumbent_must_have_fec_incumbent(self):
        bad = []
        for row in self.general_rows:
            status = (row.get("incumbent_status") or "").strip()
            fec_incumbent = (row.get("fec_incumbent_name") or "").strip()
            if status in {"running", "defeated_primary"} and not fec_incumbent:
                bad.append((row.get("seat"), row.get("incumbent_name"), status))
        self.assertEqual(
            bad,
            [],
            msg=f"Seats with running/defeated_primary incumbent but blank FEC incumbent: {bad[:40]} (total={len(bad)})",
        )

    def test_blank_fec_incumbent_requires_departure_or_vacant_status(self):
        bad = []
        for row in self.general_rows:
            fec_incumbent = (row.get("fec_incumbent_name") or "").strip()
            if fec_incumbent:
                continue
            seat = (row.get("seat") or "").strip()
            status = (row.get("incumbent_status") or "").strip()
            if status == "vacant_or_unknown":
                continue
            if seat in self.departure_seats:
                continue
            bad.append((seat, status, row.get("incumbent_name")))
        self.assertEqual(
            bad,
            [],
            msg=f"Blank FEC incumbent without departure record/vacant status: {bad[:40]} (total={len(bad)})",
        )


if __name__ == "__main__":
    unittest.main()
