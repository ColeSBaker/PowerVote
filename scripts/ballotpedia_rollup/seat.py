"""Seat and state/district resolution helpers."""
from __future__ import annotations

from pathlib import Path

from senate_seat_ids import infer_senate_seat_id

from .config import ELECTION_CYCLE_YEAR


def parse_seat_from_filename(filename: str | Path, *, office: str = "us_house") -> tuple[str, str, str]:
    stem = Path(filename).stem
    if stem == "National":
        return ("US", "NATIONAL", "NATIONAL")
    if office == "state_governor":
        if stem.endswith("-GOV"):
            state = stem[: -len("-GOV")]
            return (state, "STATEWIDE", f"{state}-GOV")
    if office == "state_lieutenant_governor":
        if stem.endswith("-LTGOV"):
            state = stem[: -len("-LTGOV")]
            return (state, "STATEWIDE", f"{state}-LTGOV")
    if office == "state_attorney_general":
        if stem.endswith("-AG"):
            state = stem[: -len("-AG")]
            return (state, "STATEWIDE", f"{state}-AG")
    if office == "us_senate":
        special = stem.endswith("-SPECIAL")
        state = stem.replace("-SPECIAL", "")
        seat_id = infer_senate_seat_id(
            state_code=state,
            cycle_year=ELECTION_CYCLE_YEAR,
            is_special=special,
        )
        if seat_id:
            return (state, "STATEWIDE", seat_id)
    if "-" in stem:
        state, district = stem.split("-", 1)
        return (state, district, f"{state}-{district}")
    return (stem, "STATE_ROLLUP", stem)
