#!/usr/bin/env python3
"""Build a UI-friendly U.S. House election view by combining canonical seats with Ballotpedia district data."""
from __future__ import annotations

import json
import re
import unicodedata
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SEAT_INDEX_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-seats.json"
BALLOTPEDIA_INPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-ballotpedia.json"
OUTPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-election-view.json"
PRIMARY_ROLLUP_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.csv"

PARTY_CODE_BY_NAME = {
    "democratic": "DEM",
    "democratic-farmer-labor": "DFL",
    "republican": "REP",
    "libertarian": "LIB",
    "independent": "IND",
    "independent party": "IND",
    "green": "GRE",
    "american independent": "AIP",
    "no party affiliation": "NPA",
    "no party preference": "NPA",
}


class HouseElectionViewError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_primary_rollup_by_seat(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.exists():
        return {}
    by_seat: dict[str, list[dict[str, str]]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            seat_raw = str(row.get("seat") or "").strip().upper()
            if not seat_raw:
                continue
            match = re.match(r"^([A-Z]{2})-(AL|\d{1,2})$", seat_raw)
            if not match:
                continue
            state_code, district = match.groups()
            seat_id = f"{state_code}-AL" if district == "AL" else f"{state_code}-{int(district):02d}"
            by_seat.setdefault(seat_id, []).append(dict(row))
    return by_seat


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _parse_json_string_map(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    output: dict[str, str] = {}
    for key, value in parsed.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        output[key_text] = str(value).strip()
    return output


def build_primary_election_views_from_rollup(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []
    for row in rows:
        party_code = normalize_party_code(row.get("party")) or "OTH"
        party_name = party_code
        election_id = str(row.get("primary_id") or "").strip() or None
        status = str(row.get("status") or "").strip() or None
        candidate_party_map = _parse_json_string_map(row.get("candidate_party_map"))
        candidate_names = _parse_json_list(row.get("candidates"))
        display_candidates = [
            {
                "name": name,
                "partyCode": normalize_party_code(candidate_party_map.get(name)) or party_code,
            }
            for name in candidate_names
        ]
        views.append({
            "electionId": election_id,
            "parentElectionId": None,
            "electionKind": "primary",
            "status": status,
            "partyCode": party_code,
            "partyName": party_name,
            "label": f"Primary ({party_code})",
            "nomineeCandidateId": None,
            "nomineeDisplayName": None,
            "candidateCount": len(display_candidates),
            "displayCandidates": display_candidates,
            "source": "ballotpedia_primary_rollup",
        })
    return views


def normalize_person_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = normalized.lower()
    normalized = re.sub(r"\(.*?\)", " ", normalized)
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_party_code(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    upper = stripped.upper()
    if upper in {"DEM", "REP", "IND", "LIB", "GRE", "DFL", "NPA", "AIP", "OWN"}:
        return upper
    return PARTY_CODE_BY_NAME.get(normalize_person_name(stripped))


def normalize_ballotpedia_candidate(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, str):
        return {"name": candidate.strip(), "party": None}
    if not isinstance(candidate, dict):
        return {"name": str(candidate).strip(), "party": None}
    return {
        "name": str(candidate.get("name") or "").strip(),
        "party": candidate.get("party") or candidate.get("partyName") or candidate.get("partyCode"),
        "incumbent": bool(candidate.get("incumbent")),
        "raw": candidate,
    }


def candidate_match_key(candidate: dict[str, Any]) -> tuple[str, str | None]:
    return normalize_person_name(candidate.get("name")), normalize_party_code(candidate.get("partyCode") or candidate.get("party"))


def ballotpedia_match_key(candidate: dict[str, Any]) -> tuple[str, str | None]:
    return normalize_person_name(candidate.get("name")), normalize_party_code(candidate.get("party"))


def build_candidate_lookup(candidates: list[dict[str, Any]]) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    lookup: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = candidate_match_key(candidate)
        lookup.setdefault(key, []).append(candidate)
        name_key = (key[0], None)
        lookup.setdefault(name_key, []).append(candidate)
    return lookup


def match_ballotpedia_candidates(
    ballotpedia_candidates: list[dict[str, Any]],
    canonical_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    lookup = build_candidate_lookup(canonical_candidates)
    matched: list[dict[str, Any]] = []
    unmatched: list[str] = []
    seen_ids: set[str] = set()

    for ballotpedia_candidate in ballotpedia_candidates:
        key = ballotpedia_match_key(ballotpedia_candidate)
        options = lookup.get(key) or lookup.get((key[0], None)) or []
        chosen = None
        if len(options) == 1:
            chosen = options[0]
        elif len(options) > 1 and key[1] is not None:
            same_party = [candidate for candidate in options if normalize_party_code(candidate.get("partyCode")) == key[1]]
            if len(same_party) == 1:
                chosen = same_party[0]
        if chosen is None:
            unmatched.append(ballotpedia_candidate.get("name") or "")
            continue
        candidate_id = str(chosen.get("candidateId") or chosen.get("name") or len(matched))
        if candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        matched.append(chosen)

    matched.sort(key=lambda candidate: ((candidate.get("partyCode") or "") not in {"DEM", "REP"}, candidate.get("partyCode") or "", candidate.get("name") or ""))
    return matched, unmatched


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[bool, str, str]:
    return (
        (candidate.get("partyCode") or "") not in {"DEM", "REP"},
        candidate.get("partyCode") or "",
        candidate.get("name") or "",
    )


def extract_canonical_election_context(canonical_election_or_candidates: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(canonical_election_or_candidates, dict):
        candidates = [candidate for candidate in canonical_election_or_candidates.get("candidates") or [] if isinstance(candidate, dict)]
        children = [child for child in canonical_election_or_candidates.get("children") or [] if isinstance(child, dict)]
        return candidates, children
    if isinstance(canonical_election_or_candidates, list):
        return [candidate for candidate in canonical_election_or_candidates if isinstance(candidate, dict)], []
    return [], []


def uses_canonical_election_statuses(canonical_candidates: list[dict[str, Any]], primary_children: list[dict[str, Any]]) -> bool:
    return bool(primary_children) and any(isinstance(candidate.get("currentElectionStatus"), dict) for candidate in canonical_candidates)


def build_general_status_display_candidates(canonical_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    display_candidates = [
        candidate
        for candidate in canonical_candidates
        if ((candidate.get("currentElectionStatus") or {}).get("code") in {"general-nominated", "general-other"})
    ]
    return sorted(display_candidates, key=candidate_sort_key)


def build_primary_election_views(primary_children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    primary_views: list[dict[str, Any]] = []
    for child in primary_children:
        child_candidates = [candidate for candidate in child.get("candidates") or [] if isinstance(candidate, dict)]
        ordered_candidates = sorted(
            child_candidates,
            key=lambda candidate: (
                str(candidate.get("candidateId") or "") != str(child.get("nomineeCandidateId") or ""),
                *candidate_sort_key(candidate),
            ),
        )
        primary_views.append({
            "electionId": child.get("electionId"),
            "parentElectionId": child.get("parentElectionId"),
            "electionKind": child.get("electionKind"),
            "status": child.get("status"),
            "partyCode": child.get("partyCode"),
            "partyName": child.get("partyName"),
            "label": child.get("label"),
            "nomineeCandidateId": child.get("nomineeCandidateId"),
            "nomineeDisplayName": child.get("nomineeDisplayName"),
            "candidateCount": len(ordered_candidates),
            "displayCandidates": ordered_candidates,
        })
    return primary_views


def infer_display_mode(ballotpedia: dict[str, Any], canonical_election_or_candidates: Any) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    canonical_candidates, primary_children = extract_canonical_election_context(canonical_election_or_candidates)
    general_candidates = [normalize_ballotpedia_candidate(candidate) for candidate in ballotpedia.get("generalElectionCandidates") or []]
    advanced_candidates = [normalize_ballotpedia_candidate(candidate) for candidate in ballotpedia.get("advancedFromPrimary") or []]
    notes = [str(note).strip() for note in ballotpedia.get("notes") or [] if str(note).strip()]
    parse_quality = str(ballotpedia.get("parseQuality") or "").strip().lower()
    incomplete_general = any("incomplete pending results from the primary" in note.lower() for note in notes)
    explicitly_incomplete = incomplete_general or any("candidate list in this election may not be complete" in note.lower() for note in notes)

    general_matches, unmatched_general = match_ballotpedia_candidates(general_candidates, canonical_candidates)
    advanced_matches, unmatched_advanced = match_ballotpedia_candidates(advanced_candidates, canonical_candidates)

    diagnostics = {
        "parseQuality": parse_quality or None,
        "notes": notes,
        "generalElectionCandidateCount": len(general_candidates),
        "advancedFromPrimaryCount": len(advanced_candidates),
        "unmatchedGeneralElectionCandidates": unmatched_general,
        "unmatchedAdvancedFromPrimary": unmatched_advanced,
        "matchedGeneralElectionCount": len(general_matches),
        "matchedAdvancedFromPrimaryCount": len(advanced_matches),
        "usedCanonicalElectionStatuses": uses_canonical_election_statuses(canonical_candidates, primary_children),
        "canonicalGeneralCandidateCount": len(build_general_status_display_candidates(canonical_candidates)),
        "canonicalPrimaryElectionCount": len(primary_children),
    }

    if diagnostics["usedCanonicalElectionStatuses"]:
        canonical_general_candidates = build_general_status_display_candidates(canonical_candidates)
        if canonical_general_candidates:
            return "general_election_only", canonical_general_candidates, diagnostics
        if primary_children:
            return "primary_only", [], diagnostics

    if not ballotpedia:
        return "unknown", list(canonical_candidates), diagnostics
    if parse_quality in {"poor", "low", "unusable"}:
        return "all_filed_candidates", list(canonical_candidates), diagnostics

    if explicitly_incomplete and not advanced_candidates:
        return "all_filed_candidates", list(canonical_candidates), diagnostics
    if unmatched_general or unmatched_advanced:
        return "all_filed_candidates", list(canonical_candidates), diagnostics
    if advanced_candidates and advanced_matches:
        mode = "top_two_only" if len(advanced_matches) == 2 else "general_election_only"
        return mode, advanced_matches, diagnostics
    if general_candidates and general_matches and not explicitly_incomplete:
        return "general_election_only", general_matches, diagnostics
    return "all_filed_candidates", list(canonical_candidates), diagnostics


def derive_seat_id(record: dict[str, Any]) -> str | None:
    seat_id = record.get("seatId")
    if seat_id:
        return str(seat_id)
    state_code = record.get("stateCode")
    district_number = record.get("districtNumber")
    if state_code is None or district_number is None:
        return None
    district_number = int(district_number)
    return f"{state_code}-AL" if district_number == 0 else f"{state_code}-{district_number:02d}"


def extract_ballotpedia_election_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    election = record.get("election") if isinstance(record.get("election"), dict) else {}
    ballotpedia = election.get("ballotpedia") if isinstance(election.get("ballotpedia"), dict) else None
    if ballotpedia is None:
        return dict(record)
    merged = dict(ballotpedia)
    for key in ("seatId", "stateCode", "stateName", "districtNumber", "districtLabel", "source"):
        if key in record and key not in merged:
            merged[key] = record[key]
    return merged


def normalize_ballotpedia_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: list[dict[str, Any]] = []
    keyed_records = payload.get("districtsBySeatId")
    if isinstance(keyed_records, dict):
        for key, value in keyed_records.items():
            if not isinstance(value, dict):
                continue
            record = dict(value)
            record.setdefault("seatId", key)
            records.append(record)
    elif isinstance(payload.get("districts"), list):
        records = [district for district in payload["districts"] if isinstance(district, dict)]
    elif isinstance(payload.get("seats"), list):
        records = [seat for seat in payload["seats"] if isinstance(seat, dict)]
    else:
        records = [value for value in payload.values() if isinstance(value, dict)]

    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        seat_id = derive_seat_id(record)
        if not seat_id:
            continue
        normalized[seat_id] = extract_ballotpedia_election_record(record)
    return normalized


def _try_relative(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def build_us_house_election_view(
    seat_index_file: Path = SEAT_INDEX_FILE,
    ballotpedia_input_file: Path = BALLOTPEDIA_INPUT_FILE,
    primary_rollup_file: Path = PRIMARY_ROLLUP_FILE,
    output_file: Path = OUTPUT_FILE,
) -> dict[str, Any]:
    seat_payload = load_json(seat_index_file)
    ballotpedia_payload = load_json(ballotpedia_input_file) if ballotpedia_input_file.exists() else {"districtsBySeatId": {}}
    ballotpedia_by_seat = normalize_ballotpedia_payload(ballotpedia_payload)
    primary_rollup_by_seat = load_primary_rollup_by_seat(primary_rollup_file)

    seats: list[dict[str, Any]] = []
    for seat in seat_payload.get("seats", []):
        seat_copy = json.loads(json.dumps(seat))
        election = seat_copy.setdefault("election", {})
        ballotpedia = dict(ballotpedia_by_seat.get(seat_copy.get("seatId"), {}))
        mode, display_candidates, diagnostics = infer_display_mode(ballotpedia, election)
        election["ballotpedia"] = {
            **ballotpedia,
            "sourceFile": ballotpedia.get("sourceFile") or ((ballotpedia.get("source") or {}).get("sourceStateFile") if isinstance(ballotpedia.get("source"), dict) else None),
            "diagnostics": diagnostics,
        }
        election["displayMode"] = mode
        election["displayCandidates"] = display_candidates
        canonical_primary_elections = build_primary_election_views(
            [child for child in election.get("children") or [] if isinstance(child, dict) and child.get("electionKind") == "primary"]
        )
        election["primaryElections"] = canonical_primary_elections or build_primary_election_views_from_rollup(
            primary_rollup_by_seat.get(str(seat_copy.get("seatId") or ""), [])
        )
        seats.append(seat_copy)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "seatIndexFile": _try_relative(seat_index_file, REPO_ROOT),
        "ballotpediaInputFile": _try_relative(ballotpedia_input_file, REPO_ROOT),
        "primaryRollupFile": _try_relative(primary_rollup_file, REPO_ROOT),
        "seatCount": len(seats),
        "seats": seats,
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = build_us_house_election_view()
    print(f"Wrote {payload['seatCount']} U.S. House election views to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
