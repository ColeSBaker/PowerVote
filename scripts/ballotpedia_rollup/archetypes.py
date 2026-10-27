"""Page archetype detection for raw Ballotpedia HTML snapshots."""
from __future__ import annotations

from enum import Enum

from .config import ELECTION_CYCLE_YEAR
from .html_utils import contains_class, find_anchor_ids
from .meta import extract_title


class Archetype(str, Enum):
    DISTRICT_DETAIL = "district_detail"
    STATE_ROLLUP = "state_rollup"
    NATIONAL_OVERVIEW = "national_overview"
    UNKNOWN = "unknown"


def detect_archetype(html: str, *, office: str = "us_house") -> Archetype:
    anchor_ids = find_anchor_ids(html)
    has_district_results = "Candidates_and_election_results" in anchor_ids or contains_class(html, "votebox")
    has_state_candidates = "Candidates" in anchor_ids and any(value.startswith("District_") for value in anchor_ids)
    title = extract_title(html) or ""
    if office == "us_senate":
        is_national = f"United States Senate elections, {ELECTION_CYCLE_YEAR}" in title
    elif office in {"state_governor", "state_lieutenant_governor"}:
        is_national = f"Gubernatorial elections, {ELECTION_CYCLE_YEAR}" in title
    elif office == "state_attorney_general":
        is_national = f"Attorney general elections, {ELECTION_CYCLE_YEAR}" in title or f"Attorney General elections, {ELECTION_CYCLE_YEAR}" in title
    else:
        is_national = f"United States House of Representatives elections, {ELECTION_CYCLE_YEAR}" in title

    if is_national:
        return Archetype.NATIONAL_OVERVIEW
    if has_district_results:
        return Archetype.DISTRICT_DETAIL
    if has_state_candidates:
        return Archetype.STATE_ROLLUP
    return Archetype.UNKNOWN
