"""District-detail page parsing for Ballotpedia raw HTML."""
from __future__ import annotations

import html
import re
from pathlib import Path

from ..config import ELECTION_CYCLE_YEAR
from ..election_dates import extract_election_dates, get_validation_date, parse_iso_date
from ..ids import make_primary_id
from ..meta import extract_meta
from ..normalize import clean_name, norm_party, parse_int_votes, parse_pct
from ..seat import parse_seat_from_filename

DIV_TAG_RE = re.compile(r"<(/?)div\b([^>]*)>", flags=re.IGNORECASE)
ROW_RE = re.compile(r'<tr class="([^"]*results_row[^"]*)"[^>]*>(.*?)</tr>', flags=re.IGNORECASE | re.DOTALL)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", flags=re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
CLASS_ATTR_RE = re.compile(r'class=["\']([^"\']+)["\']', flags=re.IGNORECASE)
TD_WITH_ATTRS_RE = re.compile(r"<td([^>]*)>(.*?)</td>", flags=re.IGNORECASE | re.DOTALL)
TR_WITH_CLASS_RE = re.compile(r'<tr[^>]*class="([^"]*)"[^>]*>(.*?)</tr>', flags=re.IGNORECASE | re.DOTALL)
TABLE_CELL_ANY_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", flags=re.IGNORECASE | re.DOTALL)
RACE_RATINGS_SECTION_RE = re.compile(
    r'id="General_election_race_ratings".*?<table[^>]*>(.*?)</table>',
    flags=re.IGNORECASE | re.DOTALL,
)
TABLE_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", flags=re.IGNORECASE | re.DOTALL)
TABLE_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", flags=re.IGNORECASE | re.DOTALL)
PRIMARY_HEADING_RE = re.compile(
    r"(?P<party>Democratic|Republican|Green|Libertarian|Nonpartisan|Top-two)\s+primary candidates</span>",
    flags=re.IGNORECASE,
)
NO_FILING_RE = re.compile(r"no\s+candidates\s+filed\s+for\s+this\s+race", flags=re.IGNORECASE)
CANCELED_ADVANCED_RE = re.compile(
    r"this\s+primary\s+was\s+canceled\s+and\s+this\s+candidate\s+advanced",
    flags=re.IGNORECASE,
)
BLOCK_DATE_YEAR_RE = re.compile(r"\bon\s+[A-Za-z]+\s+\d{1,2},\s+(20\d{2})\b", flags=re.IGNORECASE)
GENERIC_YEAR_RE = re.compile(r"\b(20\d{2})\b")
HISTORICAL_YEARS = ("2024", "2022", "2020")

RACE_RATING_TAG_BY_OUTLET = {
    "Larry J. Sabato's Crystal Ball": "most_recent_poll_larry_j_sabatos_crystal_ball",
    "Inside Elections with Nathan L. Gonzales": "most_recent_poll_inside_elections_with_nathan_l_gonzales",
    "Decision Desk HQ and The Hill": "most_recent_poll_decision_desk_hq_and_the_hill",
    "The Cook Political Report with Amy Walter": "most_recent_poll_the_cook_political_report_with_amy_walter",
}


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub("", html.unescape(value))).strip()


def _extract_div_blocks_by_class(page_html: str, class_name: str) -> list[str]:
    blocks: list[str] = []
    for match in DIV_TAG_RE.finditer(page_html):
        if match.group(1) == "/":
            continue
        attrs = match.group(2)
        class_match = CLASS_ATTR_RE.search(attrs)
        if not class_match:
            continue
        classes = set(class_match.group(1).split())
        if class_name not in classes:
            continue
        start = match.start()
        depth = 0
        end = None
        for nested_match in DIV_TAG_RE.finditer(page_html, start):
            is_close = nested_match.group(1) == "/"
            if not is_close:
                depth += 1
            else:
                depth -= 1
            if depth == 0:
                end = nested_match.end()
                break
        if end is not None:
            blocks.append(page_html[start:end])
    return blocks


