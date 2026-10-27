"""National-overview parsing for Ballotpedia raw HTML."""
from __future__ import annotations

import html
import re
from datetime import datetime

from house_seat_parsing import STATE_NAMES
from senate_seat_ids import infer_senate_seat_id
from ..config import ELECTION_CYCLE_YEAR
from ..normalize import clean_name, norm_party

TAG_RE = re.compile(r"<[^>]+>")
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", flags=re.IGNORECASE | re.DOTALL)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", flags=re.IGNORECASE | re.DOTALL)
CELL_BLOCK_RE = re.compile(r"<t[dh][^>]*>.*?</t[dh]>", flags=re.IGNORECASE | re.DOTALL)
TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", flags=re.IGNORECASE | re.DOTALL)
CAPTION_RE = re.compile(r"<caption[^>]*>(.*?)</caption>", flags=re.IGNORECASE | re.DOTALL)
HEADING_RE = re.compile(r'<h([1-6])[^>]*>\s*<span[^>]*id="([^"]+)"[^>]*>(.*?)</span>\s*</h\1>', flags=re.IGNORECASE | re.DOTALL)

ORDINAL_RE = re.compile(r"(\d+)(?:st|nd|rd|th)?", flags=re.IGNORECASE)
AT_LARGE_RE = re.compile(r"AT[-\s]?LARGE", flags=re.IGNORECASE)
PARTY_DOT_RE = re.compile(r'aria-label="([^"]+)"', flags=re.IGNORECASE)
CLASS_ROMAN_RE = re.compile(r"\bCLASS\s+(I{1,3}|IV|V|VI)\b", flags=re.IGNORECASE)
CLASS_DIGIT_RE = re.compile(r"\bCLASS\s+([123])\b", flags=re.IGNORECASE)
DATE_FORMATS = ("%b. %d, %Y", "%B %d, %Y")


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub("", html.unescape(value))).strip()


def _seat_from_district_text(text: str) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    state_code = None
    for state_name, code in STATE_NAMES.items():
        if lowered.startswith(f"{state_name}'s") or lowered.startswith(f"{state_name}'") or lowered.startswith(f"{state_name} "):
            state_code = code
            break
    if not state_code:
        return None

    if AT_LARGE_RE.search(normalized):
        return f"{state_code}-AL"

    ordinal_match = ORDINAL_RE.search(normalized)
    if not ordinal_match:
        return None
    return f"{state_code}-{int(ordinal_match.group(1))}"


def _state_code_from_text(text: str) -> str | None:
    lowered = text.lower().strip()
    for state_name, code in STATE_NAMES.items():
        if lowered.startswith(f"{state_name}'s") or lowered.startswith(f"{state_name}'") or lowered.startswith(f"{state_name} "):
            return code
        if lowered == state_name:
            return code
    short_match = re.search(r"\b([A-Z]{2})\b", text.upper())
    if short_match:
        return short_match.group(1)
    return None


def _class_hint_from_text(text: str) -> int | None:
    roman_map = {"I": 1, "II": 2, "III": 3}
    upper = text.upper()
    digit_match = CLASS_DIGIT_RE.search(upper)
    if digit_match:
        return int(digit_match.group(1))
    roman_match = CLASS_ROMAN_RE.search(upper)
    if roman_match:
        return roman_map.get(roman_match.group(1))
    return None


def _seat_from_senate_text(text: str) -> str | None:
    upper = text.upper()
    state_code = _state_code_from_text(text)
    if not state_code:
        return None
    if "SENATE" not in upper and "CLASS" not in upper and "SPECIAL" not in upper:
        return None
    class_hint = _class_hint_from_text(upper)
    is_special = "SPECIAL" in upper
    return infer_senate_seat_id(
        state_code=state_code,
        cycle_year=ELECTION_CYCLE_YEAR,
        is_special=is_special,
        class_hint=class_hint,
    )


