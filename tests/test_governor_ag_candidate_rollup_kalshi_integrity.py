import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_attorney_general_candidate_rollup as ag_builder
import build_governor_candidate_rollup as gov_builder


def _numeric_map_sum(odds_map: dict) -> tuple[int, float]:
    values = []
    for v in odds_map.values():
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    return len(values), round(sum(values), 2)


def _check_odds_map_sum_range(test_case: unittest.TestCase, rows: list[dict], label: str) -> None:
    flag_by_field = {
        "KalshiPrimaryOddsMap": "KalshiPrimaryOddsMapOutOfBand",
        "KalshiGeneralOddsMap": "KalshiGeneralOddsMapOutOfBand",
    }
    for row in rows:
        for field in ("KalshiPrimaryOddsMap", "KalshiGeneralOddsMap"):
            if row.get(flag_by_field[field]):
                continue
            count, total = _numeric_map_sum(row.get(field) or {})
            if count >= 2:
                test_case.assertTrue(
                    90.0 <= total <= 110.0,
                    msg=f"[{label}] {row.get('2026 Seat')} {row.get('BallotpediaName')} {field} sum={total}",
                )


def _check_out_of_band_flag_consistency(test_case: unittest.TestCase, rows: list[dict], label: str) -> None:
    for row in rows:
        count, total = _numeric_map_sum(row.get("KalshiPrimaryOddsMap") or {})
        if count >= 2 and not (90.0 <= total <= 110.0):
            test_case.assertTrue(
                row.get("KalshiPrimaryOddsMapOutOfBand"),
                msg=f"[{label}] {row.get('2026 Seat')} {row.get('BallotpediaName')} sum={total} but flag not set",
            )


class GovernorKalshiOddsMapIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = gov_builder.build_for_office("ballotpedia-governor")

    def test_candidate_odds_maps_sum_range(self):
        _check_odds_map_sum_range(self, self.rows, "governor")

    def test_out_of_band_flag_set_when_odds_sum_exceeds_threshold(self):
        _check_out_of_band_flag_consistency(self, self.rows, "governor")


class LtGovernorKalshiOddsMapIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = gov_builder.build_for_office("ballotpedia-lieutenant-governor")

    def test_candidate_odds_maps_sum_range(self):
        _check_odds_map_sum_range(self, self.rows, "lt-governor")

    def test_out_of_band_flag_set_when_odds_sum_exceeds_threshold(self):
        _check_out_of_band_flag_consistency(self, self.rows, "lt-governor")


class AttorneyGeneralKalshiOddsMapIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = ag_builder.build_for_office()

    def test_candidate_odds_maps_sum_range(self):
        _check_odds_map_sum_range(self, self.rows, "attorney-general")

    def test_out_of_band_flag_set_when_odds_sum_exceeds_threshold(self):
        _check_out_of_band_flag_consistency(self, self.rows, "attorney-general")


if __name__ == "__main__":
    unittest.main()
