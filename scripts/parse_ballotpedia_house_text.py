#!/usr/bin/env python3
"""Parse Ballotpedia U.S. House text dumps into seat-keyed normalized records."""
from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_us_house_seat_index import build_seat_id, format_repo_path, normalize_state_code
from build_us_house_election_view import OUTPUT_FILE as ELECTION_VIEW_OUTPUT_FILE, build_us_house_election_view

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "output_house_text"
OUTPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-ballotpedia.json"

DISTRICT_HEADER_RE = re.compile(r"^District\s+(\d+|AL|At-Large)$", re.IGNORECASE)
STATE_LINE_RE = re.compile(r"^State:\s*(.+?)\s*$")
STATE_PAGE_RE = re.compile(r"^State page:\s*(https?://\S+)\s*$")
PARTY_HEADER_RE = re.compile(
    r"^(?:=\s*candidate completed Ballotpedia's Candidate Connection survey\s+)?(.+?):$",
    re.IGNORECASE,
)
SCRAPE_GARBAGE_PATTERNS = (
    "Safe and Solid ratings indicate",
    "Likely ratings indicate",
    "Lean ratings indicate",
    "Toss-up ratings indicate",
    "Search Google News for this topic",
)


def clean_line(line: str) -> str:
    return line.strip()


def is_district_title_repeat(line: str, state_name: str) -> bool:
    return bool(re.fullmatch(rf"{re.escape(state_name)}'s\s+\d+(?:st|nd|rd|th)\s+Congressional District", line))


def is_scrape_garbage(line: str, state_name: str) -> bool:
    return any(pattern in line for pattern in SCRAPE_GARBAGE_PATTERNS) or is_district_title_repeat(line, state_name)


def district_number_from_label(label: str) -> int:
    normalized = label.strip().upper()
    if normalized in {"AL", "AT-LARGE"}:
        return 0
    return int(normalized)


SECTION_NAMES = (
    "Notes:",
    "General election candidates:",
    "Primary candidates:",
    "Advanced from primary:",
)


def parse_bullet_lines(lines: list[str], start_index: int, state_name: str) -> tuple[list[str], int, bool]:
    items: list[str] = []
    contains_scrape_garbage = False
    index = start_index
    while index < len(lines):
        raw_line = lines[index]
        line = clean_line(raw_line)
        if not line:
            index += 1
            continue
        if line in SECTION_NAMES or DISTRICT_HEADER_RE.match(line):
            break
        if line.startswith("-"):
            value = clean_line(line[1:])
            if value:
                if is_scrape_garbage(value, state_name):
                    contains_scrape_garbage = True
                else:
                    items.append(value)
        index += 1
    return items, index, contains_scrape_garbage


def parse_primary_sections(lines: list[str], start_index: int, state_name: str) -> tuple[dict[str, list[str]], int, bool]:
    sections: OrderedDict[str, list[str]] = OrderedDict()
    contains_scrape_garbage = False
    index = start_index
    current_party: str | None = None

    while index < len(lines):
        line = clean_line(lines[index])
        if not line:
            index += 1
            continue
        if line in {"Advanced from primary:"} or DISTRICT_HEADER_RE.match(line):
            break

        header_match = PARTY_HEADER_RE.match(line)
        if header_match and not line.startswith("-"):
            current_party = header_match.group(1).strip()
            sections.setdefault(current_party, [])
            index += 1
            continue

        if line.startswith("-") and current_party:
            value = clean_line(line[1:])
            if value:
                if is_scrape_garbage(value, state_name):
                    contains_scrape_garbage = True
                else:
                    sections[current_party].append(value)
            index += 1
            continue

        if line in SECTION_NAMES:
            break
        index += 1

    return dict(sections), index, contains_scrape_garbage


def build_record(
    state_name: str,
    source_file: Path,
    state_page_url: str | None,
    district_label: str,
    notes: list[str],
    general_candidates: list[str],
    primary_sections: dict[str, list[str]],
    advanced_from_primary: list[str],
    contains_scrape_garbage: bool,
) -> dict:
    state_code = normalize_state_code(state_name, None)
    district_number = district_number_from_label(district_label)
    seat_id = build_seat_id(state_code, district_number)

    flags: list[str] = []
    if not primary_sections:
        flags.append("no_primary_sections")
    if any("incomplete" in note.lower() for note in notes):
        flags.append("general_candidates_incomplete")
    if not advanced_from_primary or any("No 'advanced from the primary' text found" in item for item in advanced_from_primary):
        flags.append("advanced_from_primary_missing")
    if contains_scrape_garbage:
        flags.append("contains_scrape_garbage")

    ballotpedia = {
        "sourceStateFile": source_file.name,
        "statePageUrl": state_page_url,
        "notes": notes,
        "generalElectionCandidateLines": general_candidates,
        "primaryCandidateSections": primary_sections,
        "advancedFromPrimaryLines": advanced_from_primary,
        "scrapeQualityFlags": flags,
    }

    return {
        "seatId": seat_id,
        "stateCode": state_code,
        "stateName": state_name,
        "districtNumber": district_number,
        "districtLabel": "At-Large" if district_number == 0 else f"District {district_number}",
        "source": {
            "provider": "Ballotpedia",
            "sourceStateFile": source_file.name,
            "statePageUrl": state_page_url,
        },
        "election": {
            "ballotpedia": ballotpedia,
        },
    }


