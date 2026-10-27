from __future__ import annotations

import pytest

from scripts.senate_seat_ids import (
    infer_senate_seat_id,
    infer_senate_seat_id_from_ticker,
    normalize_senate_seat_id,
    parse_senate_seat_id,
    senate_class_for_cycle,
)


def test_normalize_senate_seat_id_accepts_regular_and_special_shapes() -> None:
    assert normalize_senate_seat_id("pa-sen-c2") == "PA-SEN-C2"
    assert normalize_senate_seat_id("oh-sen-c3-spl") == "OH-SEN-C3-SPL"
    assert normalize_senate_seat_id("ak-sen-sp1") == "AK-SEN-SP1"


def test_normalize_senate_seat_id_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        normalize_senate_seat_id("PA-SEN")
    with pytest.raises(ValueError):
        normalize_senate_seat_id("PA-SEN-C4")


def test_parse_senate_seat_id_flags_unbound_special() -> None:
    parsed = parse_senate_seat_id("AK-SEN-SP1")
    assert parsed.state_code == "AK"
    assert parsed.senate_class is None
    assert parsed.is_special is True
    assert parsed.is_unbound_special is True


def test_class_resolution_for_2026_cycle() -> None:
    assert senate_class_for_cycle(2026) == 2
    assert infer_senate_seat_id(state_code="TX", cycle_year=2026) == "TX-SEN-C2"


def test_special_override_resolution_for_2026() -> None:
    assert infer_senate_seat_id(state_code="FL", cycle_year=2026, is_special=True) == "FL-SEN-C3-SPL"
    assert infer_senate_seat_id(state_code="OH", cycle_year=2026, is_special=True) == "OH-SEN-C3-SPL"


def test_ticker_inference_detects_special_and_class_hints() -> None:
    assert (
        infer_senate_seat_id_from_ticker(
            ticker="KXSENATEOH-26-SPECIAL",
            state_code="OH",
            cycle_year=2026,
        )
        == "OH-SEN-C3-SPL"
    )
    assert (
        infer_senate_seat_id_from_ticker(
            ticker="KXSENATEPA-26-C2-R",
            state_code="PA",
            cycle_year=2026,
        )
        == "PA-SEN-C2"
    )
