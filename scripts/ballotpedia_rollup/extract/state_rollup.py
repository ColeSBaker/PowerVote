"""State-rollup page parsing for Ballotpedia raw HTML."""
from __future__ import annotations

import html
import re
from pathlib import Path

from ..election_dates import extract_election_dates
from ..ids import make_primary_id
from ..meta import extract_meta
from ..normalize import clean_name, norm_party
from ..seat import parse_seat_from_filename

TAG_RE = re.compile(r"<[^>]+>")
DISTRICT_RE = re.compile(r'id="District_(\d+|AL)"[^>]*>District\s+([0-9]+|AL)', flags=re.IGNORECASE)
HEADING_SPAN_RE = re.compile(r"<span[^>]*font-weight:\s*bold[^>]*>(.*?)</span>", flags=re.IGNORECASE | re.DOTALL)
UL_RE = re.compile(r"<ul>(.*?)</ul>", flags=re.IGNORECASE | re.DOTALL)
LI_RE = re.compile(r"<li>(.*?)</li>", flags=re.IGNORECASE | re.DOTALL)
NO_FILING_RE = re.compile(r"no\s+candidates\s+filed\s+for\s+this\s+race", flags=re.IGNORECASE)
CANCELED_ADVANCED_RE = re.compile(
    r"this\s+primary\s+was\s+canceled\s+and\s+this\s+candidate\s+advanced",
    flags=re.IGNORECASE,
)


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub("", html.unescape(value))).strip()


def _party_from_heading(heading: str) -> str:
    lower = heading.lower()
    if "democratic" in lower:
        return "D"
    if "republican" in lower:
        return "R"
    if "green" in lower:
        return "G"
    if "libertarian" in lower:
        return "L"
    if "nonpartisan" in lower or "top-two" in lower:
        return "NP"
    return "OTH"


def _extract_list_after(section_html: str, start_idx: int) -> list[dict]:
    ul_match = UL_RE.search(section_html, start_idx)
    if not ul_match:
        return []
    candidates = []
    for li in LI_RE.findall(ul_match.group(1)):
        raw = _strip_tags(li)
        anchor = re.search(r">([^<]+)</a>", li)
        name = clean_name(anchor.group(1) if anchor else raw)
        parens = re.findall(r"\(([^()]*)\)", raw)
        party = norm_party(parens[-1]) if parens else "OTH"
        candidates.append({"name": name, "party": party, "raw_text": raw})
    return candidates


def _compute_cancellation_reason(section_html: str, candidates: list[dict]) -> str:
    if NO_FILING_RE.search(section_html):
        return "no_filing"
    if len(candidates) == 1 and CANCELED_ADVANCED_RE.search(section_html):
        return "unopposed"
    return ""


