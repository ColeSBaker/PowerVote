"""Utilities for canonical US Senate seat identifiers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from house_seat_parsing import STATE_CODES

SENATE_SEAT_RE = re.compile(
    r"^(?P<state>[A-Z]{2})-SEN-(?:(?:C(?P<class>[123])(?:-(?P<special>SPL))?)|(?P<sp1>SP1))$",
    flags=re.IGNORECASE,
)

SENATE_CLASS_BY_CYCLE: dict[int, int] = {
    2024: 1,
    2026: 2,
    2028: 3,
    2030: 1,
    2032: 2,
    2034: 3,
}

# Ballotpedia and AP source truth for 2026 special Senate elections.
SPECIAL_SEAT_OVERRIDES: dict[tuple[str, int], str] = {
    ("FL", 2026): "FL-SEN-C3-SPL",
    ("OH", 2026): "OH-SEN-C3-SPL",
}


@dataclass(frozen=True)
class ParsedSenateSeatId:
    seat_id: str
    state_code: str
    senate_class: int | None
    is_special: bool
    is_unbound_special: bool


def normalize_senate_seat_id(raw: str | None) -> str:
    text = str(raw or "").strip().upper()
    match = SENATE_SEAT_RE.match(text)
    if not match:
        raise ValueError(f"Invalid Senate seat_id: {raw}")

    state = match.group("state")
    if state not in STATE_CODES:
        raise ValueError(f"Unknown state code in Senate seat_id: {raw}")

    if match.group("sp1"):
        return f"{state}-SEN-SP1"

    senate_class = match.group("class")
    if not senate_class:
        raise ValueError(f"Missing Senate class in seat_id: {raw}")
    if match.group("special"):
        return f"{state}-SEN-C{senate_class}-SPL"
    return f"{state}-SEN-C{senate_class}"


def parse_senate_seat_id(raw: str | None) -> ParsedSenateSeatId:
    normalized = normalize_senate_seat_id(raw)
    match = SENATE_SEAT_RE.match(normalized)
    if not match:
        raise ValueError(f"Invalid Senate seat_id: {raw}")

    state_code = match.group("state").upper()
    if match.group("sp1"):
        return ParsedSenateSeatId(
            seat_id=normalized,
            state_code=state_code,
            senate_class=None,
            is_special=True,
            is_unbound_special=True,
        )

    senate_class = int(match.group("class"))
    is_special = bool(match.group("special"))
    return ParsedSenateSeatId(
        seat_id=normalized,
        state_code=state_code,
        senate_class=senate_class,
        is_special=is_special,
        is_unbound_special=False,
    )


def senate_class_for_cycle(cycle_year: int) -> int:
    cycle = int(cycle_year)
    known = SENATE_CLASS_BY_CYCLE.get(cycle)
    if known is not None:
        return known
    if cycle < 2024:
        offset = (cycle - 2024) % 6
    else:
        offset = (cycle - 2024) % 6
    # 2024 => class 1, 2026 => class 2, 2028 => class 3
    return (offset // 2) + 1


def infer_senate_seat_id(
    *,
    state_code: str | None,
    cycle_year: int | None,
    is_special: bool = False,
    class_hint: int | None = None,
) -> str | None:
    state = str(state_code or "").strip().upper()
    if state not in STATE_CODES:
        return None
    if cycle_year is None:
        return None

    cycle = int(cycle_year)
    if is_special:
        override = SPECIAL_SEAT_OVERRIDES.get((state, cycle))
        if override:
            return override
        if class_hint in {1, 2, 3}:
            return f"{state}-SEN-C{class_hint}-SPL"
        return f"{state}-SEN-SP1"

    senate_class = class_hint if class_hint in {1, 2, 3} else senate_class_for_cycle(cycle)
    return f"{state}-SEN-C{senate_class}"


def infer_senate_seat_id_from_ticker(
    *,
    ticker: str | None,
    state_code: str | None,
    cycle_year: int | None,
) -> str | None:
    text = str(ticker or "").upper()
    class_hint = None
    class_match = re.search(r"(?:CLASS|C)([123])", text)
    if class_match:
        class_hint = int(class_match.group(1))
    is_special = "SPECIAL" in text or "-SPL" in text or " SP " in f" {text} "
    return infer_senate_seat_id(
        state_code=state_code,
        cycle_year=cycle_year,
        is_special=is_special,
        class_hint=class_hint,
    )