def _extract_candidates_from_block(block: str) -> tuple[list[dict], int | None, bool]:
    candidates: list[dict] = []
    vote_values: list[int] = []
    has_votes = False
    vote_column_index = _detect_vote_column_index(block)
    legend_total_votes = _extract_legend_total_votes(block)
    for row_match in ROW_RE.finditer(block):
        row_class = row_match.group(1)
        row_html = row_match.group(2)
        cells = TD_RE.findall(row_html)
        if len(cells) < 3:
            continue
        text_cell = cells[2]
        raw_text = _strip_tags(text_cell)
        if not raw_text:
            continue
        anchor_match = re.search(r">([^<]+)</a>", text_cell)
        name = clean_name(anchor_match.group(1) if anchor_match else raw_text.split("(")[0])
        party_match = re.findall(r"\(([^()]*)\)", raw_text)
        party_raw = party_match[-1] if party_match else ""
        party = norm_party(party_raw)
        number_cells = [
            _strip_tags(content)
            for attrs, content in TD_WITH_ATTRS_RE.findall(row_html)
            if "votebox-results-cell--number" in attrs
        ]
        percent = parse_pct(number_cells[0]) if number_cells else None
        row_cells = TD_WITH_ATTRS_RE.findall(row_html)
        votes = None
        if vote_column_index is not None and 0 <= vote_column_index < len(row_cells):
            votes = parse_int_votes(_strip_tags(row_cells[vote_column_index][1]))
        if votes is None and len(number_cells) > 1:
            # Fallback for layouts where numeric vote columns are not aligned to header index.
            votes = parse_int_votes(number_cells[1])
        if votes is None and number_cells:
            votes = parse_int_votes(number_cells[-1])
        if votes is not None:
            vote_values.append(votes)
            has_votes = True
        is_winner = "winner" in row_class
        is_incumbent = "incumbent" in raw_text.lower()
        candidates.append(
            {
                "name": name,
                "party": party,
                "raw_party": party_raw,
                "votes": votes,
                "percent": percent,
                "is_winner": is_winner,
                "is_incumbent": is_incumbent,
                "raw_text": raw_text,
            }
        )
    vote_total = sum(vote_values) if vote_values else None
    if legend_total_votes is not None:
        vote_total = legend_total_votes
        has_votes = legend_total_votes > 0
    return candidates, vote_total, has_votes


def _detect_vote_column_index(block: str) -> int | None:
    for class_value, row_html in TR_WITH_CLASS_RE.findall(block):
        if "non_result_row" not in class_value:
            continue
        headers = [_strip_tags(cell).lower() for cell in TABLE_CELL_ANY_RE.findall(row_html)]
        for index, header in enumerate(headers):
            if "total votes" in header:
                return index
    return None


def _extract_legend_total_votes(block: str) -> int | None:
    matches = [parse_int_votes(item) for item in re.findall(r"Total votes:\s*([0-9][0-9,]*)", block, flags=re.IGNORECASE)]
    numeric = [value for value in matches if value is not None]
    if not numeric:
        return None
    return max(numeric)


def _extract_incumbent_from_results_text(block: str) -> str | None:
    paragraph_match = re.search(r'<p class="results_text">(.*?)</p>', block, flags=re.IGNORECASE | re.DOTALL)
    if not paragraph_match:
        return None
    paragraph_html = paragraph_match.group(1)
    lower_paragraph = paragraph_html.lower()
    incumbent_idx = lower_paragraph.find("incumbent")
    if incumbent_idx == -1:
        return None
    incumbent_fragment = paragraph_html[incumbent_idx:]
    anchor_match = re.search(r">\s*([^<]+?)\s*</a>", incumbent_fragment, flags=re.IGNORECASE | re.DOTALL)
    if anchor_match:
        return clean_name(anchor_match.group(1))
    paragraph_text = _strip_tags(incumbent_fragment)
    name_match = re.search(r"incumbent\s+([^,.;]+?)(?:,| and | is | was | are )", paragraph_text, flags=re.IGNORECASE)
    if name_match:
        return clean_name(name_match.group(1))
    return None


