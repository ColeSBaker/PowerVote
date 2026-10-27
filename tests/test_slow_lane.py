from __future__ import annotations

from tests.slow_lane import is_slow_lane


def test_is_slow_lane_true_for_heavy_integrity_modules() -> None:
    assert is_slow_lane("tests/test_ballotpedia_rollup_parser.py")
    assert is_slow_lane("tests/test_kalshi_integrity_pipeline_checks.py")


def test_is_slow_lane_false_for_fast_unit_modules() -> None:
    assert not is_slow_lane("tests/test_profile_pytest_timings.py")
    assert not is_slow_lane("tests/test_fetch_kalshi_series.py")
