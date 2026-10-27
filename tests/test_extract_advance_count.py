"""Tests for extract_advance_count and advance_sum_check in kalshi_gov_shared."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "kalshi"))

from kalshi_gov_shared import advance_sum_check, extract_advance_count


# ---------------------------------------------------------------------------
# extract_advance_count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rules, title, expected",
    [
        # Top-four cases
        (
            "If Adam Crum advances to the general election from Alaska's top-four primary for Governor in 2026",
            "",
            4,
        ),
        (
            "",
            "Who will win Alaska's top-four primary for Governor?",
            4,
        ),
        # Top-two cases
        (
            "If Young Kim advances in the CA-40 top 2 primary election in 2026",
            "",
            2,
        ),
        (
            "",
            "Who will advance from the 2026 CA-04 primary?",
            2,
        ),
        (
            "If Antonio Villaraigosa advances to the general election for California governor in 2026",
            "",
            2,
        ),
        # Binary partisan primary (advance_count = 1)
        (
            "If Adam Crum wins the Republican primary nomination for Governor of Alaska in 2026",
            "",
            1,
        ),
        (
            "",
            "Will John Smith win the Democratic primary for Governor?",
            1,
        ),
    ],
)
def test_extract_advance_count(rules: str, title: str, expected: int) -> None:
    assert extract_advance_count(rules, title) == expected


def test_extract_advance_count_top_four_in_title_only() -> None:
    assert extract_advance_count("", "Who wins Alaska's top-four primary?") == 4


def test_extract_advance_count_top_two_hyphenated() -> None:
    assert extract_advance_count("advances from California's top-two primary", "") == 2


def test_extract_advance_count_generic_advance_language() -> None:
    # Generic "advances in the primary" (no top-N number) → conservative 2
    assert extract_advance_count("If Jane Doe advances in the 2026 CA-11 primary", "") == 2


def test_extract_advance_count_no_advance_language_is_1() -> None:
    assert extract_advance_count("wins the primary", "Will X win the primary?") == 1


# ---------------------------------------------------------------------------
# advance_sum_check
# ---------------------------------------------------------------------------

def test_advance_sum_check_within_band_for_top_two() -> None:
    # sum = 225, expected range [160, 240]
    odds_map = {"A": 70.0, "B": 50.0, "C": 45.0, "D": 40.0, "E": 20.0}
    observed, status = advance_sum_check(odds_map, advance_count=2)
    assert status == "ok"
    assert abs(observed - 225.0) < 0.01


def test_advance_sum_check_out_of_band_high_for_top_two() -> None:
    # sum = 255, outside [160, 240]
    odds_map = {"A": 90.0, "B": 85.0, "C": 80.0}
    _, status = advance_sum_check(odds_map, advance_count=2)
    assert status == "out_of_band"


def test_advance_sum_check_out_of_band_low_for_top_two() -> None:
    # sum = 100, outside [160, 240]
    odds_map = {"A": 55.0, "B": 45.0}
    _, status = advance_sum_check(odds_map, advance_count=2)
    assert status == "out_of_band"


def test_advance_sum_check_within_band_for_top_four() -> None:
    # Mimics AK real data: sum = 381, expected range [320, 480]
    odds_map = {
        "Tom Begich": 77.0,
        "Bernadette Wilson": 68.0,
        "Jonathan Kreiss-Tomkins": 49.0,
        "Dave Bronson": 41.0,
        "Treg Taylor": 32.0,
        "Click Bishop": 40.0,
        "Nancy Dahlstrom": 19.0,
        "Shelley Hughes": 14.0,
        "Adam Crum": 10.0,
        "Matt Heilala": 7.0,
        "Edna DeVries": 11.0,
        "Lisa Murkowski": 2.0,
        "Mary Peltola": 2.0,
        "Matthew Claman": 9.0,
    }
    total = sum(odds_map.values())
    observed, status = advance_sum_check(odds_map, advance_count=4)
    assert status == "ok", f"Expected ok (within_band) but sum={total:.1f}"


def test_advance_sum_check_out_of_band_for_top_four() -> None:
    # sum = 500, outside [320, 480]
    odds_map = {f"candidate_{i}": 100.0 for i in range(5)}
    _, status = advance_sum_check(odds_map, advance_count=4)
    assert status == "out_of_band"


def test_advance_sum_check_insufficient_entries() -> None:
    odds_map = {"only_one": 95.0}
    _, status = advance_sum_check(odds_map, advance_count=2)
    assert status == "insufficient_entries"


def test_advance_sum_check_binary_winner_within_band() -> None:
    # Standard binary partisan primary: sum should be ~100, range [80, 120]
    odds_map = {"Alice": 55.0, "Bob": 30.0, "Carol": 15.0}
    _, status = advance_sum_check(odds_map, advance_count=1)
    assert status == "ok"