def _extract_general_election_race_ratings(page_html: str) -> dict:
    section_match = RACE_RATINGS_SECTION_RE.search(page_html)
    if not section_match:
        return {"most_recent_poll_tags": []}

    table_html = section_match.group(1)
    rows = TABLE_ROW_RE.findall(table_html)
    parsed_rows: list[list[str]] = []
    for row_html in rows:
        cells = [_strip_tags(cell) for cell in TABLE_CELL_RE.findall(row_html)]
        if cells:
            parsed_rows.append(cells)

    latest_date: str | None = None
    for row in parsed_rows:
        if len(row) >= 2 and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", row[1]):
            latest_date = row[1]
            break

    outlet_ratings: list[dict[str, str]] = []
    tags: list[str] = []
    for row in parsed_rows:
        if len(row) < 2:
            continue
        outlet = row[0].strip()
        tag = RACE_RATING_TAG_BY_OUTLET.get(outlet)
        if not tag:
            continue
        rating = row[1].strip()
        outlet_ratings.append({
            "outlet": outlet,
            "rating": rating,
            "tag": tag,
        })
        tags.append(tag)

    return {
        "most_recent_poll_date": latest_date,
        "outlet_ratings": outlet_ratings,
        "most_recent_poll_tags": tags,
    }


def _party_from_primary_heading(heading_party: str) -> str:
    heading_lower = heading_party.lower()
    if "democratic" in heading_lower:
        return "D"
    if "republican" in heading_lower:
        return "R"
    if "green" in heading_lower:
        return "G"
    if "libertarian" in heading_lower:
        return "L"
    if "nonpartisan" in heading_lower or "top-two" in heading_lower:
        return "NP"
    return "OTH"


def _extract_party_primary_reasons_from_page(page_html: str) -> dict[str, str]:
    reasons: dict[str, str] = {}
    heading_matches = list(PRIMARY_HEADING_RE.finditer(page_html))
    for index, match in enumerate(heading_matches):
        heading_party = match.group("party")
        party_code = _party_from_primary_heading(heading_party)
        if party_code not in {"D", "R", "NP"}:
            continue
        start = match.end()
        end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(page_html)
        section_html = page_html[start:end]
        if NO_FILING_RE.search(section_html):
            reasons[party_code] = "no_filing"
        elif CANCELED_ADVANCED_RE.search(section_html):
            reasons[party_code] = "unopposed"
    return reasons


def _infer_primary_cancellation_reason(block_html: str, candidate_count: int) -> str:
    if NO_FILING_RE.search(block_html):
        return "no_filing"
    if candidate_count == 1 and CANCELED_ADVANCED_RE.search(block_html):
        return "unopposed"
    return ""


def _is_target_cycle_block(block_html: str, target_year: int = 2026) -> bool:
    """Keep only blocks for the active cycle while dropping historical race tables."""
    text = _strip_tags(block_html)
    years = [int(item) for item in BLOCK_DATE_YEAR_RE.findall(text)]
    if years:
        return target_year in years
    return str(target_year) in block_html


def _extract_block_year(block_html: str) -> str | None:
    text = _strip_tags(block_html)
    dated_years = BLOCK_DATE_YEAR_RE.findall(text)
    if dated_years:
        return str(dated_years[0])
    generic_years = GENERIC_YEAR_RE.findall(text)
    if generic_years:
        return str(generic_years[0])
    return None


def _empty_historical_primary_year() -> dict[str, str]:
    return {"D": "unknown", "R": "unknown"}


