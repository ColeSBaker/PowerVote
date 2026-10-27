#!/usr/bin/env python3
"""Build a debug view joining canonical U.S. House seats with auxiliary datasets."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SEAT_INDEX_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-seats.json"
BALLOTPEDIA_INPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-ballotpedia.json"
MARKET_INDEX_INPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-market-index.json"
OUTPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-seat-debug-view.json"

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


class HouseSeatDebugViewError(RuntimeError):
    pass


class NormalizedDataset(dict):
    records: dict[str, dict[str, Any]]
    duplicates: list[dict[str, Any]]
    malformed: list[dict[str, Any]]
    missing_seat_id: list[dict[str, Any]]
    unmapped: list[dict[str, Any]]



def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))



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
    stripped = str(value).strip()
    upper = stripped.upper()
    if upper in {"DEM", "REP", "IND", "LIB", "GRE", "DFL", "NPA", "AIP", "OWN"}:
        return upper
    return PARTY_CODE_BY_NAME.get(normalize_person_name(stripped))



def candidate_match_key(candidate: dict[str, Any]) -> tuple[str, str | None]:
    return normalize_person_name(candidate.get("name")), normalize_party_code(candidate.get("partyCode") or candidate.get("party"))



def normalize_ballotpedia_candidate(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, str):
        return {"name": candidate.strip(), "party": None}
    if not isinstance(candidate, dict):
        return {"name": str(candidate).strip(), "party": None}
    return {
        "name": str(candidate.get("name") or "").strip(),
        "party": candidate.get("party") or candidate.get("partyName") or candidate.get("partyCode"),
        "raw": candidate,
    }



def ballotpedia_match_key(candidate: dict[str, Any]) -> tuple[str, str | None]:
    return normalize_person_name(candidate.get("name")), normalize_party_code(candidate.get("party"))



def build_candidate_lookup(candidates: list[dict[str, Any]]) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    lookup: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = candidate_match_key(candidate)
        lookup.setdefault(key, []).append(candidate)
        lookup.setdefault((key[0], None), []).append(candidate)
    return lookup



def find_unmatched_ballotpedia_candidates(
    ballotpedia_candidates: list[dict[str, Any]],
    canonical_candidates: list[dict[str, Any]],
) -> list[str]:
    lookup = build_candidate_lookup(canonical_candidates)
    unmatched: list[str] = []
    for ballotpedia_candidate in ballotpedia_candidates:
        key = ballotpedia_match_key(ballotpedia_candidate)
        options = lookup.get(key) or lookup.get((key[0], None)) or []
        if not options:
            name = ballotpedia_candidate.get("name") or ""
            if name:
                unmatched.append(name)
    return unmatched



def project_record_context(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {"value": record}
    projected = {
        "seatId": record.get("seatId"),
        "stateCode": record.get("stateCode"),
        "districtNumber": record.get("districtNumber"),
        "districtLabel": record.get("districtLabel"),
        "displayName": record.get("displayName"),
    }
    if record.get("source"):
        projected["source"] = record.get("source")
    return projected



def build_ballotpedia_unmapped_record(seat_id: str, record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    election = record.get("election") if isinstance(record.get("election"), dict) else {}
    ballotpedia = election.get("ballotpedia") if isinstance(election.get("ballotpedia"), dict) else {}
    return {
        "seatId": seat_id,
        "stateCode": record.get("stateCode"),
        "stateName": record.get("stateName"),
        "districtNumber": record.get("districtNumber"),
        "districtLabel": record.get("districtLabel"),
        "sourceStateFile": source.get("sourceStateFile") or ballotpedia.get("sourceStateFile"),
        "statePageUrl": source.get("statePageUrl") or ballotpedia.get("statePageUrl"),
        "diagnosticsNote": "canonical seat missing",
        "sourcePayload": clone_json_compatible(record),
    }



def build_kalshi_unmapped_record(seat_id: str, record: dict[str, Any]) -> dict[str, Any]:
    markets = record.get("markets") if isinstance(record.get("markets"), list) else []
    market_tickers = [market.get("ticker") for market in markets if isinstance(market, dict) and market.get("ticker")]
    market_source_files = [market.get("sourceFile") for market in markets if isinstance(market, dict) and market.get("sourceFile")]
    return {
        "seatId": seat_id,
        "stateCode": record.get("stateCode"),
        "districtNumber": record.get("districtNumber"),
        "districtCode": record.get("districtCode"),
        "districtLabel": record.get("districtLabel"),
        "displayName": record.get("displayName"),
        "marketCount": record.get("marketCount"),
        "marketTickers": market_tickers,
        "marketSourceFiles": market_source_files,
        "diagnosticsNote": "canonical seat missing",
        "sourcePayload": clone_json_compatible(record),
    }



def normalize_canonical_seats(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(seat["seatId"]): seat
        for seat in payload.get("seats", [])
        if isinstance(seat, dict) and seat.get("seatId")
    }



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


def normalize_ballotpedia_districts(payload: dict[str, Any]) -> NormalizedDataset:
    normalized: NormalizedDataset = NormalizedDataset(records={}, duplicates=[], malformed=[], missing_seat_id=[], unmapped=[])

    if isinstance(payload.get("districtsBySeatId"), dict):
        iterable = list(payload["districtsBySeatId"].items())
    elif isinstance(payload.get("districts"), list):
        iterable = list(enumerate(payload["districts"]))
    elif isinstance(payload.get("seats"), list):
        iterable = list(enumerate(payload["seats"]))
    else:
        normalized["malformed"] = [{
            "reason": "Ballotpedia payload must provide districtsBySeatId, districts, or seats",
            "record": project_record_context(payload),
        }]
        return normalized

    for key, record in iterable:
        if not isinstance(record, dict):
            normalized["malformed"].append({"reason": "district record is not an object", "key": key, "record": project_record_context(record)})
            continue
        seat_id = derive_seat_id(record) or (str(key) if isinstance(key, str) and key else None)
        if not seat_id:
            normalized["missing_seat_id"].append({"reason": "missing seatId", "key": key, "record": project_record_context(record)})
            continue
        seat_id = str(seat_id)
        if isinstance(payload.get("districtsBySeatId"), dict) and record.get("seatId") and str(record.get("seatId")) != str(key):
            normalized["malformed"].append({
                "reason": "districtsBySeatId key does not match record seatId",
                "key": key,
                "record": project_record_context(record),
            })
        if seat_id in normalized["records"]:
            normalized["duplicates"].append({
                "seatId": seat_id,
                "reason": "duplicate seatId",
                "kept": project_record_context(normalized["records"][seat_id]),
                "discarded": project_record_context(record),
            })
            continue
        normalized["records"][seat_id] = record
    return normalized



def normalize_market_index_districts(payload: dict[str, Any]) -> NormalizedDataset:
    normalized: NormalizedDataset = NormalizedDataset(records={}, duplicates=[], malformed=[], missing_seat_id=[], unmapped=[])
    for index, district in enumerate(payload.get("districts", [])):
        if not isinstance(district, dict):
            normalized["malformed"].append({"reason": "district record is not an object", "index": index, "record": project_record_context(district)})
            continue
        seat_id = district.get("seatId")
        if not seat_id:
            normalized["missing_seat_id"].append({"reason": "missing seatId", "index": index, "record": project_record_context(district)})
            continue
        seat_id = str(seat_id)
        if seat_id in normalized["records"]:
            normalized["duplicates"].append({
                "seatId": seat_id,
                "reason": "duplicate seatId",
                "kept": project_record_context(normalized["records"][seat_id]),
                "discarded": project_record_context(district),
            })
            continue
        normalized["records"][seat_id] = district
    return normalized



def relative_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)



def clone_json_compatible(value: Any) -> Any:
    return json.loads(json.dumps(value))



def candidate_sort_key(candidate: dict[str, Any]) -> tuple[bool, str, str]:
    return (
        (candidate.get("partyCode") or "") not in {"DEM", "REP"},
        candidate.get("partyCode") or "",
        candidate.get("name") or "",
    )



def build_general_debug_candidates(canonical_election: dict[str, Any]) -> list[dict[str, Any]]:
    canonical_candidates = [candidate for candidate in canonical_election.get("candidates") or [] if isinstance(candidate, dict)]
    has_statuses = any(isinstance(candidate.get("currentElectionStatus"), dict) for candidate in canonical_candidates)
    if has_statuses:
        general_candidates = [
            candidate
            for candidate in canonical_candidates
            if ((candidate.get("currentElectionStatus") or {}).get("code") in {"general-nominated", "general-other"})
        ]
    else:
        general_candidates = canonical_candidates
    return sorted((clone_json_compatible(candidate) for candidate in general_candidates), key=candidate_sort_key)



def build_primary_debug_candidates(primary_election: dict[str, Any]) -> list[dict[str, Any]]:
    primary_candidates = [
        clone_json_compatible(candidate)
        for candidate in primary_election.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    nominee_candidate_id = str(primary_election.get("nomineeCandidateId") or "")
    return sorted(
        primary_candidates,
        key=lambda candidate: (
            str(candidate.get("candidateId") or "") != nominee_candidate_id,
            *candidate_sort_key(candidate),
        ),
    )



def build_subelection_layer(canonical_seat: dict[str, Any]) -> list[dict[str, Any]]:
    canonical_election = canonical_seat.get("election") if isinstance(canonical_seat.get("election"), dict) else {}
    if not canonical_election:
        return []

    subelections = [{
        "electionId": canonical_election.get("electionId"),
        "parentElectionId": None,
        "electionKind": canonical_election.get("electionKind") or "general",
        "label": "General",
        "status": canonical_election.get("status") or "active",
        "candidateCount": len(build_general_debug_candidates(canonical_election)),
        "candidates": build_general_debug_candidates(canonical_election),
        "nomineeCandidateId": None,
        "nomineeDisplayName": None,
    }]

    primary_children = [
        child
        for child in canonical_election.get("children") or []
        if isinstance(child, dict) and child.get("electionKind") == "primary"
    ]
    primary_children.sort(key=lambda child: ((child.get("partyCode") or "") not in {"DEM", "REP"}, child.get("partyCode") or "", child.get("label") or ""))
    for child in primary_children:
        ordered_candidates = build_primary_debug_candidates(child)
        subelections.append({
            "electionId": child.get("electionId"),
            "parentElectionId": child.get("parentElectionId"),
            "electionKind": child.get("electionKind"),
            "label": child.get("label") or f"Primary ({child.get('partyCode')})",
            "status": child.get("status") or "active",
            "partyCode": child.get("partyCode"),
            "partyName": child.get("partyName"),
            "candidateCount": len(ordered_candidates),
            "candidates": ordered_candidates,
            "nomineeCandidateId": child.get("nomineeCandidateId"),
            "nomineeDisplayName": child.get("nomineeDisplayName"),
        })
    return subelections



def collect_ballotpedia_candidate_inputs(ballotpedia_record: dict[str, Any] | None) -> dict[str, Any]:
    ballotpedia = ((ballotpedia_record or {}).get("election") or {}).get("ballotpedia") or {}
    if not isinstance(ballotpedia, dict):
        return {
            "generalElectionCandidateLines": [],
            "advancedFromPrimaryLines": [],
            "parsedGeneralElectionCandidates": [],
            "parsedAdvancedFromPrimary": [],
        }
    return {
        "generalElectionCandidateLines": [str(line).strip() for line in ballotpedia.get("generalElectionCandidateLines") or [] if str(line).strip()],
        "advancedFromPrimaryLines": [str(line).strip() for line in ballotpedia.get("advancedFromPrimaryLines") or [] if str(line).strip()],
        "parsedGeneralElectionCandidates": [normalize_ballotpedia_candidate(candidate) for candidate in ballotpedia.get("generalElectionCandidates") or []],
        "parsedAdvancedFromPrimary": [normalize_ballotpedia_candidate(candidate) for candidate in ballotpedia.get("advancedFromPrimary") or []],
    }



def summarize_diagnostics(
    seat_id: str,
    canonical_seat: dict[str, Any],
    ballotpedia_record: dict[str, Any] | None,
    market_index_record: dict[str, Any] | None,
    ballotpedia_normalization: NormalizedDataset,
    market_normalization: NormalizedDataset,
) -> dict[str, Any]:
    canonical_election = canonical_seat.get("election") if isinstance(canonical_seat.get("election"), dict) else {}
    canonical_candidates = [candidate for candidate in canonical_election.get("candidates") or [] if isinstance(candidate, dict)]
    candidate_inputs = collect_ballotpedia_candidate_inputs(ballotpedia_record)

    canonical_candidate_names = [str(candidate.get("name") or "").strip() for candidate in canonical_candidates if str(candidate.get("name") or "").strip()]

    parsed_ballotpedia_candidates = [
        candidate
        for candidate in [*candidate_inputs["parsedGeneralElectionCandidates"], *candidate_inputs["parsedAdvancedFromPrimary"]]
        if candidate.get("name")
    ]
    parsed_ballotpedia_candidate_names = [candidate["name"] for candidate in parsed_ballotpedia_candidates]

    unmatched_ballotpedia_names = find_unmatched_ballotpedia_candidates(parsed_ballotpedia_candidates, canonical_candidates)

    source_presence = {
        "hasCanonicalElectionData": bool(canonical_election),
        "hasBallotpediaData": ballotpedia_record is not None,
        "hasKalshiMarketData": market_index_record is not None,
    }

    mapping_issue_groups = {
        "missingSeatId": [],
        "duplicateSourceRecords": [],
        "malformedSourceRecords": [],
    }

    for source_name, normalization in (("ballotpedia", ballotpedia_normalization), ("marketIndex", market_normalization)):
        mapping_issue_groups["missingSeatId"].extend({"source": source_name, **issue} for issue in normalization["missing_seat_id"])
        mapping_issue_groups["malformedSourceRecords"].extend({"source": source_name, **issue} for issue in normalization["malformed"])
        mapping_issue_groups["duplicateSourceRecords"].extend(
            {"source": source_name, **issue}
            for issue in normalization["duplicates"]
            if issue.get("seatId") == seat_id
        )

    issue_count = len(unmatched_ballotpedia_names)
    issue_count += sum(len(entries) for entries in mapping_issue_groups.values())

    if not source_presence["hasCanonicalElectionData"]:
        issue_count += 1
    if source_presence["hasBallotpediaData"] and not parsed_ballotpedia_candidate_names and (
        candidate_inputs["generalElectionCandidateLines"] or candidate_inputs["advancedFromPrimaryLines"]
    ):
        issue_count += 1

    return {
        "sourcePresence": source_presence,
        "candidateMismatchSummary": {
            "canonicalCandidateNames": canonical_candidate_names,
            "ballotpediaCandidateNames": {
                "generalElectionCandidateLines": candidate_inputs["generalElectionCandidateLines"],
                "advancedFromPrimaryLines": candidate_inputs["advancedFromPrimaryLines"],
                "parsedCandidateNames": parsed_ballotpedia_candidate_names,
            },
            "unmatchedBallotpediaNames": unmatched_ballotpedia_names,
        },
        "mappingIssues": mapping_issue_groups,
        "hasIssues": issue_count > 0,
        "issueCount": issue_count,
    }



def build_source_projection(
    canonical_seat: dict[str, Any],
    ballotpedia_record: dict[str, Any] | None,
    market_index_record: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "congressionalFilings": clone_json_compatible(canonical_seat.get("election")) if canonical_seat.get("election") is not None else None,
        "ballotpedia": clone_json_compatible(ballotpedia_record) if ballotpedia_record is not None else None,
        "kalshi": clone_json_compatible(market_index_record) if market_index_record is not None else None,
    }



def build_us_house_seat_debug_view(
    seat_index_file: Path = SEAT_INDEX_FILE,
    ballotpedia_input_file: Path = BALLOTPEDIA_INPUT_FILE,
    market_index_input_file: Path = MARKET_INDEX_INPUT_FILE,
    output_file: Path = OUTPUT_FILE,
) -> dict[str, Any]:
    canonical_payload = load_json(seat_index_file)
    ballotpedia_payload = load_json(ballotpedia_input_file)
    market_index_payload = load_json(market_index_input_file)

    canonical_seats = normalize_canonical_seats(canonical_payload)
    ballotpedia_normalization = normalize_ballotpedia_districts(ballotpedia_payload)
    market_normalization = normalize_market_index_districts(market_index_payload)

    ballotpedia_by_seat = ballotpedia_normalization["records"]
    market_index_by_seat = market_normalization["records"]

    seats: list[dict[str, Any]] = []
    for seat_id, seat in sorted(canonical_seats.items()):
        seat_record = clone_json_compatible(seat)
        ballotpedia_record = ballotpedia_by_seat.get(seat_id)
        market_index_record = market_index_by_seat.get(seat_id)
        seat_record["debug"] = {
            "subelections": build_subelection_layer(seat),
        }
        seat_record["sources"] = build_source_projection(
            canonical_seat=seat,
            ballotpedia_record=ballotpedia_record,
            market_index_record=market_index_record,
        )
        seat_record["diagnostics"] = summarize_diagnostics(
            seat_id=seat_id,
            canonical_seat=seat,
            ballotpedia_record=ballotpedia_record,
            market_index_record=market_index_record,
            ballotpedia_normalization=ballotpedia_normalization,
            market_normalization=market_normalization,
        )
        seats.append(seat_record)

    mapped_seat_ids = set(canonical_seats)
    ballotpedia_unmapped = [
        build_ballotpedia_unmapped_record(seat_id, record)
        for seat_id, record in sorted(ballotpedia_by_seat.items())
        if seat_id not in mapped_seat_ids
    ]
    kalshi_unmapped = [
        build_kalshi_unmapped_record(seat_id, record)
        for seat_id, record in sorted(market_index_by_seat.items())
        if seat_id not in mapped_seat_ids
    ]

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceFiles": {
            "seatIndex": relative_path(seat_index_file),
            "ballotpedia": relative_path(ballotpedia_input_file),
            "marketIndex": relative_path(market_index_input_file),
            "output": relative_path(output_file),
        },
        "seatCount": len(seats),
        "seats": seats,
        "unmappedRecords": {
            "ballotpedia": ballotpedia_unmapped,
            "kalshi": kalshi_unmapped,
        },
        "normalizationIssues": {
            "ballotpedia": {
                "duplicateSourceRecords": clone_json_compatible(ballotpedia_normalization["duplicates"]),
                "missingSeatId": clone_json_compatible(ballotpedia_normalization["missing_seat_id"]),
                "malformedSourceRecords": clone_json_compatible(ballotpedia_normalization["malformed"]),
            },
            "marketIndex": {
                "duplicateSourceRecords": clone_json_compatible(market_normalization["duplicates"]),
                "missingSeatId": clone_json_compatible(market_normalization["missing_seat_id"]),
                "malformedSourceRecords": clone_json_compatible(market_normalization["malformed"]),
            },
        },
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload



def main() -> None:
    payload = build_us_house_seat_debug_view()
    print(f"Wrote {payload['seatCount']} U.S. House seats to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