def parse_state_rollup_file(page_html: str, source_file: str, *, office: str = "us_house") -> tuple[list[dict], list[dict]]:
    state, district, _seat = parse_seat_from_filename(source_file, office=office)
    if district != "STATE_ROLLUP":
        return [], []

    metadata = extract_meta(page_html, Path(source_file))
    election_dates = extract_election_dates(page_html)
    matches = list(DISTRICT_RE.finditer(page_html))
    general_rows: list[dict] = []
    primary_rows: list[dict] = []

    for index, district_match in enumerate(matches):
        district_number = district_match.group(1).upper()
        seat = f"{state}-{district_number}"
        start = district_match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page_html)
        section = page_html[start:end]

        row = {
            "seat": seat,
            "state": state,
            "district": district_number,
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
            "general_status": "upcoming",
            "historical_general_vote_totals": {},
            "historical_primary_vote_totals": {},
            "historical_primary_status": {},
            "historical_primary_reason": {},
            "primary_date": election_dates.get("primary_date") or "",
            "runoff_date": election_dates.get("runoff_date") or "",
            "general_date": election_dates.get("general_date") or "",
            "filing_deadline": election_dates.get("filing_deadline") or "",
            "source_file": source_file,
            "source_url": metadata.get("source_url"),
            "parser_notes": ["state_rollup_used", "missing_vote_totals"],
            "source_priority": 1,
        }
        saw_general_heading = False
        saw_general_candidates = False
        saw_incumbent_marker = False
        general_parties_present: set[str] = set()

        heading_matches = list(HEADING_SPAN_RE.finditer(section))
        for heading_index, heading_match in enumerate(heading_matches):
            heading = _strip_tags(heading_match.group(1))
            heading_lower = heading.lower()
            candidates = _extract_list_after(section, heading_match.end())
            heading_party = _party_from_heading(heading)
            next_heading_start = heading_matches[heading_index + 1].start() if heading_index + 1 < len(heading_matches) else len(section)
            heading_section = section[heading_match.end():next_heading_start]

            if "general election candidates" in heading_lower:
                saw_general_heading = True
                if candidates:
                    saw_general_candidates = True
                for candidate in candidates:
                    general_parties_present.add(candidate["party"])
                    if "incumbent" in candidate["raw_text"].lower() and row["incumbent_name"] is None:
                        row["incumbent_name"] = candidate["name"]
                        row["incumbent_party"] = candidate["party"]
                    if "incumbent" in candidate["raw_text"].lower():
                        saw_incumbent_marker = True
                    if candidate["party"] == "D" and row["nominee_d"] is None:
                        row["nominee_d"] = candidate["name"]
                    elif candidate["party"] == "R" and row["nominee_r"] is None:
                        row["nominee_r"] = candidate["name"]
                    elif candidate["party"] == "G" and row["nominee_green"] is None:
                        row["nominee_green"] = candidate["name"]
                    elif candidate["party"] == "L" and row["nominee_libertarian"] is None:
                        row["nominee_libertarian"] = candidate["name"]
                    elif candidate["name"] not in row["other_general_candidates"]:
                        row["other_general_candidates"].append(candidate["name"])
                continue

            if "primary" not in heading_lower:
                continue

            party = heading_party
            round_name = "runoff" if "runoff" in heading_lower else ("top_two" if "top-two" in heading_lower else "primary")
            status = "runoff" if round_name == "runoff" else "upcoming"
            has_canceled_advanced = bool(CANCELED_ADVANCED_RE.search(heading_section))
            if any("\u2714" in c["raw_text"] for c in candidates) or has_canceled_advanced:
                status = "complete"
            cancellation_reason = _compute_cancellation_reason(heading_section, candidates)

            if not candidates and party in {"D", "R", "NP"} and cancellation_reason:
                if party == "D":
                    row["primary_reason_d"] = cancellation_reason
                elif party == "R":
                    row["primary_reason_r"] = cancellation_reason
                else:
                    row["primary_reason_np"] = cancellation_reason
                continue

            if not candidates:
                continue

            for candidate in candidates:
                if "incumbent" in candidate["raw_text"].lower() and row["incumbent_name"] is None:
                    row["incumbent_name"] = candidate["name"]
                    row["incumbent_party"] = party if party not in {"NP", "OTH"} else candidate["party"]
                if "incumbent" in candidate["raw_text"].lower():
                    saw_incumbent_marker = True

            primary_id = make_primary_id(seat, party, round_name)
            primary_rows.append(
                {
                    "primary_id": primary_id,
                    "seat": seat,
                    "state": state,
                    "district": district_number,
                    "party": party,
                    "round": round_name,
                    "status": status,
                    "cancellation_reason": cancellation_reason,
                    "candidates": [c["name"] for c in candidates],
                    "primary_vote_total": None,
                    "primary_date": election_dates.get("primary_date") or "",
                    "runoff_date": election_dates.get("runoff_date") or "",
                    "primary_vote_share": {},
                    "primary_vote_count": {},
                    "candidate_party_map": {c["name"]: c.get("party") for c in candidates if c.get("name")},
                    "candidate_incumbent_map": {c["name"]: ("incumbent" in (c.get("raw_text") or "").lower()) for c in candidates if c.get("name")},
                    "runoff_candidate_1": candidates[0]["name"] if round_name == "runoff" and len(candidates) > 0 else None,
                    "runoff_candidate_2": candidates[1]["name"] if round_name == "runoff" and len(candidates) > 1 else None,
                    "runoff_id": None,
                    "parent_primary_id": None,
                    "source_file": source_file,
                    "source_url": metadata.get("source_url"),
                    "parser_notes": ["state_rollup_used", "missing_vote_totals"],
                    "source_priority": 1,
                }
            )
            if party == "D":
                row["primary_status_d"] = status
                row["primary_id_d"] = primary_id
                row["primary_reason_d"] = cancellation_reason
            elif party == "R":
                row["primary_status_r"] = status
                row["primary_id_r"] = primary_id
                row["primary_reason_r"] = cancellation_reason
            elif party == "NP":
                row["primary_status_np"] = status
                row["primary_id_np"] = primary_id
                row["primary_reason_np"] = cancellation_reason

        if row["incumbent_name"] is None:
            row["parser_notes"].append(
                "source_missing_incumbent_marker" if (saw_general_heading and not saw_incumbent_marker) else "source_missing_incumbent_field"
            )
        else:
            row["parser_notes"].append("incumbent_from_state_rollup")
        for party_code, field_name, note_name in (
            ("D", "nominee_d", "source_missing_nominee_d"),
            ("R", "nominee_r", "source_missing_nominee_r"),
            ("G", "nominee_green", "source_missing_nominee_green"),
            ("L", "nominee_libertarian", "source_missing_nominee_libertarian"),
        ):
            if row[field_name] is None and (not saw_general_candidates or party_code not in general_parties_present):
                row["parser_notes"].append(note_name)
        if not saw_general_heading:
            row["parser_notes"].append("source_missing_general_election_section")
        elif not saw_general_candidates:
            row["parser_notes"].append("source_missing_general_candidates")
        if not (row.get("primary_date") and row.get("general_date")):
            row["parser_notes"].append("missing_election_dates")
        general_rows.append(row)

    return general_rows, primary_rows