def _extract_historical_vote_totals(voteboxes: list[str]) -> tuple[dict[str, int], dict[str, dict[str, int]], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    general_totals: dict[str, int] = {}
    primary_totals: dict[str, dict[str, int]] = {year: {} for year in HISTORICAL_YEARS}
    primary_status: dict[str, dict[str, str]] = {year: _empty_historical_primary_year() for year in HISTORICAL_YEARS}
    primary_reason: dict[str, dict[str, str]] = {year: {"D": "", "R": ""} for year in HISTORICAL_YEARS}

    for block in voteboxes:
        year = _extract_block_year(block)
        if year not in HISTORICAL_YEARS:
            continue
        election_type_match = re.search(r'votebox-header-election-type">(.*?)</h5>', block, flags=re.IGNORECASE | re.DOTALL)
        election_type = _strip_tags(election_type_match.group(1) if election_type_match else "")
        lower_type = election_type.lower()
        candidates, vote_total, has_votes = _extract_candidates_from_block(block)
        if "general election" in lower_type:
            if has_votes and vote_total is not None:
                existing = general_totals.get(year)
                is_special_general = "special general election" in lower_type
                if existing is None or (not is_special_general):
                    general_totals[year] = int(vote_total)
            continue
        if "primary" not in lower_type or "runoff" in lower_type:
            continue

        party = "NP"
        if "democratic" in lower_type:
            party = "D"
        elif "republican" in lower_type:
            party = "R"
        if party not in {"D", "R"}:
            continue

        if candidates and has_votes and vote_total is not None:
            primary_totals[year][party] = int(vote_total)
            primary_status[year][party] = "complete"
            continue

        cancellation_reason = _infer_primary_cancellation_reason(block, len(candidates))
        if cancellation_reason:
            primary_status[year][party] = "none"
            primary_reason[year][party] = cancellation_reason
        elif candidates:
            primary_status[year][party] = "unknown"
        else:
            primary_status[year][party] = "unknown"

    for year in HISTORICAL_YEARS:
        if year not in general_totals:
            continue
        statuses = primary_status.get(year) or {}
        reasons = primary_reason.get(year) or {}
        for party in ("D", "R"):
            if statuses.get(party) == "unknown" and party not in (primary_totals.get(year) or {}):
                statuses[party] = "none"
                if not reasons.get(party):
                    reasons[party] = "no_primary_structure"

    return general_totals, primary_totals, primary_status, primary_reason


def parse_district_detail_file(page_html: str, source_file: str, *, office: str = "us_house") -> tuple[dict | None, list[dict]]:
    state, district, seat = parse_seat_from_filename(source_file, office=office)
    if district in {"STATE_ROLLUP", "NATIONAL"}:
        return None, []

    metadata = extract_meta(page_html, Path(source_file))
    race_ratings = _extract_general_election_race_ratings(page_html)
    election_dates = extract_election_dates(page_html)
    validation_date = get_validation_date()
    voteboxes = _extract_div_blocks_by_class(page_html, "votebox")
    current_boxes = [box for box in voteboxes if _is_target_cycle_block(box, target_year=ELECTION_CYCLE_YEAR)]

    general_row = {
        "seat": seat,
        "state": state,
        "district": district,
        "incumbent_name": None,
        "incumbent_party": None,
        "incumbent_status": "",
        "fec_incumbent_name": "",
        "fec_incumbent_party": "",
        "fec_incumbent_conflict": "",
        "nominee_d": None,
        "nominee_r": None,
        "nominee_green": None,
        "nominee_libertarian": None,
        "other_general_candidates": [],
        "primary_status_d": "none",
        "primary_status_r": "none",
        "primary_status_np": "none",
        "primary_reason_d": "",
        "primary_reason_r": "",
        "primary_reason_np": "",
        "primary_id_d": None,
        "primary_id_r": None,
        "primary_id_np": None,
        "general_vote_total": None,
        "general_status": "unknown",
        "primary_date": election_dates.get("primary_date") or "",
        "runoff_date": election_dates.get("runoff_date") or "",
        "general_date": election_dates.get("general_date") or "",
        "filing_deadline": election_dates.get("filing_deadline") or "",
        "source_file": source_file,
        "source_url": metadata.get("source_url"),
        "general_election_race_ratings": race_ratings,
        "historical_general_vote_totals": {},
        "historical_primary_vote_totals": {},
        "historical_primary_status": {},
        "historical_primary_reason": {},
        "parser_notes": ["district_detail_preferred"],
        "source_priority": 2,
    }

    primary_rows: list[dict] = []
    saw_general_block = False
    saw_general_candidates = False
    general_parties_present: set[str] = set()
    saw_incumbent_marker = False
    ignored_votes_before_date = False
    for block in current_boxes:
        election_type_match = re.search(r'votebox-header-election-type">(.*?)</h5>', block, flags=re.IGNORECASE | re.DOTALL)
        election_type = _strip_tags(election_type_match.group(1) if election_type_match else "")
        candidates, vote_total, has_votes = _extract_candidates_from_block(block)
        lower_type = election_type.lower()
        if "general election" in lower_type:
            saw_general_block = True
            if candidates:
                saw_general_candidates = True
            general_date_value = parse_iso_date(election_dates.get("general_date") or "")
            has_effective_votes = bool(has_votes and general_date_value and general_date_value <= validation_date)
            if has_votes and not has_effective_votes:
                ignored_votes_before_date = True
            general_row["general_status"] = "complete" if has_effective_votes else "upcoming"
            general_row["general_vote_total"] = vote_total if has_effective_votes else None
            general_row["source_priority"] = 3 if vote_total is not None else 2
            incumbent_from_text = _extract_incumbent_from_results_text(block)
            if incumbent_from_text:
                saw_incumbent_marker = True
                if not general_row["incumbent_name"]:
                    general_row["incumbent_name"] = incumbent_from_text
            for candidate in candidates:
                general_parties_present.add(candidate["party"])
                if candidate["is_incumbent"] and not general_row["incumbent_name"]:
                    general_row["incumbent_name"] = candidate["name"]
                    general_row["incumbent_party"] = candidate["party"]
                if candidate["is_incumbent"]:
                    saw_incumbent_marker = True
                if general_row["incumbent_name"] == candidate["name"] and (
                    general_row["incumbent_party"] is None
                    or (general_row["incumbent_party"] == "OTH" and candidate["party"] != "OTH")
                ):
                    general_row["incumbent_party"] = candidate["party"]
                if candidate["party"] == "D" and not general_row["nominee_d"]:
                    general_row["nominee_d"] = candidate["name"]
                elif candidate["party"] == "R" and not general_row["nominee_r"]:
                    general_row["nominee_r"] = candidate["name"]
                elif candidate["party"] == "G" and not general_row["nominee_green"]:
                    general_row["nominee_green"] = candidate["name"]
                elif candidate["party"] == "L" and not general_row["nominee_libertarian"]:
                    general_row["nominee_libertarian"] = candidate["name"]
                elif candidate["name"] not in general_row["other_general_candidates"]:
                    general_row["other_general_candidates"].append(candidate["name"])
            continue

        if not candidates:
            continue
        if "primary" in lower_type or "top-two" in lower_type:
            party = "NP"
            if "democratic" in lower_type:
                party = "D"
            elif "republican" in lower_type:
                party = "R"
            elif "libertarian" in lower_type:
                party = "L"
            elif "green" in lower_type:
                party = "G"
            round_name = "runoff" if "runoff" in lower_type else ("top_two" if "top-two" in lower_type else "primary")
            if round_name == "runoff":
                round_date = parse_iso_date(election_dates.get("runoff_date") or "")
                has_effective_votes = bool(has_votes and round_date and round_date <= validation_date)
                if has_votes and not has_effective_votes:
                    ignored_votes_before_date = True
                status = "complete" if has_effective_votes else "runoff"
            else:
                round_date = parse_iso_date(election_dates.get("primary_date") or "")
                has_effective_votes = bool(has_votes and round_date and round_date <= validation_date)
                if has_votes and not has_effective_votes:
                    ignored_votes_before_date = True
                status = "complete" if has_effective_votes else "upcoming"
            cancellation_reason = _infer_primary_cancellation_reason(block, len(candidates))
            primary_id = make_primary_id(seat, party, round_name)
            vote_share = {c["name"]: c["percent"] for c in candidates if c.get("percent") is not None}
            vote_count = {c["name"]: c["votes"] for c in candidates if c.get("votes") is not None}
            runoff_names = [c["name"] for c in candidates[:2]] if round_name == "runoff" else []
            primary_rows.append(
                {
                    "primary_id": primary_id,
                    "seat": seat,
                    "state": state,
                    "district": district,
                    "party": party,
                    "round": round_name,
                    "status": status,
                    "cancellation_reason": cancellation_reason,
                    "candidates": [c["name"] for c in candidates],
                    "primary_vote_total": vote_total if has_effective_votes else None,
                    "primary_date": election_dates.get("primary_date") or "",
                    "runoff_date": election_dates.get("runoff_date") or "",
                    "primary_vote_share": vote_share if has_effective_votes else {},
                    "primary_vote_count": vote_count if has_effective_votes else {},
                    "candidate_party_map": {c["name"]: c.get("party") for c in candidates if c.get("name")},
                    "candidate_incumbent_map": {c["name"]: bool(c.get("is_incumbent")) for c in candidates if c.get("name")},
                    "runoff_candidate_1": runoff_names[0] if len(runoff_names) > 0 else None,
                    "runoff_candidate_2": runoff_names[1] if len(runoff_names) > 1 else None,
                    "runoff_id": None,
                    "parent_primary_id": None,
                    "source_file": source_file,
                    "source_url": metadata.get("source_url"),
                    "parser_notes": [],
                    "source_priority": 3 if has_votes else 2,
                }
            )
            if party == "D":
                general_row["primary_status_d"] = status
                general_row["primary_id_d"] = primary_id
                general_row["primary_reason_d"] = cancellation_reason
            if party == "R":
                general_row["primary_status_r"] = status
                general_row["primary_id_r"] = primary_id
                general_row["primary_reason_r"] = cancellation_reason
            if party == "NP":
                general_row["primary_status_np"] = status
                general_row["primary_id_np"] = primary_id
                general_row["primary_reason_np"] = cancellation_reason

    inferred_reasons = _extract_party_primary_reasons_from_page(page_html)
    for party_code, reason in inferred_reasons.items():
        if party_code == "D":
            field_name = "primary_reason_d"
        elif party_code == "R":
            field_name = "primary_reason_r"
        else:
            field_name = "primary_reason_np"
        if not general_row.get(field_name):
            general_row[field_name] = reason

    historical_boxes = [box for box in voteboxes if not _is_target_cycle_block(box, target_year=ELECTION_CYCLE_YEAR)]
    historical_general, historical_primary, historical_status, historical_reason = _extract_historical_vote_totals(historical_boxes)
    general_row["historical_general_vote_totals"] = historical_general
    general_row["historical_primary_vote_totals"] = historical_primary
    general_row["historical_primary_status"] = historical_status
    general_row["historical_primary_reason"] = historical_reason

    if general_row["incumbent_name"] is None:
        general_row["parser_notes"].append(
            "source_missing_incumbent_marker" if saw_general_block and not saw_incumbent_marker else "source_missing_incumbent_field"
        )
    else:
        general_row["parser_notes"].append("incumbent_from_district_detail")
    for party_code, field_name, note_name in (
        ("D", "nominee_d", "source_missing_nominee_d"),
        ("R", "nominee_r", "source_missing_nominee_r"),
        ("G", "nominee_green", "source_missing_nominee_green"),
        ("L", "nominee_libertarian", "source_missing_nominee_libertarian"),
    ):
        if general_row[field_name] is None and (not saw_general_candidates or party_code not in general_parties_present):
            general_row["parser_notes"].append(note_name)
    if not saw_general_block:
        general_row["parser_notes"].append("source_missing_general_election_section")
    elif not saw_general_candidates:
        general_row["parser_notes"].append("source_missing_general_candidates")
    if not (general_row.get("primary_date") and general_row.get("general_date")):
        general_row["parser_notes"].append("missing_election_dates")
    if ignored_votes_before_date:
        general_row["parser_notes"].append("votes_ignored_before_election_date")

    if general_row["general_status"] == "unknown" and not primary_rows:
        return None, []
    return general_row, primary_rows