def parse_state_file(path: Path) -> tuple[list[dict], dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    state_name = None
    state_page_url = None
    for line in lines[:5]:
        if state_name is None:
            match = STATE_LINE_RE.match(clean_line(line))
            if match:
                state_name = match.group(1).strip()
        if state_page_url is None:
            match = STATE_PAGE_RE.match(clean_line(line))
            if match:
                state_page_url = match.group(1).strip()
    if not state_name:
        raise ValueError(f"Missing state name in {path}")

    records: list[dict] = []
    state_flags: list[str] = []
    if any(clean_line(line) == "No district sections were parsed." for line in lines):
        state_flags.append("no_district_sections")

    index = 0
    while index < len(lines):
        district_match = DISTRICT_HEADER_RE.match(clean_line(lines[index]))
        if not district_match:
            index += 1
            continue
        district_label = district_match.group(1)
        index += 1

        notes: list[str] = []
        general_candidates: list[str] = []
        primary_sections: dict[str, list[str]] = {}
        advanced_from_primary: list[str] = []
        contains_scrape_garbage = False

        while index < len(lines):
            line = clean_line(lines[index])
            if not line:
                index += 1
                continue
            if DISTRICT_HEADER_RE.match(line):
                break
            if line == "Notes:":
                notes, index, garbage = parse_bullet_lines(lines, index + 1, state_name)
                contains_scrape_garbage = contains_scrape_garbage or garbage
                continue
            if line == "General election candidates:":
                general_candidates, index, garbage = parse_bullet_lines(lines, index + 1, state_name)
                contains_scrape_garbage = contains_scrape_garbage or garbage
                continue
            if line == "Primary candidates:":
                primary_sections, index, garbage = parse_primary_sections(lines, index + 1, state_name)
                contains_scrape_garbage = contains_scrape_garbage or garbage
                continue
            if line == "Advanced from primary:":
                advanced_from_primary, index, garbage = parse_bullet_lines(lines, index + 1, state_name)
                contains_scrape_garbage = contains_scrape_garbage or garbage
                continue
            index += 1

        records.append(
            build_record(
                state_name=state_name,
                source_file=path,
                state_page_url=state_page_url,
                district_label=district_label,
                notes=notes,
                general_candidates=general_candidates,
                primary_sections=primary_sections,
                advanced_from_primary=advanced_from_primary,
                contains_scrape_garbage=contains_scrape_garbage,
            )
        )

    return records, {
        "stateName": state_name,
        "stateCode": normalize_state_code(state_name, None),
        "sourceStateFile": path.name,
        "statePageUrl": state_page_url,
        "districtCount": len(records),
        "scrapeQualityFlags": state_flags,
    }


def build_ballotpedia_house_index(input_dir: Path = INPUT_DIR, output_file: Path = OUTPUT_FILE) -> dict:
    state_files = sorted(input_dir.glob("*.txt"))
    records_by_seat_id: OrderedDict[str, dict] = OrderedDict()
    state_summaries = []

    for path in state_files:
        records, state_summary = parse_state_file(path)
        state_summaries.append(state_summary)
        for record in records:
            records_by_seat_id[record["seatId"]] = record

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDirectory": format_repo_path(input_dir),
        "outputFile": format_repo_path(output_file),
        "districtCount": len(records_by_seat_id),
        "stateFileCount": len(state_files),
        "districtsBySeatId": records_by_seat_id,
        "stateFiles": state_summaries,
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = build_ballotpedia_house_index()
    view_payload = build_us_house_election_view()
    print(f"Wrote {payload['districtCount']} Ballotpedia U.S. House district records to {OUTPUT_FILE}")
    print(f"Refreshed {view_payload['seatCount']} U.S. House election views at {ELECTION_VIEW_OUTPUT_FILE}")


if __name__ == "__main__":
    main()
