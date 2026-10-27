#!/usr/bin/env python3
"""Build canonical U.S. House seat objects from Census/NTAD congressional district data."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_us_house_election_view import OUTPUT_FILE as ELECTION_VIEW_OUTPUT_FILE, build_us_house_election_view as build_derived_us_house_election_view
from election_rules.us_house_primary_systems import (
    NONPARTISAN_OR_UNKNOWN,
    PARTISAN_PRIMARY,
    PRIMARY_SYSTEMS_BY_STATE,
    TOP_TWO,
    JUNGLE_PRIMARY_OR_MAJORITY_TRIGGER,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = REPO_ROOT / "test_data" / "maps" / "Congressional"
FALLBACK_SOURCE_DIRS = [
    REPO_ROOT / "test_data" / "maps" / "NTAD_Congressional_Districts_03182026",
]
DEFAULT_SOURCE_HINT = "NTAD_Congressional_Districts_-128469763264767056"
OUTPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-seats.json"
CANDIDATE_SOURCE_FILE = REPO_ROOT / "test_data" / "candidates" / "candidate_summary_2026.csv"
BALLOTPEDIA_HOUSE_TEXT_DIR = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "output_house_text"
MARKET_CANDIDATE_SOURCE_DIR = REPO_ROOT / "test_data" / "kalshi" / "market"

STATE_ABBREVIATIONS = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL",
    "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA",
    "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}

FIELD_ALIASES = {
    "state_name": ["STATE", "STATE_NAME", "STATENAME", "STATE_ABBR_NAME"],
    "state_code": ["STATEABBR", "STATE_ABBR", "STATE_CODE", "STUSPS", "STATE_POSTAL"],
    "state_fips": ["STATEFP", "STATEFP20", "STATE_FIPS", "STATEFP10"],
    "district_number": ["DISTRICT", "CD", "CDFP", "CD119FP", "CD118FP", "DISTRICTNO", "DISTRICT_NUMBER"],
    "district_code": ["DISTRICT", "DISTRICTID", "DISTRICT_CODE", "CD119FP", "CD118FP", "CDFP"],
    "geoid": ["GEOID", "GEOIDFQ", "GEOID20"],
    "name": ["NAME", "NAMELSAD", "DISTRICTNAME", "LABEL"],
    "lsad": ["LSAD", "LSAD20"],
    "aland": ["ALAND", "ALAND20", "AREA_LAND"],
    "awater": ["AWATER", "AWATER20", "AREA_WATER"],
    "intptlat": ["INTPTLAT", "INTPTLAT20", "CENTLAT", "CENTROID_LAT"],
    "intptlon": ["INTPTLON", "INTPTLON20", "CENTLON", "CENTROID_LON"],
    "shape_area": ["SHAPE__AREA", "SHAPE_AREA"],
    "shape_length": ["SHAPE__LENGTH", "SHAPE_LENGTH"],
    "object_id": ["OBJECTID", "OBJECTID_1", "FID"],
    "global_id": ["GLOBALID", "GLOBAL_ID"],
}

LOW_CONFIDENCE_NOTE_PATTERNS = (
    "candidate list in this election may not be complete",
    "list of general election candidates is incomplete pending results from the primary",
    "no district sections were parsed",
)
PARTY_CODE_BY_BALLOTPEDIA_LABEL = {
    "DEMOCRATIC": "DEM",
    "DEMOCRATIC PARTY": "DEM",
    "DFL": "DFL",
    "REPUBLICAN": "REP",
    "REPUBLICAN PARTY": "REP",
    "LIBERTARIAN": "LIB",
    "LIBERTARIAN PARTY": "LIB",
    "GREEN": "GRE",
    "GREEN PARTY": "GRE",
    "INDEPENDENT": "IND",
    "NO PARTY AFFILIATION": "NPA",
    "NO PARTY PREFERENCE": "NPA",
    "NONPARTISAN": "NPA",
    "AMERICAN INDEPENDENT": "AIP",
}

STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}

NAME_SUFFIX_TOKENS = {"JR", "SR", "II", "III", "IV", "V"}
HONORIFIC_TOKENS = {
    "DR", "MR", "MRS", "MS", "MISS", "SEN", "SENATOR", "REP", "REPRESENTATIVE", "GOV", "GOVERNOR",
    "LT", "LTGOV", "MAYOR", "JUDGE", "REV",
}
COMMON_NICKNAME_GROUPS = (
    ("BRAD", "BRADLEY"),
    ("DAVE", "DAVID"),
    ("ED", "EDWARD"),
    ("JEFF", "JEFFREY"),
    ("JIM", "JAMES"),
    ("JOE", "JOSEPH"),
    ("KAT", "KATHERINE"),
    ("SAM", "SAMUEL", "SAMMY"),
)


def normalize_header(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


NORMALIZED_ALIASES = {
    key: [normalize_header(name) for name in names]
    for key, names in FIELD_ALIASES.items()
}


def pick_field(row: dict[str, str], logical_name: str) -> str | None:
    normalized_row = {normalize_header(key): value for key, value in row.items()}
    for alias in NORMALIZED_ALIASES[logical_name]:
        value = normalized_row.get(alias)
        if value not in (None, ""):
            return str(value).strip()
    return None


def format_repo_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class SeatBuildError(RuntimeError):
    pass


PARTY_NAME_BY_CODE = {
    "AIP": "American Independent",
    "DEM": "Democratic",
    "DFL": "Democratic-Farmer-Labor",
    "GRE": "Green",
    "IND": "Independent",
    "LIB": "Libertarian",
    "NPA": "No Party Affiliation",
    "OWN": "Other",
    "REP": "Republican",
}


CONTENTIONS = {
    "no_election": "No Election",
    "uncontested": "Uncontested Election",
    "contested_primary_only": "Contested Election (Primary only)",
    "contested": "Contested Election",
}

TOP_TWO_PRIMARY_STATES = {"CA", "WA"}
NONPARTISAN_PRIMARY_STATES = {"AK", "LA"}
TRACKED_NOMINATION_PARTIES = ("DEM", "REP")


def find_source_file(source_dir: Path = DEFAULT_SOURCE_DIR, source_hint: str = DEFAULT_SOURCE_HINT) -> Path:
    if not source_dir.exists():
        fallback_source_dir = next((path for path in FALLBACK_SOURCE_DIRS if path.exists()), None)
        if fallback_source_dir is None:
            raise SeatBuildError(f"Source directory not found: {source_dir}")
        source_dir = fallback_source_dir

    preferred_files = sorted(path for path in source_dir.rglob("*") if path.is_file() and source_hint in path.name)
    csv_candidates = preferred_files or sorted(path for path in source_dir.rglob("*.csv") if path.is_file())
    if not csv_candidates:
        raise SeatBuildError(f"No CSV seat source found under {source_dir}")
    return csv_candidates[0]


def parse_district_number(raw_value: str | None) -> int:
    if raw_value is None:
        raise SeatBuildError("Missing district number")

    value = raw_value.strip().upper()
    if value in {"AL", "AT LARGE", "AT-LARGE"}:
        return 0

    match = re.search(r"(\d+)", value)
    if not match:
        raise SeatBuildError(f"Unparseable district number: {raw_value}")
    return int(match.group(1))


def normalize_state_code(state_name: str | None, state_code: str | None) -> str:
    if state_code:
        return state_code.strip().upper()
    if state_name:
        upper_name = state_name.strip().upper()
        if len(upper_name) == 2 and upper_name.isalpha():
            return upper_name
        if upper_name in STATE_ABBREVIATIONS:
            return STATE_ABBREVIATIONS[upper_name]
    raise SeatBuildError(f"Unable to determine state code from state_name={state_name!r} state_code={state_code!r}")


def build_seat_id(state_code: str, district_number: int) -> str:
    return f"{state_code}-AL" if district_number == 0 else f"{state_code}-{district_number:02d}"


def build_market_aliases(state_code: str, district_number: int) -> list[str]:
    aliases = [build_seat_id(state_code, district_number)]
    if district_number == 0:
        aliases.append(f"{state_code}-REP")
    return aliases


def normalize_party_name(party_code: str | None) -> str:
    if not party_code:
        return "Other"
    return PARTY_NAME_BY_CODE.get(party_code.strip().upper(), "Other")


def normalize_candidate_name(raw_name: str | None) -> str:
    if not raw_name:
        return "Unknown"
    parts = [part.strip() for part in raw_name.split(",") if part.strip()]
    if len(parts) >= 2:
        combined = " ".join(parts[1:] + [parts[0]])
    else:
        combined = parts[0] if parts else raw_name.strip()
    return combined.title()


def normalize_person_name_tokens(raw_name: str | None) -> tuple[str, ...]:
    if not raw_name:
        return ()
    cleaned = re.sub(r"\([^)]*\)", " ", raw_name)
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned).upper()
    tokens = [BALLOTPEDIA_NICKNAME_EQUIVALENTS.get(token, token) for token in cleaned.split() if token]
    return tuple(tokens)


def has_ballotpedia_nickname_alias(raw_name: str | None) -> bool:
    if not raw_name:
        return False
    cleaned = re.sub(r"\([^)]*\)", " ", raw_name)
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned).upper()
    return any(token in BALLOTPEDIA_NICKNAME_EQUIVALENTS for token in cleaned.split())


def ballotpedia_name_match_score(left: str | None, right: str | None) -> float:
    left_tokens = normalize_person_name_tokens(left)
    right_tokens = normalize_person_name_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    if left_tokens == right_tokens:
        return 1.0

    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if left_set == right_set:
        return 0.97

    if left_tokens[-1] != right_tokens[-1]:
        return 0.0

    overlap = len(left_set & right_set)
    denom = max(len(left_set), len(right_set))
    if denom == 0:
        return 0.0
    score = overlap / denom
    if score >= 0.5:
        return 0.75 + (0.2 * score)
    return 0.0


def normalize_ballotpedia_party(raw_party: str | None) -> tuple[str, str]:
    if not raw_party:
        return "OWN", "Other"
    party_label = raw_party.strip()
    party_code = PARTY_LABEL_TO_CODE.get(party_label.upper(), "OWN")
    return party_code, normalize_party_name(party_code) if party_code != "OWN" else party_label.title()


def parse_ballotpedia_candidate_line(raw_line: str, fallback_party: str | None = None) -> dict | None:
    stripped = raw_line.strip()
    if not stripped.startswith("- "):
        return None
    value = stripped[2:].strip()
    if value in {"[None parsed]", "[No primary sections parsed]"}:
        return None

    incumbent = "(Incumbent)" in value
    advanced = "✔" in value
    party_match = re.search(r"\(([^()]+)\)\s*$", value)
    parsed_party = party_match.group(1) if party_match else fallback_party

    name = re.sub(r"\([^)]*\)", "", value)
    name = name.replace("✔", " ")
    name = re.sub(r"\s+", " ", name).strip(" -")

    party_code, party_name = normalize_ballotpedia_party(parsed_party)
    return {
        "name": name,
        "partyCode": party_code,
        "partyName": party_name,
        "incumbent": incumbent,
        "advanced": advanced,
        "sourceText": value,
    }


def parse_ballotpedia_house_text(text: str, state_name: str | None = None) -> dict:
    result = {
        "stateName": state_name,
        "districts": {},
        "noDistrictSectionsParsed": "No district sections were parsed." in text,
    }
    if result["noDistrictSectionsParsed"]:
        return result

    district_pattern = re.compile(r"^District\s+(\d+)\n[-]+\n(.*?)(?=^District\s+\d+\n[-]+\n|\Z)", re.M | re.S)
    for match in district_pattern.finditer(text):
        district_number = int(match.group(1))
        block = match.group(2)
        district = {
            "districtNumber": district_number,
            "notes": [],
            "generalCandidates": [],
            "primaryCandidatesByParty": {},
            "primarySectionsParsed": True,
            "parseConfidence": 1.0,
        }

        notes_match = re.search(r"Notes:\n(.*?)(?=General election candidates:)", block, re.S)
        if notes_match:
            district["notes"] = [
                line.strip()[2:].strip()
                for line in notes_match.group(1).splitlines()
                if line.strip().startswith("- ")
            ]

        general_match = re.search(r"General election candidates:\n(.*?)(?=Primary candidates:)", block, re.S)
        if general_match:
            for line in general_match.group(1).splitlines():
                candidate = parse_ballotpedia_candidate_line(line)
                if candidate:
                    district["generalCandidates"].append(candidate)

        primary_match = re.search(r"Primary candidates:\n(.*?)(?=Advanced from primary:|\Z)", block, re.S)
        if primary_match:
            primary_text = primary_match.group(1)
            if "[No primary sections parsed]" in primary_text:
                district["primarySectionsParsed"] = False
            current_party = None
            for raw_line in primary_text.splitlines():
                line = raw_line.rstrip()
                party_match = re.match(r"\s*(?:=\s*candidate.*?\s+)?([A-Za-z][A-Za-z' -]+):\s*$", line)
                if party_match:
                    current_party = party_match.group(1).strip()
                    district["primaryCandidatesByParty"].setdefault(current_party, [])
                    continue
                if current_party:
                    candidate = parse_ballotpedia_candidate_line(line, fallback_party=current_party)
                    if candidate:
                        district["primaryCandidatesByParty"][current_party].append(candidate)

        result["districts"][district_number] = district

    return result


def is_scrape_garbage_candidate(name: str) -> bool:
    normalized = name.upper()
    if any(marker in normalized for marker in SCRAPE_GARBAGE_MARKERS):
        return True
    if re.search(r"\bCONGRESSIONAL DISTRICT\b", normalized):
        return True
    return len(normalized.split()) > 12


def prune_scrape_garbage_candidates(candidates: list[dict], parse_confidence: float) -> list[dict]:
    if parse_confidence < 0.5:
        return list(candidates)
    return [candidate for candidate in candidates if not is_scrape_garbage_candidate(candidate["name"])]


def reconcile_ballotpedia_candidates(ballotpedia_candidates: list[dict], official_candidates: list[dict]) -> list[dict]:
    reconciled: list[dict] = []
    for candidate in ballotpedia_candidates:
        best_match = None
        best_score = 0.0
        for official in official_candidates:
            score = ballotpedia_name_match_score(candidate.get("name"), official.get("name"))
            if candidate.get("partyCode") and official.get("partyCode") and candidate["partyCode"] != official["partyCode"]:
                score = 0.0
            if score > best_score:
                best_score = score
                best_match = official

        merged = dict(candidate)
        merged["matchedOfficialName"] = best_match.get("name") if best_match else None
        merged["reconciliationScore"] = round(best_score, 3)
        if best_match and best_score >= 0.8:
            merged["candidateId"] = best_match.get("candidateId")
            merged["partyCode"] = best_match.get("partyCode", merged.get("partyCode"))
            merged["partyName"] = best_match.get("partyName", merged.get("partyName"))
            official_name = best_match.get("name")
            if (
                official_name
                and has_ballotpedia_nickname_alias(candidate.get("name"))
                and len(normalize_person_name_tokens(official_name)) <= len(normalize_person_name_tokens(candidate.get("name")))
            ):
                merged["name"] = official_name
        reconciled.append(merged)
    return reconciled


def build_us_house_election_view(parsed_district: dict, official_candidates: list[dict] | None = None) -> dict:
    official_candidates = official_candidates or []
    parse_confidence = float(parsed_district.get("parseConfidence", 1.0))
    general_candidates = reconcile_ballotpedia_candidates(
        prune_scrape_garbage_candidates(parsed_district.get("generalCandidates", []), parse_confidence),
        official_candidates,
    )

    primary_candidates: list[dict] = []
    for party, candidates in parsed_district.get("primaryCandidatesByParty", {}).items():
        for candidate in candidates:
            candidate_copy = dict(candidate)
            if not candidate_copy.get("partyCode") or candidate_copy["partyCode"] == "OWN":
                party_code, party_name = normalize_ballotpedia_party(party)
                candidate_copy["partyCode"] = party_code
                candidate_copy["partyName"] = party_name
            primary_candidates.append(candidate_copy)
    primary_candidates = reconcile_ballotpedia_candidates(
        prune_scrape_garbage_candidates(primary_candidates, parse_confidence),
        official_candidates,
    )

    if not parsed_district.get("primarySectionsParsed", True):
        primary_status = "top_two_primary"
    elif parsed_district.get("primaryCandidatesByParty"):
        primary_status = "partisan_primary"
    else:
        primary_status = "no_primary_data"

    if primary_status == "top_two_primary":
        display_mode = "primary"
        display_candidates = general_candidates
    elif not general_candidates and primary_candidates:
        display_mode = "primary"
        display_candidates = primary_candidates
    elif general_candidates and len(general_candidates) == 1:
        display_mode = "general"
        display_candidates = general_candidates
    elif any(candidate.get("advanced") for candidate in primary_candidates):
        display_mode = "primary"
        advanced_candidates = [candidate for candidate in primary_candidates if candidate.get("advanced")]
        display_candidates = advanced_candidates or primary_candidates or general_candidates
    else:
        display_mode = "general"
        display_candidates = general_candidates

    return {
        "primaryStatus": primary_status,
        "displayMode": display_mode,
        "displayCandidates": [
            {
                "name": candidate.get("name"),
                "partyCode": candidate.get("partyCode"),
                "partyName": candidate.get("partyName"),
                "candidateId": candidate.get("candidateId"),
            }
            for candidate in display_candidates
        ],
    }


def canonicalize_person_name(raw_name: str | None) -> str:
    if not raw_name:
        return ""
    cleaned = re.sub(r"\([^)]*\)", " ", raw_name)
    cleaned = cleaned.replace("✔", " ")
    cleaned = re.sub(r"\bIncumbent\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", cleaned).strip().upper()
    return re.sub(r"\s+", " ", cleaned)


def normalize_alias_tokens(raw_name: str | None) -> list[str]:
    if not raw_name:
        return []
    cleaned = re.sub(r"\([^)]*\)", " ", raw_name)
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", cleaned).strip().upper()
    return [token for token in re.sub(r"\s+", " ", cleaned).split(" ") if token]


def strip_middle_initial_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) < 3:
        return list(tokens)
    stripped: list[str] = []
    for index, token in enumerate(tokens):
        if 0 < index < (len(tokens) - 1) and len(token) == 1:
            continue
        stripped.append(token)
    return stripped


def strip_middle_name_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) <= 2:
        return list(tokens)
    return [tokens[0], tokens[-1]]


def strip_honorific_tokens(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token not in HONORIFIC_TOKENS and token not in NAME_SUFFIX_TOKENS]


def build_nickname_lookup() -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for group in COMMON_NICKNAME_GROUPS:
        normalized = {token.upper() for token in group}
        for token in normalized:
            lookup.setdefault(token, set()).update(normalized)
    return lookup


NICKNAME_LOOKUP = build_nickname_lookup()


def first_name_matches_with_nickname(left: str, right: str) -> bool:
    if left == right:
        return True
    return right in NICKNAME_LOOKUP.get(left, set()) or left in NICKNAME_LOOKUP.get(right, set())


def classify_candidate_alias(candidate_name: str, alias_name: str) -> str | None:
    candidate_tokens = normalize_alias_tokens(candidate_name)
    alias_tokens = normalize_alias_tokens(alias_name)
    if not candidate_tokens or not alias_tokens:
        return None

    if candidate_tokens == alias_tokens:
        return "exact"

    candidate_without_middle = strip_middle_initial_tokens(candidate_tokens)
    alias_without_middle = strip_middle_initial_tokens(alias_tokens)
    if candidate_without_middle == alias_without_middle:
        return "middle_initial_only"

    candidate_without_honorifics = strip_honorific_tokens(candidate_without_middle)
    alias_without_honorifics = strip_honorific_tokens(alias_without_middle)
    if candidate_without_honorifics == alias_without_honorifics:
        return "honorific_or_suffix"

    if len(candidate_without_honorifics) < 2 or len(alias_without_honorifics) < 2:
        return None
    if candidate_without_honorifics[-1] != alias_without_honorifics[-1]:
        return None

    candidate_first = candidate_without_honorifics[0]
    alias_first = alias_without_honorifics[0]
    if not first_name_matches_with_nickname(candidate_first, alias_first):
        return None

    candidate_core = strip_middle_name_tokens(candidate_without_honorifics)
    alias_core = strip_middle_name_tokens(alias_without_honorifics)
    if candidate_core == alias_core:
        return "nickname" if candidate_first != alias_first else "middle_name_only"

    candidate_middle = candidate_without_honorifics[1:-1]
    alias_middle = alias_without_honorifics[1:-1]
    if candidate_middle == alias_middle:
        return "nickname"
    if not candidate_middle or not alias_middle:
        return "compound_variation"
    if set(candidate_middle) == set(alias_middle):
        return "compound_variation"

    return None


def format_house_seat_id(state_code: str, district_code: str) -> str:
    return f"{state_code}-AL" if district_code == "AL" else f"{state_code}-{int(district_code):02d}"


def infer_structured_house_seat_id(text: str) -> str | None:
    upper = text.upper()
    patterns = (
        r"\bKXHOUSERACE-([A-Z]{2})(AL|\d{1,2})-\d{2}(?:-|$)",
        r"\bKX([A-Z]{2})(AL|\d{1,2})([DR])(?:-|$)",
        r"\bKX([A-Z]{2})PRIMARY-(\d{1,2})([DR])\d{2}(?:-|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, upper)
        if match:
            return format_house_seat_id(match.group(1), match.group(2))
    return None


def infer_market_candidate_seat_id(series_ticker: str, market_ticker: str, title: str, rules_primary: str = "") -> str | None:
    for text in (market_ticker, series_ticker):
        structured = infer_structured_house_seat_id(text)
        if structured:
            return structured

    combined = f"{title} {rules_primary}".upper()
    match = re.search(r"\b([A-Z]{2})-(AL|\d{1,2})\b", combined)
    if match:
        return format_house_seat_id(match.group(1), match.group(2))

    if "DISTRICT OF COLUMBIA" in combined and "AT-LARGE DISTRICT" in combined:
        return "DC-AL"

    match = re.search(
        r"\b([A-Z][A-Z\s]+?)'?S\s+(AT-LARGE|AT LARGE|\d{1,2})(?:ST|ND|RD|TH)?\s+(?:CONGRESSIONAL\s+)?DISTRICT\b",
        combined,
    )
    if not match:
        return None
    state_name = re.sub(r"\s+", " ", match.group(1).strip().lower())
    state_code = STATE_NAME_TO_CODE.get(state_name)
    if not state_code:
        return None
    district_code = "AL" if match.group(2).startswith("AT") else match.group(2)
    return format_house_seat_id(state_code, district_code)


def infer_market_candidate_name(market_payload: dict) -> str | None:
    custom_strike = market_payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        for key in ("Candidate", "candidate", "Nominee", "Person"):
            value = custom_strike.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("yes_sub_title", "title"):
        value = market_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def infer_market_candidate_party(market_payload: dict) -> str | None:
    custom_strike = market_payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        party_value = custom_strike.get("Party")
        if isinstance(party_value, str) and party_value.strip():
            normalized = party_value.strip().upper()
            if normalized.startswith("DEM"):
                return "DEM"
            if normalized.startswith("REP"):
                return "REP"

    combined = f"{market_payload.get('title') or ''} {market_payload.get('rules_primary') or ''}".upper()
    if "DEMOCRATIC" in combined or "DEMOCRAT" in combined:
        return "DEM"
    if "REPUBLICAN" in combined or "GOP" in combined:
        return "REP"
    return None


def match_market_alias_to_candidate(alias_name: str, candidates: list[dict], party_code: str | None = None) -> tuple[dict, str] | None:
    pool = [
        candidate for candidate in candidates
        if not party_code or str(candidate.get("partyCode") or "").upper() == party_code
    ]
    for category in ("exact", "middle_initial_only", "honorific_or_suffix", "middle_name_only", "nickname", "compound_variation"):
        matches = [
            candidate for candidate in pool
            if classify_candidate_alias(str(candidate.get("name") or ""), alias_name) == category
        ]
        if len(matches) == 1:
            return matches[0], category
    return None


def add_candidate_alias(candidate: dict, alias_name: str) -> None:
    alias = alias_name.strip()
    if not alias:
        return
    aliases = list(candidate.get("aliases") or [])
    if alias == candidate.get("name") or alias in aliases:
        return
    aliases.append(alias)
    aliases.sort()
    candidate["aliases"] = aliases
    if candidate.get("kalshiName") is None and canonicalize_person_name(alias) != canonicalize_person_name(candidate.get("name")):
        candidate["kalshiName"] = alias


def enrich_candidates_with_market_aliases(
    candidates_by_seat: dict[str, list[dict]],
    market_candidate_source_dir: Path = MARKET_CANDIDATE_SOURCE_DIR,
) -> dict[str, list[dict]]:
    if not market_candidate_source_dir.exists():
        return candidates_by_seat

    for market_file in sorted(market_candidate_source_dir.glob("market_*.json")):
        market_payload = json.loads(market_file.read_text(encoding="utf-8"))
        title = str(market_payload.get("title") or "")
        if "NOMINEE" not in title.upper() and "PRIMARY" not in title.upper():
            continue
        alias_name = infer_market_candidate_name(market_payload)
        if not alias_name:
            continue
        seat_id = infer_market_candidate_seat_id(
            str(market_payload.get("event_ticker") or ""),
            str(market_payload.get("ticker") or ""),
            title,
            str(market_payload.get("rules_primary") or ""),
        )
        if not seat_id or seat_id not in candidates_by_seat:
            continue
        matched = match_market_alias_to_candidate(
            alias_name,
            candidates_by_seat[seat_id],
            infer_market_candidate_party(market_payload),
        )
        if matched is None:
            continue
        candidate, _category = matched
        add_candidate_alias(candidate, alias_name)

    return candidates_by_seat


def normalize_candidate_district(raw_value: str | None) -> int:
    if raw_value in (None, ""):
        return 0
    return parse_district_number(raw_value)


def build_candidate_object(row: dict[str, str]) -> dict | None:
    if (row.get("Cand_Office") or "").strip().upper() != "H":
        return None

    state_code = normalize_state_code(row.get("Cand_Office_St"), row.get("Cand_Office_St"))
    district_number = normalize_candidate_district(row.get("Cand_Office_Dist"))
    seat_id = build_seat_id(state_code, district_number)
    party_code = (row.get("Cand_Party_Affiliation") or "").strip().upper() or "OWN"

    return {
        "candidateId": (row.get("Cand_Id") or "").strip() or None,
        "name": normalize_candidate_name(row.get("Cand_Name")),
        "kalshiName": None,
        "aliases": [],
        "partyCode": party_code,
        "partyName": normalize_party_name(party_code),
        "seatId": seat_id,
        "electionId": f"US-HOUSE-2026-{seat_id}",
        "incumbentStatus": (row.get("Cand_Incumbent_Challenger_Open_Seat") or "").strip() or None,
        "fecUrl": (row.get("Link_Image") or "").strip() or None,
        "filingSource": "FEC candidate summary 2026",
    }


def ballotpedia_party_code(raw_label: str | None) -> str:
    if not raw_label:
        return "OWN"
    cleaned = raw_label.replace(":", " ")
    cleaned = re.sub(r"= candidate completed Ballotpedia's Candidate Connection survey", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z ]+", " ", cleaned).strip().upper()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return PARTY_CODE_BY_BALLOTPEDIA_LABEL.get(cleaned, "OWN")


def extract_party_from_candidate_text(text: str) -> str:
    match = re.search(r"\(([^)]*Party|No party preference|No Party Affiliation|Independent|Nonpartisan)\)", text, re.IGNORECASE)
    if match:
        return ballotpedia_party_code(match.group(1))
    return "OWN"


def parse_ballotpedia_candidate_entry(line: str, fallback_party_code: str | None = None) -> dict | None:
    stripped = line.strip()
    if not stripped.startswith("- "):
        return None
    raw = stripped[2:].strip()
    if not raw or raw.startswith("["):
        return None
    if raw.startswith("Safe and Solid ratings") or raw.startswith("Likely ratings") or raw.startswith("Lean ratings") or raw.startswith("Toss-up ratings"):
        return None
    name = re.sub(r"\([^)]*\)", " ", raw)
    name = name.replace("✔", " ")
    name = re.sub(r"\s+", " ", name).strip(" -")
    if not name:
        return None
    party_code = fallback_party_code or extract_party_from_candidate_text(raw)
    return {
        "name": name,
        "partyCode": party_code,
        "rawText": raw,
        "canonicalName": canonicalize_person_name(name),
        "isExplicitAdvancer": "✔" in raw or bool(re.search(r"\b(advanced|won|qualified|runoff)\b", raw, re.IGNORECASE)),
    }


def parse_ballotpedia_districts(text: str, state_code: str) -> dict[str, dict]:
    districts: dict[str, dict] = {}
    if "No district sections were parsed." in text:
        return districts

    pattern = re.compile(r"^District\s+(\d+)\n[-]+\n", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        district_number = int(match.group(1))
        seat_id = build_seat_id(state_code, district_number)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        district = {
            "seatId": seat_id,
            "notes": [],
            "general": [],
            "advanced": [],
            "primaryByParty": defaultdict(list),
        }
        section = None
        current_party_code = None
        for raw_line in block.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if stripped == "Notes:":
                section = "notes"
                current_party_code = None
                continue
            if stripped == "General election candidates:":
                section = "general"
                current_party_code = None
                continue
            if stripped == "Primary candidates:":
                section = "primary"
                current_party_code = None
                continue
            if stripped == "Advanced from primary:":
                section = "advanced"
                current_party_code = None
                continue
            if section == "notes" and stripped.startswith("- "):
                district["notes"].append(stripped[2:].strip())
                continue
            if section == "primary" and stripped.endswith(":") and not stripped.startswith("- "):
                current_party_code = ballotpedia_party_code(stripped[:-1])
                continue
            if section == "general":
                candidate = parse_ballotpedia_candidate_entry(stripped)
                if candidate:
                    district["general"].append(candidate)
                continue
            if section == "advanced":
                candidate = parse_ballotpedia_candidate_entry(stripped)
                if candidate:
                    district["advanced"].append(candidate)
                continue
            if section == "primary":
                candidate = parse_ballotpedia_candidate_entry(stripped, current_party_code)
                if candidate:
                    district["primaryByParty"][candidate["partyCode"]].append(candidate)
        districts[seat_id] = district
    return districts


def district_has_low_confidence_parse(district: dict) -> bool:
    notes = " ".join(district.get("notes") or []).lower()
    return any(pattern in notes for pattern in LOW_CONFIDENCE_NOTE_PATTERNS)


def candidate_keys(candidates: list[dict]) -> set[str]:
    return {candidate.get("canonicalName") or canonicalize_person_name(candidate.get("name")) for candidate in candidates}


def infer_advancing_candidates(district: dict, primary_system: str) -> list[dict] | None:
    if primary_system == NONPARTISAN_OR_UNKNOWN or district_has_low_confidence_parse(district):
        return None

    if district["advanced"]:
        if primary_system == PARTISAN_PRIMARY:
            by_party: dict[str, dict] = {}
            for candidate in district["advanced"]:
                party_code = candidate["partyCode"]
                if party_code == "OWN":
                    continue
                by_party.setdefault(party_code, candidate)
            return list(by_party.values()) if by_party else None
        if primary_system == TOP_TWO:
            return district["advanced"][:2]
        if primary_system == JUNGLE_PRIMARY_OR_MAJORITY_TRIGGER:
            return district["advanced"]

    if primary_system == PARTISAN_PRIMARY:
        nominees = []
        for party_code, primary_candidates in district["primaryByParty"].items():
            explicit = [candidate for candidate in primary_candidates if candidate["isExplicitAdvancer"]]
            if len(explicit) == 1:
                nominees.append(explicit[0])
        if nominees:
            return nominees

        if district["general"]:
            by_party: dict[str, dict] = {}
            for candidate in district["general"]:
                party_code = candidate["partyCode"]
                if party_code in {"DEM", "REP"} and party_code not in by_party:
                    by_party[party_code] = candidate
            return list(by_party.values()) if by_party else None

    if primary_system == TOP_TWO and district["general"]:
        return district["general"][:2]

    if primary_system == JUNGLE_PRIMARY_OR_MAJORITY_TRIGGER:
        explicit = []
        for primary_candidates in district["primaryByParty"].values():
            explicit.extend(candidate for candidate in primary_candidates if candidate["isExplicitAdvancer"])
        return explicit or None

    return None


def merge_ballotpedia_candidates(
    candidates_by_seat: dict[str, list[dict]],
    ballotpedia_dir: Path = BALLOTPEDIA_HOUSE_TEXT_DIR,
) -> dict[str, list[dict]]:
    merged: dict[str, list[dict]] = {seat_id: [dict(candidate) for candidate in candidates] for seat_id, candidates in candidates_by_seat.items()}
    if not ballotpedia_dir.exists():
        return merged

    for text_file in sorted(ballotpedia_dir.glob("*.txt")):
        state_name = text_file.stem
        state_code = STATE_ABBREVIATIONS.get(state_name.upper())
        if not state_code:
            continue
        districts = parse_ballotpedia_districts(text_file.read_text(encoding="utf-8"), state_code)
        primary_system = PRIMARY_SYSTEMS_BY_STATE.get(state_code, NONPARTISAN_OR_UNKNOWN)
        for seat_id, district in districts.items():
            seat_candidates = merged.setdefault(seat_id, [])
            existing_keys = {canonicalize_person_name(candidate.get("name")): candidate for candidate in seat_candidates}

            for candidate in district["general"]:
                if candidate["canonicalName"] in existing_keys:
                    continue
                generated = {
                    "candidateId": None,
                    "name": candidate["name"],
                    "kalshiName": None,
                    "partyCode": candidate["partyCode"],
                    "partyName": normalize_party_name(candidate["partyCode"]),
                    "seatId": seat_id,
                    "electionId": f"US-HOUSE-2026-{seat_id}",
                    "incumbentStatus": "Incumbent" if "incumbent" in candidate["rawText"].lower() else None,
                    "fecUrl": None,
                    "filingSource": "Ballotpedia 2026 House text",
                }
                seat_candidates.append(generated)
                existing_keys[candidate["canonicalName"]] = generated

            advancing_candidates = infer_advancing_candidates(district, primary_system)
            if not advancing_candidates:
                seat_candidates.sort(key=lambda candidate: (candidate["partyCode"], candidate["name"]))
                continue

            allowed_keys = candidate_keys(advancing_candidates)
            pruned_candidates = [candidate for candidate in seat_candidates if canonicalize_person_name(candidate.get("name")) in allowed_keys]
            if pruned_candidates:
                seat_candidates[:] = pruned_candidates
            seat_candidates.sort(key=lambda candidate: (candidate["partyCode"], candidate["name"]))

    return merged


def load_candidates_by_seat(
    candidate_source_file: Path = CANDIDATE_SOURCE_FILE,
    market_candidate_source_dir: Path = MARKET_CANDIDATE_SOURCE_DIR,
) -> dict[str, list[dict]]:
    if not candidate_source_file.exists():
        return {}

    candidates_by_seat: dict[str, list[dict]] = defaultdict(list)
    with candidate_source_file.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candidate = build_candidate_object(row)
            if candidate is None:
                continue
            candidates_by_seat[candidate["seatId"]].append(candidate)

    for candidates in candidates_by_seat.values():
        candidates.sort(key=lambda candidate: (candidate["partyCode"], candidate["name"]))

    merged_candidates = merge_ballotpedia_candidates(dict(candidates_by_seat))
    return enrich_candidates_with_market_aliases(merged_candidates, market_candidate_source_dir)


def classify_contention(candidates: list[dict]) -> str:
    if not candidates:
        return "no_election"
    if len(candidates) == 1:
        return "uncontested"

    represented_parties = {candidate["partyCode"] for candidate in candidates}
    if len(represented_parties) == 1:
        return "contested_primary_only"
    return "contested"


def determine_primary_system(state_code: str) -> str:
    if state_code in TOP_TWO_PRIMARY_STATES:
        return "top_two"
    if state_code in NONPARTISAN_PRIMARY_STATES:
        return "nonpartisan"
    return "partisan"


def build_party_nomination_status(party_candidates: list[dict], primary_system: str) -> dict:
    if primary_system != "partisan":
        return {
            "nomineeKnown": False,
            "nomineeCandidateId": None,
            "nomineeDisplayName": None,
            "sourcePriority": "primary_system_nonpartisan",
            "sourceConfidence": "not_applicable",
            "nominationComplete": False,
        }

    if not party_candidates:
        return {
            "nomineeKnown": False,
            "nomineeCandidateId": None,
            "nomineeDisplayName": None,
            "sourcePriority": "fec_candidate_summary",
            "sourceConfidence": "none",
            "nominationComplete": False,
        }

    if len(party_candidates) == 1:
        candidate = party_candidates[0]
        return {
            "nomineeKnown": True,
            "nomineeCandidateId": candidate.get("candidateId"),
            "nomineeDisplayName": candidate.get("name"),
            "sourcePriority": "fec_candidate_summary",
            "sourceConfidence": "low",
            "nominationComplete": False,
        }

    return {
        "nomineeKnown": False,
        "nomineeCandidateId": None,
        "nomineeDisplayName": None,
        "sourcePriority": "fec_candidate_summary",
        "sourceConfidence": "low",
        "nominationComplete": False,
    }



def build_nomination_status(state_code: str, candidates_by_party: dict[str, list[dict]]) -> dict:
    primary_system = determine_primary_system(state_code)

    if primary_system == "partisan":
        tracked_party_counts = {
            party_code: len(candidates_by_party.get(party_code, []))
            for party_code in TRACKED_NOMINATION_PARTIES
        }
        all_candidate_counts = [len(party_candidates) for party_candidates in candidates_by_party.values()]
        has_same_party_contest = any(count > 1 for count in all_candidate_counts)
        has_any_candidates = any(count > 0 for count in all_candidate_counts)
        tracked_nomination_complete = has_any_candidates and any(
            tracked_party_counts[party_code] == 1 for party_code in TRACKED_NOMINATION_PARTIES
        ) and not has_same_party_contest

        if not has_any_candidates:
            primary_status = "not_available"
        elif has_same_party_contest:
            primary_status = "primary_pending_results"
        else:
            primary_status = "general_only"
    else:
        tracked_nomination_complete = False
        primary_status = "not_available" if not candidates_by_party else "pre_primary"

    parties = {
        party_code: build_party_nomination_status(candidates_by_party.get(party_code, []), primary_system)
        for party_code in TRACKED_NOMINATION_PARTIES
    }

    high_confidence_complete = (
        primary_system == "partisan"
        and tracked_nomination_complete
        and all(parties[party_code]["sourceConfidence"] == "high" for party_code in TRACKED_NOMINATION_PARTIES if candidates_by_party.get(party_code))
    )

    return {
        "primarySystem": primary_system,
        "primaryStatus": primary_status,
        "parties": parties,
        "pruneToGeneralElectionCandidates": high_confidence_complete,
        "pruneReason": (
            "high_confidence_partisan_nominees_confirmed"
            if high_confidence_complete
            else "retain_primary_candidates_until_high_confidence_partisan_nominees_confirmed"
        ),
    }



def build_candidate_election_status(
    candidate: dict,
    primary_system: str,
    party_candidates: list[dict],
) -> dict:
    party_code = candidate.get("partyCode")
    if primary_system == "partisan" and party_code in TRACKED_NOMINATION_PARTIES:
        if len(party_candidates) == 1:
            return {
                "code": "general-nominated",
                "partyCode": party_code,
                "label": f"General nominated ({party_code})",
            }
        if len(party_candidates) > 1:
            return {
                "code": "primary-active",
                "partyCode": party_code,
                "label": f"Active primary ({party_code})",
            }
    return {
        "code": "general-other",
        "partyCode": party_code,
        "label": "General other",
    }



def build_primary_election_objects(
    seat_id: str,
    district_label: str,
    office_code: str,
    office_name: str,
    state_code: str,
    candidates_by_party: dict[str, list[dict]],
) -> list[dict]:
    primary_system = determine_primary_system(state_code)
    if primary_system != "partisan":
        return []

    primary_children: list[dict] = []
    for party_code in TRACKED_NOMINATION_PARTIES:
        party_candidates = sorted(candidates_by_party.get(party_code, []), key=lambda candidate: candidate["name"])
        if not party_candidates:
            continue
        concluded = len(party_candidates) == 1
        nominee = party_candidates[0] if concluded else None
        primary_children.append({
            "electionId": f"US-HOUSE-2026-{seat_id}-PRIMARY-{party_code}",
            "parentElectionId": f"US-HOUSE-2026-{seat_id}",
            "electionKind": "primary",
            "status": "concluded" if concluded else "active",
            "officeCode": office_code,
            "officeName": office_name,
            "seatId": seat_id,
            "districtLabel": district_label,
            "partyCode": party_code,
            "partyName": normalize_party_name(party_code),
            "label": f"Primary ({party_code})",
            "candidateCount": len(party_candidates),
            "candidates": party_candidates,
            "nomineeCandidateId": nominee.get("candidateId") if nominee else None,
            "nomineeDisplayName": nominee.get("name") if nominee else None,
        })
    return primary_children



def build_election_object(seat_id: str, district_label: str, office_code: str, office_name: str, candidates: list[dict], state_code: str) -> dict:
    candidates_by_party: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_party[candidate["partyCode"]].append(candidate)

    primary_system = determine_primary_system(state_code)
    candidates_with_status = []
    for candidate in candidates:
        candidate_copy = dict(candidate)
        candidate_copy["currentElectionStatus"] = build_candidate_election_status(
            candidate_copy,
            primary_system,
            candidates_by_party.get(candidate_copy.get("partyCode"), []),
        )
        candidates_with_status.append(candidate_copy)

    candidates_by_party_with_status: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates_with_status:
        candidates_by_party_with_status[candidate["partyCode"]].append(candidate)

    sorted_party_entries = [
        {
            "partyCode": party_code,
            "partyName": normalize_party_name(party_code),
            "candidates": sorted(party_candidates, key=lambda candidate: candidate["name"]),
        }
        for party_code, party_candidates in sorted(
            candidates_by_party_with_status.items(),
            key=lambda item: (item[0] not in {"DEM", "REP"}, item[0]),
        )
    ]

    contention_bucket = classify_contention(candidates_with_status)
    nomination_status = build_nomination_status(state_code, candidates_by_party_with_status)
    primary_children = build_primary_election_objects(
        seat_id=seat_id,
        district_label=district_label,
        office_code=office_code,
        office_name=office_name,
        state_code=state_code,
        candidates_by_party=candidates_by_party_with_status,
    )
    return {
        "electionId": f"US-HOUSE-2026-{seat_id}",
        "electionCycle": 2026,
        "electionKind": "general",
        "status": "active",
        "officeCode": office_code,
        "officeName": office_name,
        "seatId": seat_id,
        "districtLabel": district_label,
        "contentionBucket": contention_bucket,
        "contentionLabel": CONTENTIONS[contention_bucket],
        "candidateCount": len(candidates_with_status),
        "partyCount": len(candidates_by_party_with_status),
        "nominationStatus": nomination_status,
        "candidates": candidates_with_status,
        "candidatesByParty": sorted_party_entries,
        "children": primary_children,
    }


def build_seat_object(
    row: dict[str, str],
    source_file: Path,
    candidates_by_seat: dict[str, list[dict]] | None = None,
) -> dict:
    state_name = pick_field(row, "state_name")
    state_code = normalize_state_code(state_name, pick_field(row, "state_code"))
    district_number = parse_district_number(pick_field(row, "district_number") or pick_field(row, "district_code"))
    district_code = pick_field(row, "district_code")
    if district_code is None:
        district_code = "AL" if district_number == 0 else f"{district_number:02d}"
    district_code = district_code.strip().upper()

    geoid = pick_field(row, "geoid")
    if not geoid and pick_field(row, "state_fips"):
        geoid = f"{pick_field(row, 'state_fips')}{district_code if district_code == 'AL' else district_code.zfill(2)}"

    seat_id = build_seat_id(state_code, district_number)
    candidates = list((candidates_by_seat or {}).get(seat_id, []))
    default_name = f"{state_name or state_code} {'At-Large' if district_number == 0 else f'District {district_number}'}"
    display_name = pick_field(row, "name") or default_name

    raw_metadata = {key: value for key, value in row.items() if value not in (None, "")}
    district_label = "At-Large" if district_number == 0 else f"District {district_number}"

    return {
        "seatId": seat_id,
        "seatType": "US-REP",
        "officeCode": "US-HOUSE",
        "officeName": "U.S. House of Representatives",
        "areaLevel": "congressional_district",
        "countryCode": "US",
        "stateCode": state_code,
        "stateName": state_name,
        "districtNumber": district_number,
        "districtCode": district_code,
        "districtLabel": district_label,
        "isAtLarge": district_number == 0,
        "displayName": display_name,
        "canonicalName": f"{state_code} {'At-Large' if district_number == 0 else f'District {district_number}'}",
        "marketSeatIdAliases": build_market_aliases(state_code, district_number),
        "election": build_election_object(seat_id, district_label, "US-HOUSE", "U.S. House of Representatives", candidates, state_code),
        "area": {
            "level": "congressional_district",
            "name": display_name,
            "stateFips": pick_field(row, "state_fips"),
            "districtCode": district_code,
            "geoid": geoid,
        },
        "gis": {
            "sourceDataset": source_file.stem,
            "sourceFile": format_repo_path(source_file),
            "geometryAvailable": False,
            "geometrySource": None,
            "centroid": {
                "lat": pick_field(row, "intptlat"),
                "lon": pick_field(row, "intptlon"),
            },
            "landArea": pick_field(row, "aland"),
            "waterArea": pick_field(row, "awater"),
            "shapeArea": pick_field(row, "shape_area"),
            "shapeLength": pick_field(row, "shape_length"),
        },
        "source": {
            "provider": "US Census / NTAD",
            "dataset": source_file.stem,
            "rowObjectId": pick_field(row, "object_id"),
            "rowGlobalId": pick_field(row, "global_id"),
            "sourceFile": format_repo_path(source_file),
        },
        "rawMetadata": raw_metadata,
    }


def iter_source_rows(source_file: Path):
    with source_file.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SeatBuildError(f"CSV file is missing a header row: {source_file}")
        for row in reader:
            if not any((value or "").strip() for value in row.values()):
                continue
            yield row


def build_seat_index(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output_file: Path = OUTPUT_FILE,
    candidate_source_file: Path = CANDIDATE_SOURCE_FILE,
    market_candidate_source_dir: Path = MARKET_CANDIDATE_SOURCE_DIR,
) -> dict:
    source_file = find_source_file(source_dir)
    candidates_by_seat = load_candidates_by_seat(candidate_source_file, market_candidate_source_dir)
    seats = []
    for row in iter_source_rows(source_file):
        try:
            seats.append(build_seat_object(row, source_file, candidates_by_seat))
        except SeatBuildError:
            continue
    seats.sort(key=lambda item: (item["stateCode"], item["districtNumber"]))

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDirectory": (
            str(source_file.parent.relative_to(REPO_ROOT))
            if source_file.parent.is_relative_to(REPO_ROOT)
            else str(source_file.parent)
        ),
        "sourceFile": format_repo_path(source_file) if source_file.is_relative_to(REPO_ROOT) else str(source_file),
        "seatType": "US-REP",
        "seatCount": len(seats),
        "seats": seats,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = build_seat_index()
    view_payload = build_derived_us_house_election_view()
    print(f"Wrote {payload['seatCount']} U.S. House seats to {OUTPUT_FILE}")
    print(f"Refreshed {view_payload['seatCount']} U.S. House election views at {ELECTION_VIEW_OUTPUT_FILE}")


if __name__ == "__main__":
    main()