def _seat_from_state_name_for_senate(text: str) -> str | None:
    state_code = _state_code_from_text(text)
    if not state_code:
        return None
    return infer_senate_seat_id(
        state_code=state_code,
        cycle_year=ELECTION_CYCLE_YEAR,
        is_special=False,
        class_hint=2,
    )


def _extract_targeted_seats(page_html: str, headline_id: str) -> set[str]:
    anchor = page_html.find(f'id="{headline_id}"')
    if anchor < 0:
        return set()

    section = page_html[anchor:]
    table_match = TABLE_RE.search(section)
    if not table_match:
        return set()

    seats: set[str] = set()
    for row_html in ROW_RE.findall(table_match.group(1)):
        cells = CELL_RE.findall(row_html)
        if not cells:
            continue
        district = _strip_tags(cells[0])
        if district.lower() in {"district", "state", "seat"}:
            continue
        seat = _seat_from_district_text(district)
        if not seat:
            seat = _seat_from_senate_text(district)
        if seat:
            seats.add(seat)
    return seats


def _extract_table_near_heading(page_html: str, heading_id: str) -> str | None:
    heading_match = re.search(rf'id="{re.escape(heading_id)}"', page_html, flags=re.IGNORECASE)
    if not heading_match:
        return None
    section = page_html[heading_match.end():]
    table_match = TABLE_RE.search(section)
    if not table_match:
        return None
    return table_match.group(0)


def _extract_table_headers_and_rows(table_html: str) -> tuple[list[str], list[list[str]], list[list[str]]]:
    header_rows = re.findall(r"<thead[^>]*>(.*?)</thead>", table_html, flags=re.IGNORECASE | re.DOTALL)
    headers: list[str] = []
    if header_rows:
        first_header_row = re.search(r"<tr[^>]*>(.*?)</tr>", header_rows[0], flags=re.IGNORECASE | re.DOTALL)
        if first_header_row:
            headers = [_strip_tags(cell) for cell in CELL_BLOCK_RE.findall(first_header_row.group(1))]

    parsed_rows: list[list[str]] = []
    raw_rows: list[list[str]] = []
    tbody_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", table_html, flags=re.IGNORECASE | re.DOTALL)
    if not tbody_match:
        return headers, parsed_rows, raw_rows
    for row_html in ROW_RE.findall(tbody_match.group(1)):
        cell_html = CELL_BLOCK_RE.findall(row_html)
        if not cell_html:
            continue
        raw_rows.append(cell_html)
        parsed_rows.append([_strip_tags(cell) for cell in cell_html])
    return headers, parsed_rows, raw_rows


def _parse_party(value: str) -> str:
    text = value.strip().upper()
    if text == "DEMOCRAT":
        return "D"
    if text == "REPUBLICAN":
        return "R"
    if text == "DEMOCRATIC":
        return "D"
    return norm_party(text)


def _clean_person_name(value: str) -> str:
    cleaned = re.sub(r"\[\d+\]", "", value)
    return clean_name(cleaned)


def _parse_date_or_empty(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.replace("Sept.", "Sep."), fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def _district_text_from_cell(cell_html: str, cell_text: str) -> str:
    title_match = re.search(r'title="([^"]+)"', cell_html, flags=re.IGNORECASE)
    if title_match:
        return _strip_tags(title_match.group(1))
    return cell_text


def _party_from_cell(cell_html: str, cell_text: str) -> str:
    label_match = PARTY_DOT_RE.search(cell_html)
    if label_match:
        return _parse_party(label_match.group(1))
    return _parse_party(cell_text)


def parse_national_incumbent_tables(
    page_html: str,
    source_url: str | None = None,
    *,
    office: str = "us_house",
) -> tuple[dict[str, dict], list[dict]]:
    by_seat: dict[str, dict] = {}
    departures: list[dict] = []

    def upsert_entry(entry: dict) -> None:
        seat = entry["seat"]
        existing = by_seat.get(seat)
        priority = {
            "defeated_general": 5,
            "defeated_primary": 4,
            "seeking_other_office": 3,
            "retiring": 2,
            "running": 1,
            "vacant_or_unknown": 0,
        }
        if existing is None or priority.get(entry["incumbent_status"], 0) >= priority.get(existing.get("incumbent_status", ""), 0):
            by_seat[seat] = {
                "incumbent_name": entry["name"],
                "incumbent_party": entry["party"],
                "incumbent_status": entry["incumbent_status"],
                "departure_reason": entry["departure_reason"],
                "departure_subreason": entry["departure_subreason"],
            }

    def parse_open_seat_table(heading_id: str, reason: str, subreason: str = "") -> None:
        table_html = _extract_table_near_heading(page_html, heading_id)
        if not table_html:
            return
        headers, parsed_rows, raw_rows = _extract_table_headers_and_rows(table_html)
        header_idx = {name.lower(): idx for idx, name in enumerate(headers)}
        name_idx = header_idx.get("name", 0)
        party_idx = header_idx.get("party", 1)
        seat_idx = header_idx.get("seat", 2)
        date_idx = header_idx.get("date announced", 3)
        for row, raw_row in zip(parsed_rows, raw_rows):
            if len(row) <= max(name_idx, party_idx, seat_idx):
                continue
            seat_text = _district_text_from_cell(raw_row[seat_idx], row[seat_idx])
            if office == "us_senate":
                seat = _seat_from_state_name_for_senate(seat_text) or _seat_from_senate_text(seat_text)
            else:
                seat = _seat_from_district_text(seat_text)
            if not seat:
                continue
            name = _clean_person_name(row[name_idx])
            party = _parse_party(row[party_idx])
            date_announced = _parse_date_or_empty(row[date_idx] if date_idx < len(row) else "")
            entry = {
                "name": name,
                "party": party,
                "seat": seat,
                "departure_reason": reason,
                "departure_subreason": subreason,
                "date_announced": date_announced,
                "source_section": heading_id,
                "source_url": source_url or "",
                "notes": "",
                "incumbent_status": "retiring" if reason == "retiring" else "seeking_other_office",
            }
            departures.append(entry)
            upsert_entry(entry)

    if office == "us_senate":
        senate_cycle_table = _extract_table_by_caption(page_html, f"{ELECTION_CYCLE_YEAR} Senate elections")
        if senate_cycle_table:
            headers, parsed_rows, raw_rows = _extract_table_headers_and_rows(senate_cycle_table)
            header_idx = {name.lower(): idx for idx, name in enumerate(headers)}
            state_idx = header_idx.get("state", 0)
            incumbent_idx = header_idx.get("pre-election incumbent", 1)
            for row, raw_row in zip(parsed_rows, raw_rows):
                if len(row) <= max(state_idx, incumbent_idx):
                    continue
                seat = _seat_from_state_name_for_senate(row[state_idx])
                if not seat:
                    continue
                incumbent_name = _clean_person_name(row[incumbent_idx])
                incumbent_party = _party_from_cell(raw_row[incumbent_idx], row[incumbent_idx])
                if not incumbent_name:
                    continue
                upsert_entry(
                    {
                        "name": incumbent_name,
                        "party": incumbent_party,
                        "seat": seat,
                        "departure_reason": "",
                        "departure_subreason": "",
                        "date_announced": "",
                        "source_section": f"{ELECTION_CYCLE_YEAR} Senate elections",
                        "source_url": source_url or "",
                        "notes": "",
                        "incumbent_status": "running",
                    }
                )

        parse_open_seat_table("Incumbents_retiring_from_public_office", "retiring")
        parse_open_seat_table("Incumbents_seeking_other_offices", "seeking_other_office")
        parse_open_seat_table("Incumbents_running_for_governor", "seeking_other_office", "governor")
    else:
        parse_open_seat_table("Incumbents_retiring_from_public_office", "retiring")
        parse_open_seat_table("Representatives_running_for_a_U.S._Senate_seat", "seeking_other_office", "senate")
        parse_open_seat_table("Representatives_running_for_governor", "seeking_other_office", "governor")
        parse_open_seat_table("Representatives_running_for_attorney_general", "seeking_other_office", "attorney_general")

    defeated_table_html = _extract_table_near_heading(page_html, "Incumbents_defeated")
    if defeated_table_html:
        headers, parsed_rows, raw_rows = _extract_table_headers_and_rows(defeated_table_html)
        header_idx = {name.lower(): idx for idx, name in enumerate(headers)}
        name_idx = header_idx.get("name", 0)
        district_idx = header_idx.get("district", 1)
        phase_idx = header_idx.get("primary of general election?", 2)
        for row, raw_row in zip(parsed_rows, raw_rows):
            if len(row) <= max(name_idx, district_idx, phase_idx):
                continue
            district_text = _district_text_from_cell(raw_row[district_idx], row[district_idx])
            if office == "us_senate":
                seat = _seat_from_state_name_for_senate(district_text) or _seat_from_senate_text(district_text)
            else:
                seat = _seat_from_district_text(district_text)
            if not seat:
                continue
            phase = row[phase_idx].strip().lower()
            status = "defeated_general" if "general" in phase else "defeated_primary"
            party = _party_from_cell(raw_row[name_idx], row[name_idx])
            entry = {
                "name": _clean_person_name(row[name_idx]),
                "party": party,
                "seat": seat,
                "departure_reason": "defeated",
                "departure_subreason": "general" if status == "defeated_general" else "primary",
                "date_announced": "",
                "source_section": "Incumbents_defeated",
                "source_url": source_url or "",
                "notes": "",
                "incumbent_status": status,
            }
            departures.append(entry)
            upsert_entry(entry)

    return by_seat, departures


def _extract_table_by_caption(page_html: str, caption_text: str) -> str | None:
    for table_html in re.findall(r"<table[^>]*>.*?</table>", page_html, flags=re.IGNORECASE | re.DOTALL):
        caption_match = re.search(r"<caption[^>]*>(.*?)</caption>", table_html, flags=re.IGNORECASE | re.DOTALL)
        if not caption_match:
            continue
        caption_clean = _strip_tags(caption_match.group(1))
        if caption_clean.strip().lower() == caption_text.strip().lower():
            return table_html
    return None


def parse_national_targeting(page_html: str) -> tuple[dict[str, dict[str, bool]], dict[str, object]]:
    dccc_seats = _extract_targeted_seats(page_html, "DCCC_targets")
    nrcc_seats = _extract_targeted_seats(page_html, "NRCC_targets")
    dscc_seats = _extract_targeted_seats(page_html, "DSCC_targets")
    nrsc_seats = _extract_targeted_seats(page_html, "NRSC_targets")

    targeting: dict[str, dict[str, bool]] = {}
    for seat in sorted(dccc_seats | nrcc_seats | dscc_seats | nrsc_seats):
        targeting[seat] = {
            "dccc_target": seat in dccc_seats,
            "nrcc_target": seat in nrcc_seats,
            "dscc_target": seat in dscc_seats,
            "nrsc_target": seat in nrsc_seats,
        }

    plan = {
        "source": "National.txt",
        "tables": {
            "dccc": {
                "headlineId": "DCCC_targets",
                "expectedColumns": ["District", "Incumbent", "Winner", "2024 margin"],
            },
            "nrcc": {
                "headlineId": "NRCC_targets",
                "expectedColumns": ["District", "Incumbent", "Winner", "2024 margin"],
            },
            "dscc": {
                "headlineId": "DSCC_targets",
                "expectedColumns": ["State/Seat", "Incumbent", "Winner", "2024 margin"],
            },
            "nrsc": {
                "headlineId": "NRSC_targets",
                "expectedColumns": ["State/Seat", "Incumbent", "Winner", "2024 margin"],
            },
        },
    }

    return targeting, plan
