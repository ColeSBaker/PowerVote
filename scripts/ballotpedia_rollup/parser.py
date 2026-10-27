"""End-to-end parser for Ballotpedia House raw HTML pages."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .archetypes import Archetype, detect_archetype
from .config import DEFAULT_FEC_CANDIDATE_SUMMARY_FILE, DEFAULT_PARSE_CACHE_FILE, STATE_PRIMARY_RULES_JSON
from .consolidate import (
    backfill_primary_links,
    consolidate_general_rows,
    consolidate_primary_rows,
    split_and_link_primary_rows,
)
from .extract.district_detail import parse_district_detail_file
from .extract.state_rollup import parse_state_rollup_file
from .extract.national_overview import parse_national_incumbent_tables, parse_national_targeting
from .fec_matching import (
    FecMatcher,
    build_fec_candidate_id_index,
    build_fec_match_audit,
    build_fec_matcher,
    FecCandidate,
    build_fec_unmatched_rows,
    enrich_rows_with_fec_candidate_maps,
    load_fec_rows,
    load_fec_candidates,
    match_candidate,
    seat_from_fec_row,
)
from .kalshi import (
    build_entity_odds_map,
    odds_map_sum_status,
    match_candidate_to_contest_markets,
    build_kalshi_contest_indexes,
    load_kalshi_us_rep_contests,
    normalize_seat_id as normalize_kalshi_seat_id,
    select_contest_for_row,
    summarize_contest,
)
from .kalshi_integrity import annotate_rows_with_kalshi_integrity
from .io import list_input_files
from .meta import extract_meta
from .normalize import clean_name
INCUMBENT_STATUS_VALUES = {
    "running",
    "retiring",
    "seeking_other_office",
    "defeated_primary",
    "defeated_general",
    "vacant_or_unknown",
}
PARSE_CACHE_VERSION = "ballotpedia-rollup-v2"
HISTORICAL_GENERAL_REQUIRED_YEARS = ("2020", "2022", "2024")
HISTORICAL_GENERAL_LOW_TOTAL_THRESHOLD = 10000
HISTORICAL_GENERAL_LOW_TOTAL_ALLOWLIST: set[tuple[str, str]] = set()
HISTORICAL_GENERAL_MISSING_ALLOWLIST: dict[tuple[str, str], str] = {
    ("CO-8", "2020"): "seat_not_contested_in_cycle",
    ("FL-20", "2024"): "source_missing_year_block",
    ("FL-25", "2020"): "source_missing_year_block",
    ("FL-28", "2020"): "source_missing_year_block",
    ("FL-5", "2022"): "source_missing_year_block",
    ("LA-1", "2020"): "source_missing_historical_general_section",
    ("LA-1", "2022"): "source_missing_historical_general_section",
    ("LA-1", "2024"): "source_missing_historical_general_section",
    ("LA-2", "2020"): "source_missing_historical_general_section",
    ("LA-2", "2022"): "source_missing_historical_general_section",
    ("LA-2", "2024"): "source_missing_historical_general_section",
    ("LA-3", "2020"): "source_missing_historical_general_section",
    ("LA-3", "2022"): "source_missing_historical_general_section",
    ("LA-3", "2024"): "source_missing_historical_general_section",
    ("LA-4", "2020"): "source_missing_historical_general_section",
    ("LA-4", "2022"): "source_missing_historical_general_section",
    ("LA-4", "2024"): "source_missing_historical_general_section",
    ("LA-5", "2022"): "source_missing_year_block",
    ("LA-5", "2024"): "source_missing_year_block",
    ("LA-6", "2020"): "source_missing_historical_general_section",
    ("LA-6", "2022"): "source_missing_historical_general_section",
    ("LA-6", "2024"): "source_missing_historical_general_section",
    ("MT-1", "2020"): "seat_not_contested_in_cycle",
    ("MT-2", "2020"): "seat_not_contested_in_cycle",
    ("NC-14", "2020"): "seat_not_contested_in_cycle",
    ("OK-3", "2024"): "source_missing_year_block",
    ("OR-6", "2020"): "seat_not_contested_in_cycle",
    ("TX-37", "2020"): "seat_not_contested_in_cycle",
    ("TX-38", "2020"): "seat_not_contested_in_cycle",
}


@dataclass
class RollupBuildContext:
    general_rows: list[dict]
    primary_rows: list[dict]
    runoff_rows: list[dict]
    archetype_counts: dict[str, int]
    incumbent_departures: list[dict]
    fec_unmatched: list[dict]
    kalshi_join_audit: list[dict]
    ballotpedia_kalshi_unmatched: list[dict]
    historical_vote_total_violations: list[dict]
    primary_kalshi_join_anomalies: list[dict]
    fec_match_audit: list[dict]
    fec_match_metrics: dict[str, dict[str, float | int]]
    parse_profile: dict[str, float] = field(default_factory=dict)


def _normalize_fec_candidate_name(raw: str) -> str:
    text = clean_name(raw)
    if not text:
        return ""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) >= 2:
        return " ".join(parts[1:] + [parts[0]]).title()
    return text.title()


def _normalize_fec_party(raw: str) -> str:
    value = (raw or "").strip().upper()
    if value in {"DEM", "DFL"}:
        return "D"
    if value in {"REP", "R"}:
        return "R"
    if value == "LIB":
        return "L"
    if value in {"GRE", "GRN"}:
        return "G"
    if value in {"IND", "NPA"}:
        return value
    return "OTH"


def _parse_fec_coverage_date(raw: str) -> datetime:
    text = (raw or "").strip()
    if not text:
        return datetime.min
    try:
        return datetime.strptime(text, "%m/%d/%Y")
    except ValueError:
        return datetime.min


def _build_fec_incumbent_index(
    fec_file: Path = DEFAULT_FEC_CANDIDATE_SUMMARY_FILE,
    *,
    fec_rows: list[dict] | None = None,
    office: str = "us_house",
) -> dict[str, dict]:
    by_seat: dict[str, list[dict]] = {}
    source_rows = fec_rows if fec_rows is not None else load_fec_rows(fec_file)
    if not source_rows:
        return {}

    for row in source_rows:
        incumbent_flag = (row.get("Cand_Incumbent_Challenger_Open_Seat") or "").strip().upper()
        if incumbent_flag != "INCUMBENT":
            continue
        seat = seat_from_fec_row(row, office=office)
        if not seat:
            continue
        entry = {
            "name": _normalize_fec_candidate_name(str(row.get("Cand_Name") or "")),
            "party": _normalize_fec_party(str(row.get("Cand_Party_Affiliation") or "")),
            "candidate_id": (row.get("Cand_Id") or "").strip(),
            "coverage_end_date": (row.get("Coverage_End_Date") or "").strip(),
            "_coverage_dt": _parse_fec_coverage_date(str(row.get("Coverage_End_Date") or "")),
        }
        by_seat.setdefault(seat, []).append(entry)

    resolved: dict[str, dict] = {}
    for seat, entries in by_seat.items():
        entries_sorted = sorted(entries, key=lambda item: item["_coverage_dt"], reverse=True)
        chosen = entries_sorted[0]
        conflict_text = ""
        if len(entries_sorted) > 1:
            conflict_text = "multiple_incumbents:" + ";".join(
                f"{item['name']}({item['candidate_id']}|{item['coverage_end_date']})"
                for item in entries_sorted
            )
        resolved[seat] = {
            "fec_incumbent_name": chosen["name"],
            "fec_incumbent_party": chosen["party"],
            "fec_incumbent_conflict": conflict_text,
        }
    return resolved


def _apply_national_incumbent_overlay(row: dict, national_entry: dict | None) -> None:
    if not national_entry:
        return
    if not (row.get("incumbent_name") or "").strip():
        row["incumbent_name"] = national_entry.get("incumbent_name") or ""
        row["incumbent_party"] = national_entry.get("incumbent_party") or ""
        row.setdefault("parser_notes", []).append("incumbent_from_national_backfill")
    row["incumbent_status"] = national_entry.get("incumbent_status") or row.get("incumbent_status") or ""


def _fallback_fec_incumbent_from_name(
    row: dict,
    fec_candidates: list[FecCandidate],
    *,
    matcher: FecMatcher | None = None,
    candidate_by_id: dict[str, FecCandidate] | None = None,
) -> dict[str, str]:
    incumbent_name = str(row.get("incumbent_name") or "").strip()
    if not incumbent_name:
        return {}
    seat = str(row.get("seat") or "").strip()
    party = str(row.get("incumbent_party") or "").strip().upper()
    candidate_id, strategy, _score = match_candidate(
        seat,
        party,
        incumbent_name,
        fec_candidates,
        matcher=matcher,
    )
    if not candidate_id:
        return {}
    if candidate_by_id is None:
        candidate_by_id = build_fec_candidate_id_index(fec_candidates)
    matched = candidate_by_id.get(candidate_id)
    if not matched:
        return {}
    return {
        "fec_incumbent_name": matched.name,
        "fec_incumbent_party": matched.party,
        "fec_incumbent_conflict": f"name_matched_fallback:{strategy}",
    }


def _ensure_incumbent_completeness(row: dict) -> None:
    notes = row.setdefault("parser_notes", [])
    incumbent_name = (row.get("incumbent_name") or "").strip()
    incumbent_party = (row.get("incumbent_party") or "").strip()
    incumbent_status = (row.get("incumbent_status") or "").strip()

    if not incumbent_name:
        row["incumbent_name"] = "Unknown"
        notes.append("incumbent_unknown_fallback")
    if not incumbent_party:
        row["incumbent_party"] = "OTH"
        notes.append("incumbent_party_unknown_fallback")
    if incumbent_status not in INCUMBENT_STATUS_VALUES:
        row["incumbent_status"] = "running" if row["incumbent_name"] != "Unknown" else "vacant_or_unknown"


def _hash_page_html(page_html: str) -> str:
    return hashlib.sha256(page_html.encode("utf-8")).hexdigest()


def _load_parse_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": PARSE_CACHE_VERSION, "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": PARSE_CACHE_VERSION, "entries": {}}
    if payload.get("version") != PARSE_CACHE_VERSION:
        return {"version": PARSE_CACHE_VERSION, "entries": {}}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {"version": PARSE_CACHE_VERSION, "entries": {}}
    return {"version": PARSE_CACHE_VERSION, "entries": entries}


def _save_parse_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _cache_key_for_input_file(input_dir: Path, file_path: Path) -> str:
    try:
        return str(file_path.relative_to(input_dir)).replace("\\", "/")
    except ValueError:
        return file_path.name


def _cache_lookup_entry(
    cache_payload: dict[str, Any] | None,
    *,
    input_dir: Path,
    file_path: Path,
    file_hash: str,
) -> dict[str, Any] | None:
    if cache_payload is None:
        return None
    entries = cache_payload.get("entries") or {}
    cache_key = _cache_key_for_input_file(input_dir, file_path)
    entry = entries.get(cache_key)
    if not isinstance(entry, dict):
        return None
    if str(entry.get("file_hash") or "") != file_hash:
        return None
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None
    return copy.deepcopy(payload)


def _cache_store_entry(
    cache_payload: dict[str, Any] | None,
    *,
    input_dir: Path,
    file_path: Path,
    file_hash: str,
    payload: dict[str, Any],
) -> None:
    if cache_payload is None:
        return
    entries = cache_payload.setdefault("entries", {})
    entries[_cache_key_for_input_file(input_dir, file_path)] = {
        "file_hash": file_hash,
        "payload": copy.deepcopy(payload),
    }


def _cache_payload_for_archetype(
    *,
    archetype: Archetype,
    general_row: dict | None = None,
    primary_rows: list[dict] | None = None,
    state_general_rows: list[dict] | None = None,
    state_primary_rows: list[dict] | None = None,
    national_targeting_by_seat: dict[str, dict[str, bool]] | None = None,
    parsing_plan: dict[str, object] | None = None,
    national_incumbent_by_seat: dict[str, dict] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"archetype": archetype.value}
    if archetype == Archetype.DISTRICT_DETAIL:
        payload["general_row"] = copy.deepcopy(general_row) if general_row else None
        payload["primary_rows"] = copy.deepcopy(primary_rows or [])
    elif archetype == Archetype.STATE_ROLLUP:
        payload["general_rows"] = copy.deepcopy(state_general_rows or [])
        payload["primary_rows"] = copy.deepcopy(state_primary_rows or [])
    elif archetype == Archetype.NATIONAL_OVERVIEW:
        payload["national_targeting_by_seat"] = copy.deepcopy(national_targeting_by_seat or {})
        payload["parsing_plan"] = copy.deepcopy(parsing_plan) if parsing_plan is not None else None
        payload["national_incumbent_by_seat"] = copy.deepcopy(national_incumbent_by_seat or {})
    return payload


def _apply_cached_archetype_payload(
    payload: dict[str, Any],
    *,
    general_rows: list[dict],
    primary_rows: list[dict],
    national_targeting_by_seat: dict[str, dict[str, bool]],
) -> tuple[dict[str, object] | None, dict[str, dict]]:
    archetype_raw = str(payload.get("archetype") or "").strip()
    if not archetype_raw:
        return None, {}
    try:
        archetype = Archetype(archetype_raw)
    except ValueError:
        return None, {}
    parsing_plan: dict[str, object] | None = None
    national_incumbent_by_seat: dict[str, dict] = {}
    if archetype == Archetype.DISTRICT_DETAIL:
        general_row = payload.get("general_row")
        if isinstance(general_row, dict):
            general_rows.append(copy.deepcopy(general_row))
        primary_rows.extend(copy.deepcopy(payload.get("primary_rows") or []))
    elif archetype == Archetype.STATE_ROLLUP:
        general_rows.extend(copy.deepcopy(payload.get("general_rows") or []))
        primary_rows.extend(copy.deepcopy(payload.get("primary_rows") or []))
    elif archetype == Archetype.NATIONAL_OVERVIEW:
        national_targeting_by_seat.clear()
        national_targeting_by_seat.update(copy.deepcopy(payload.get("national_targeting_by_seat") or {}))
        parsing_plan_raw = payload.get("parsing_plan")
        if isinstance(parsing_plan_raw, dict):
            parsing_plan = copy.deepcopy(parsing_plan_raw)
        national_incumbent_by_seat = copy.deepcopy(payload.get("national_incumbent_by_seat") or {})
    return parsing_plan, national_incumbent_by_seat


def parse_national_incumbent_departures(input_dir: Path, *, office: str = "us_house") -> list[dict]:
    for file_path in list_input_files(input_dir):
        page_html = file_path.read_text(encoding="utf-8")
        if detect_archetype(page_html, office=office) != Archetype.NATIONAL_OVERVIEW:
            continue
        metadata = extract_meta(page_html, file_path)
        _by_seat, departures = parse_national_incumbent_tables(
            page_html,
            metadata.get("source_url"),
            office=office,
        )
        return departures
    return []


def parse_ballotpedia_fec_unmatched(
    input_dir: Path,
    *,
    primary_rows: list[dict] | None = None,
    runoff_rows: list[dict] | None = None,
    fec_candidates: list[FecCandidate] | None = None,
    office: str = "us_house",
) -> list[dict]:
    if primary_rows is None or runoff_rows is None:
        _general_rows, parsed_primary_rows, parsed_runoff_rows, _ = parse_all(input_dir, office=office)
        primary_rows = parsed_primary_rows
        runoff_rows = parsed_runoff_rows

    rows = list(primary_rows) + list(runoff_rows)
    has_existing_maps = all(isinstance(row.get("candidate_fec_match_strategy_map"), dict) for row in rows)
    if has_existing_maps:
        unmatched: list[dict] = []
        for row in rows:
            id_map = row.get("candidate_fec_id_map") or {}
            strategy_map = row.get("candidate_fec_match_strategy_map") or {}
            score_map = row.get("candidate_fec_match_score_map") or {}
            party_map = row.get("candidate_party_map") or {}
            for name in row.get("candidates") or []:
                if str(id_map.get(name) or "").strip():
                    continue
                candidate_party = str(party_map.get(name) or row.get("party") or "").strip().upper()
                unmatched.append(
                    {
                        "office": office,
                        "seat": row.get("seat") or "",
                        "party": candidate_party,
                        "ballotpedia_name": name,
                        "reason": str(strategy_map.get(name) or ""),
                        "score": float(score_map.get(name) or 0.0),
                        "primary_id": row.get("primary_id") or "",
                    }
                )
        return build_fec_unmatched_rows(unmatched)

    effective_fec_candidates = fec_candidates if fec_candidates is not None else load_fec_candidates(office=office)
    fec_matcher = build_fec_matcher(effective_fec_candidates)
    unmatched = enrich_rows_with_fec_candidate_maps(
        primary_rows,
        runoff_rows,
        effective_fec_candidates,
        matcher=fec_matcher,
        office=office,
    )
    return build_fec_unmatched_rows(unmatched)


def _build_general_kalshi_payload(contests: list[dict]) -> dict:
    if not contests:
        return {}
    summaries = [summarize_contest(contest) for contest in contests]
    market_tickers = sorted(
        {
            ticker
            for summary in summaries
            for ticker in summary.get("marketTickers") or []
            if ticker
        }
    )
    series_tickers = sorted(
        {
            ticker
            for summary in summaries
            for ticker in summary.get("seriesTickers") or []
            if ticker
        }
    )
    return {
        "contests": summaries,
        "marketTickers": market_tickers,
        "seriesTickers": series_tickers,
        "marketCount": len(market_tickers),
    }


def _general_aggregate_from_contests(general_contests: list[dict]) -> tuple[dict[str, float], float, str]:
    for contest in general_contests:
        aggregate_map = contest.get("general_election_odds_map")
        aggregate_sum = contest.get("general_election_odds_sum")
        aggregate_status = str(contest.get("general_election_odds_sum_status") or "").strip()
        if not isinstance(aggregate_map, dict) or not aggregate_status:
            continue
        normalized_map: dict[str, float] = {}
        for key, value in aggregate_map.items():
            try:
                normalized_map[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        try:
            sum_value = round(float(aggregate_sum), 2)
        except (TypeError, ValueError):
            sum_value = round(sum(normalized_map.values()), 2)
        return normalized_map, sum_value, aggregate_status

    fallback_map = build_entity_odds_map(
        [
            market
            for contest in general_contests
            for market in contest.get("markets") or []
            if isinstance(market, dict)
        ]
    )
    fallback_sum, fallback_status = odds_map_sum_status(fallback_map)
    return fallback_map, fallback_sum, fallback_status


_state_primary_rules_cache: dict | None = None


def load_state_primary_rules() -> dict:
    """Load state-primary-rules.json, cached for the lifetime of the process."""
    global _state_primary_rules_cache
    if _state_primary_rules_cache is None:
        try:
            with open(STATE_PRIMARY_RULES_JSON, encoding="utf-8") as f:
                _state_primary_rules_cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            _state_primary_rules_cache = {}
    return _state_primary_rules_cache


def _attach_kalshi_rollup_metadata(
    general_rows: list[dict],
    primary_rows: list[dict],
    runoff_rows: list[dict],
    *,
    kalshi_indexes: dict[str, Any] | None = None,
    office: str = "us_house",
) -> None:
    if kalshi_indexes is None:
        contests = load_kalshi_us_rep_contests()
        indexes = build_kalshi_contest_indexes(contests)
    else:
        indexes = kalshi_indexes
    indexes.setdefault("by_seat_round_party", {})
    indexes.setdefault("by_seat_round", {})
    indexes.setdefault("normalized_entity_by_ticker", {})
    normalized_entity_by_ticker = indexes.get("normalized_entity_by_ticker") or {}
    state_rules = load_state_primary_rules()

    # Pre-scan: identify which seats have at least one NP primary row.
    # Used below to decide advance-contest join policy per seat.
    seats_with_np_primary: set[str] = {
        str(row.get("seat") or "").strip()
        for row in primary_rows
        if str(row.get("party") or "").strip().upper() in {"", "NP"}
    }
    # Track which seats have already been assigned a non-NP advance-contest row,
    # so we only attach the contest to one row per seat in the no-NP-row case.
    seats_advance_assigned_non_np: set[str] = set()

    for row in primary_rows + runoff_rows:
        seat = str(row.get("seat") or "").strip()
        party = str(row.get("party") or "").strip().upper()
        round_name = "runoff" if str(row.get("round") or "").strip().lower() == "runoff" else "primary"
        contest, strategy = select_contest_for_row(
            indexes,
            seat=seat,
            round_name=round_name,
            party_lane=party,
        )
        # Determine whether the matched contest is a multi-winner advance market
        # (candidate_advance / primary_party_combo).  These have no party lane and
        # are valid matches even without a party-specific key.
        is_advance_contest = str((contest or {}).get("market_role") or "").lower() in {
            "candidate_advance", "primary_party_combo"
        }
        # Advance contests (top-two / top-four) are non-partisan and have no party lane.
        # Attaching the same contest to multiple party-lane rows would duplicate market
        # tickers.  Deduplication policy depends on what Ballotpedia emits for the seat:
        #   • If the seat has an NP row (CA-style): only join to NP rows; skip D/R/OTH.
        #   • If the seat has no NP row (WA-style): allow exactly ONE non-NP row to
        #     receive the contest (first-seen-wins); block the rest.
        if is_advance_contest and party not in {"", "NP"}:
            if seat in seats_with_np_primary:
                # NP row exists for this seat — skip non-NP rows to avoid duplicates.
                contest = None
                strategy = "none"
                is_advance_contest = False
            elif seat in seats_advance_assigned_non_np:
                # No NP row, but another partisan row already claimed the advance contest.
                contest = None
                strategy = "none"
                is_advance_contest = False
            else:
                # No NP row and first partisan row for this seat — assign and record.
                seats_advance_assigned_non_np.add(seat)
        # Primary/runoff rows must use party-consistent contests only,
        # UNLESS the contest is a candidate_advance (top-two/top-four) with no party lane.
        if strategy != "seat_round_party" and not is_advance_contest:
            contest = None
            strategy = "none"
        elif contest is not None and not is_advance_contest:
            contest_party = str(contest.get("party_lane") or "").strip().upper()
            if contest_party and party and contest_party != party:
                contest = None
                strategy = "none"
        summary = summarize_contest(contest)
        row["kalshi_contest"] = summary
        row["kalshi_series_tickers"] = list(summary.get("seriesTickers") or [])
        row["kalshi_market_count"] = int(summary.get("marketCount") or 0)
        row["kalshi_join_strategy"] = strategy
        kalshi_advance_count = int(summary.get("advanceCount") or 1)
        state = seat.split("-")[0].upper() if "-" in seat else seat.upper()
        state_rule = state_rules.get(state, {}).get(office, {})
        baseline_advance_count = int(state_rule.get("advance_count", 1))
        row["advance_count"] = max(baseline_advance_count, kalshi_advance_count)
        row["primary_type"] = str(state_rule.get("type", "partisan_binary"))
        odds_map = build_entity_odds_map((contest or {}).get("markets") or [])
        row["kalshi_primary_odds_map"] = {}
        row["kalshi_runoff_odds_map"] = {}
        if round_name == "runoff":
            row["kalshi_runoff_odds_map"] = odds_map
        else:
            row["kalshi_primary_odds_map"] = odds_map
        odds_sum, sum_status = odds_map_sum_status(odds_map)

        candidates = [str(name).strip() for name in (row.get("candidates") or []) if str(name).strip()]
        for runoff_field in ("runoff_candidate_1", "runoff_candidate_2"):
            name = str(row.get(runoff_field) or "").strip()
            if name and name not in candidates:
                candidates.append(name)

        candidate_market_map: dict[str, list[str]] = {}
        unmatched_rows: list[dict] = []
        for candidate_name in candidates:
            matched_markets, match_strategy, match_score = match_candidate_to_contest_markets(
                contest,
                candidate_name,
                normalized_entity_by_ticker=normalized_entity_by_ticker,
            )
            market_tickers = [str(item.get("marketTicker") or "").strip() for item in matched_markets if str(item.get("marketTicker") or "").strip()]
            if market_tickers:
                candidate_market_map[candidate_name] = sorted(dict.fromkeys(market_tickers))
                continue
            unmatched_rows.append(
                {
                    "seat": seat,
                    "primary_id": row.get("primary_id") or "",
                    "round": round_name,
                    "party": party,
                    "candidate_name": candidate_name,
                    "reason": match_strategy,
                    "score": match_score,
                    "contest_id": summary.get("contestId") or "",
                }
            )

        row["kalshi_candidate_market_map"] = candidate_market_map
        row["kalshi_unmatched_candidates"] = unmatched_rows
        row["kalshi_join_audit"] = {
            "row_type": round_name,
            "seat": seat,
            "id": row.get("primary_id") or "",
            "strategy": strategy,
            "contest_id": summary.get("contestId") or "",
            "party": party,
            "market_count": row["kalshi_market_count"],
            "matched_candidate_count": len(candidate_market_map),
            "unmatched_candidate_count": len(unmatched_rows),
            "odds_map_sum": odds_sum,
            "sum_status": sum_status,
        }

    for row in general_rows:
        seat = str(row.get("seat") or "").strip()
        seat_norm = normalize_kalshi_seat_id(seat)
        general_contests = list(indexes["by_seat_round"].get((seat_norm, "general")) or [])
        primary_d_contest, strategy_d = select_contest_for_row(
            indexes,
            seat=seat,
            round_name="primary",
            party_lane="D",
        )
        primary_r_contest, strategy_r = select_contest_for_row(
            indexes,
            seat=seat,
            round_name="primary",
            party_lane="R",
        )
        row["kalshi_general"] = _build_general_kalshi_payload(general_contests)
        row["kalshi_primary_d"] = summarize_contest(primary_d_contest)
        row["kalshi_primary_r"] = summarize_contest(primary_r_contest)
        general_odds_map, odds_sum, sum_status = _general_aggregate_from_contests(general_contests)
        row["kalshi_general_odds_map"] = general_odds_map
        series_tickers = sorted(
            {
                ticker
                for payload in (row["kalshi_general"], row["kalshi_primary_d"], row["kalshi_primary_r"])
                for ticker in payload.get("seriesTickers") or []
                if ticker
            }
        )
        market_tickers = sorted(
            {
                ticker
                for payload in (row["kalshi_general"], row["kalshi_primary_d"], row["kalshi_primary_r"])
                for ticker in payload.get("marketTickers") or []
                if ticker
            }
        )
        row["kalshi_series_tickers"] = series_tickers
        row["kalshi_market_count"] = len(market_tickers)
        diagnostic = ""
        if not general_contests and (primary_d_contest is not None or primary_r_contest is not None):
            diagnostic = "general_lookup_miss"
        strategy_parts = [
            f"general={len(general_contests)}",
            f"primary_d={strategy_d}",
            f"primary_r={strategy_r}",
        ]
        if diagnostic:
            strategy_parts.append(f"diagnostic={diagnostic}")
        row["kalshi_join_strategy"] = ";".join(strategy_parts)
        row["kalshi_join_audit"] = {
            "row_type": "general",
            "seat": seat,
            "id": "",
            "strategy": row["kalshi_join_strategy"],
            "contest_id": "",
            "party": "",
            "market_count": row["kalshi_market_count"],
            "matched_candidate_count": 0,
            "unmatched_candidate_count": 0,
            "odds_map_sum": odds_sum,
            "sum_status": sum_status,
            "diagnostic": diagnostic,
        }


def _enrich_general_rows_with_fec_candidate_maps(
    general_rows: list[dict],
    fec_candidates: list[FecCandidate],
    *,
    matcher: FecMatcher | None = None,
) -> None:
    effective_matcher = matcher if matcher is not None else build_fec_matcher(fec_candidates)
    for row in general_rows:
        seat = str(row.get("seat") or "").strip()
        if not seat:
            continue
        candidate_party_pairs: list[tuple[str, str]] = []
        nominee_fields = (
            ("nominee_d", "D"),
            ("nominee_r", "R"),
            ("nominee_green", "G"),
            ("nominee_libertarian", "L"),
        )
        for field, party in nominee_fields:
            name = str(row.get(field) or "").strip()
            if name:
                candidate_party_pairs.append((name, party))
        incumbent_name = str(row.get("incumbent_name") or "").strip()
        incumbent_party = str(row.get("incumbent_party") or "").strip().upper() or "OTH"
        if incumbent_name:
            candidate_party_pairs.append((incumbent_name, incumbent_party))
        for name in row.get("other_general_candidates") or []:
            text = str(name or "").strip()
            if text:
                candidate_party_pairs.append((text, "OTH"))

        id_map: dict[str, str] = {}
        strategy_map: dict[str, str] = {}
        score_map: dict[str, float] = {}
        party_map: dict[str, str] = {}
        for name, party in candidate_party_pairs:
            if not name:
                continue
            party_map[name] = party
            fec_id, strategy, score = match_candidate(
                seat,
                party,
                name,
                fec_candidates,
                matcher=effective_matcher,
            )
            if fec_id:
                id_map[name] = fec_id
            strategy_map[name] = strategy
            score_map[name] = score
        row["candidate_fec_id_map"] = id_map
        row["candidate_fec_match_strategy_map"] = strategy_map
        row["candidate_fec_match_score_map"] = score_map
        row["candidate_party_map"] = party_map

def parse_kalshi_rollup_join_audit(input_dir: Path, *, office: str = "us_house") -> list[dict]:
    general_rows, primary_rows, runoff_rows, _ = parse_all(input_dir, office=office)
    return collect_kalshi_rollup_join_audit(general_rows, primary_rows, runoff_rows)


def collect_kalshi_rollup_join_audit(general_rows: list[dict], primary_rows: list[dict], runoff_rows: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for row in general_rows + primary_rows + runoff_rows:
        audit = row.get("kalshi_join_audit")
        if isinstance(audit, dict):
            rows.append(dict(audit))
    return rows


def parse_ballotpedia_kalshi_unmatched_candidates(input_dir: Path, *, office: str = "us_house") -> list[dict]:
    _general_rows, primary_rows, runoff_rows, _ = parse_all(input_dir, office=office)
    return collect_ballotpedia_kalshi_unmatched_candidates(primary_rows, runoff_rows)


def collect_ballotpedia_kalshi_unmatched_candidates(primary_rows: list[dict], runoff_rows: list[dict]) -> list[dict]:
    unmatched: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in primary_rows + runoff_rows:
        for item in row.get("kalshi_unmatched_candidates") or []:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("seat") or ""),
                str(item.get("primary_id") or ""),
                str(item.get("round") or ""),
                str(item.get("candidate_name") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            unmatched.append(dict(item))
    return sorted(unmatched, key=lambda item: (item.get("seat") or "", item.get("primary_id") or "", item.get("candidate_name") or ""))


def collect_primary_kalshi_join_anomalies(primary_rows: list[dict]) -> list[dict]:
    anomalies: list[dict] = []
    ticker_to_rows: dict[str, list[dict]] = defaultdict(list)

    for row in primary_rows:
        primary_id = str(row.get("primary_id") or "").strip()
        seat = str(row.get("seat") or "").strip()
        party = str(row.get("party") or "").strip().upper()
        strategy = str(row.get("kalshi_join_strategy") or "").strip()
        contest = row.get("kalshi_contest") or {}
        contest_id = str(contest.get("contestId") or "").strip()
        contest_party_lane = str(contest.get("partyLane") or "").strip().upper()

        base = {
            "primary_id": primary_id,
            "seat": seat,
            "party": party,
            "kalshi_join_strategy": strategy,
            "contest_id": contest_id,
            "contest_party_lane": contest_party_lane,
        }

        contest_market_role = str(contest.get("marketRole") or "").lower()
        # candidate_advance / primary_party_combo contests intentionally have no party lane;
        # joining via seat_round is correct for these, not an anomaly.
        is_advance = contest_market_role in {"candidate_advance", "primary_party_combo"}
        if strategy == "seat_round" and not is_advance:
            anomalies.append({**base, "issue_type": "seat_round_fallback"})
        if contest_party_lane and party and contest_party_lane != party:
            anomalies.append({**base, "issue_type": "party_lane_mismatch"})

        for ticker in contest.get("marketTickers") or []:
            ticker_text = str(ticker).strip()
            if ticker_text:
                ticker_to_rows[ticker_text].append(base)

    for ticker, rows in ticker_to_rows.items():
        if len(rows) <= 1:
            continue
        row_ids = sorted({str(item.get("primary_id") or "") for item in rows})
        for row in rows:
            anomalies.append(
                {
                    **row,
                    "issue_type": "duplicated_market_ticker",
                    "market_ticker": ticker,
                    "duplicate_primary_ids": "|".join(row_ids),
                }
            )

    return sorted(
        anomalies,
        key=lambda item: (
            str(item.get("issue_type") or ""),
            str(item.get("seat") or ""),
            str(item.get("primary_id") or ""),
            str(item.get("market_ticker") or ""),
        ),
    )


def _compute_ballotpedia_candidate_match_metrics(primary_rows: list[dict], runoff_rows: list[dict]) -> dict[str, float | int]:
    total_candidates = 0
    ambiguous_candidates = 0
    unresolved_candidates = 0
    for row in primary_rows + runoff_rows:
        id_map = row.get("candidate_fec_id_map") or {}
        strategy_map = row.get("candidate_fec_match_strategy_map") or {}
        for name in row.get("candidates") or []:
            total_candidates += 1
            if str(id_map.get(name) or "").strip():
                continue
            strategy = str(strategy_map.get(name) or "")
            if strategy == "ambiguous_fuzzy":
                ambiguous_candidates += 1
                continue
            unresolved_candidates += 1
    denominator = total_candidates - ambiguous_candidates
    unresolved_rate = float(unresolved_candidates / denominator) if denominator else 0.0
    return {
        "declared_total": denominator,
        "declared_matched": denominator - unresolved_candidates,
        "declared_unmatched": unresolved_candidates,
        "declared_unmatched_rate": round(unresolved_rate, 6),
        "ambiguous_unmatched": ambiguous_candidates,
    }


def collect_historical_vote_total_violations(
    general_rows: list[dict],
    *,
    required_years: tuple[str, ...] = HISTORICAL_GENERAL_REQUIRED_YEARS,
    low_total_threshold: int = HISTORICAL_GENERAL_LOW_TOTAL_THRESHOLD,
    low_total_allowlist: set[tuple[str, str]] | None = None,
    missing_total_allowlist: dict[tuple[str, str], str] | None = None,
) -> list[dict]:
    violations: list[dict] = []
    allowlist = low_total_allowlist if low_total_allowlist is not None else HISTORICAL_GENERAL_LOW_TOTAL_ALLOWLIST
    missing_allowlist = (
        missing_total_allowlist
        if missing_total_allowlist is not None
        else HISTORICAL_GENERAL_MISSING_ALLOWLIST
    )
    for row in general_rows:
        seat = str(row.get("seat") or "").strip()
        totals_raw = row.get("historical_general_vote_totals") or {}
        totals: dict[str, int] = {}
        if isinstance(totals_raw, dict):
            for year, value in totals_raw.items():
                try:
                    totals[str(year)] = int(value)
                except (TypeError, ValueError):
                    continue

        for year in required_years:
            value = totals.get(year)
            if value is None:
                if (seat, year) in missing_allowlist:
                    continue
                violations.append(
                    {
                        "type": "missing_historical_general_vote_total",
                        "seat": seat,
                        "year": year,
                        "value": "",
                        "max_other_year": "",
                        "reason": "missing_year_total",
                    }
                )

        for year, value in totals.items():
            if value >= low_total_threshold:
                continue
            if (seat, year) in allowlist:
                continue
            other_values = [other for other_year, other in totals.items() if other_year != year]
            max_other_year = max(other_values) if other_values else ""
            reason = "below_threshold_vs_history" if isinstance(max_other_year, int) and max_other_year > value else "below_threshold"
            violations.append(
                {
                    "type": "low_historical_general_vote_total",
                    "seat": seat,
                    "year": year,
                    "value": value,
                    "max_other_year": max_other_year,
                    "reason": reason,
                }
            )

    return sorted(violations, key=lambda item: (item.get("seat") or "", item.get("year") or "", item.get("type") or ""))


_CONTENTION_INACTIVE = {"none", "canceled", ""}


def _contention_band(active_party_count: int) -> str:
    if active_party_count >= 2:
        return "contested"
    if active_party_count == 1:
        return "uncontested"
    return "no_election"


def _annotate_contention_fields(
    general_rows: list[dict],
    primary_rows: list[dict],
) -> None:
    """Stamp pre-computed contention bands onto each general row.

    general_contention — how many distinct entities are fielding a general-election candidate.
        Entities: D primary lane, R primary lane, NP primary (weighted by candidate count),
        and each independent / third-party candidate in other_general_candidates.
        Bands: "contested" (≥2 entities), "uncontested" (1 entity), "no_election" (none).

    primary_contention — how competitive the primaries are for this district.
        Based on the maximum candidate count across all party primaries for the seat.
        Bands: "contested" (any primary has ≥2 candidates), "uncontested" (all have ≤1),
        "no_election" (no primary rows at all).
    """
    # Build indices: seat → max overall candidates, seat → NP candidate count
    max_candidates_by_seat: dict[str, int] = {}
    np_candidates_by_seat: dict[str, int] = {}
    for prow in primary_rows:
        seat = prow.get("seat") or ""
        party = str(prow.get("party") or "").upper().strip()
        count = len(prow.get("candidates") or [])
        if party in ("NP", "NPA", "NONPARTISAN", "NPP"):
            np_candidates_by_seat[seat] = max(np_candidates_by_seat.get(seat, 0), count)
        if count > max_candidates_by_seat.get(seat, 0):
            max_candidates_by_seat[seat] = count

    for row in general_rows:
        seat = row.get("seat") or ""

        # D and R lanes each count as 1 entity when active (either ran a primary or
        # has a confirmed general-election nominee even without a primary structure).
        has_d = (
            str(row.get("primary_status_d") or "").lower().strip() not in _CONTENTION_INACTIVE
            or bool(row.get("nominee_d"))
        )
        has_r = (
            str(row.get("primary_status_r") or "").lower().strip() not in _CONTENTION_INACTIVE
            or bool(row.get("nominee_r"))
        )
        active = sum([has_d, has_r])

        # NP primary (CA/WA/AK top-two): contribute based on candidate count so that
        # a multi-candidate NP field forces "contested" (capped at 2 to avoid over-counting)
        np_status = str(row.get("primary_status_np") or "").lower().strip()
        if np_status not in _CONTENTION_INACTIVE:
            np_count = np_candidates_by_seat.get(seat, 1)
            active += min(np_count, 2)

        # Each independent / third-party candidate in the general is its own entity
        other = row.get("other_general_candidates") or []
        active += len(other) if isinstance(other, list) else 0

        row["general_contention"] = _contention_band(active)

        # primary_contention: based on max candidate count per seat
        if seat not in max_candidates_by_seat:
            row["primary_contention"] = "no_election"
        elif max_candidates_by_seat[seat] >= 2:
            row["primary_contention"] = "contested"
        else:
            row["primary_contention"] = "uncontested"


def parse_all(
    input_dir: Path,
    *,
    office: str = "us_house",
    fec_candidates: list[FecCandidate] | None = None,
    fec_rows: list[dict] | None = None,
    kalshi_indexes: dict[str, Any] | None = None,
    incremental: bool = False,
    cache_path: Path = DEFAULT_PARSE_CACHE_FILE,
    profile: dict[str, float] | None = None,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    timings = profile if profile is not None else {}

    general_rows: list[dict] = []
    primary_rows: list[dict] = []
    archetype_counts: dict[str, int] = {item.value: 0 for item in Archetype}
    national_targeting_by_seat: dict[str, dict[str, bool]] = {}
    national_incumbent_by_seat: dict[str, dict] = {}
    parsing_plan: dict[str, object] | None = None

    cache_payload: dict[str, Any] | None = _load_parse_cache(cache_path) if incremental else None
    cache_dirty = False

    def _file_matches_office(fp: Path) -> bool:
        stem = fp.stem
        if stem == "National":
            return True
        if office == "state_governor":
            return stem.endswith("-GOV")
        if office == "state_lieutenant_governor":
            return stem.endswith("-LTGOV")
        if office == "state_attorney_general":
            return stem.endswith("-AG")
        return True

    t_parse_start = time.perf_counter()
    for file_path in list_input_files(input_dir):
        if not _file_matches_office(file_path):
            continue
        page_html = file_path.read_text(encoding="utf-8")
        file_hash = _hash_page_html(page_html)
        cached = _cache_lookup_entry(
            cache_payload,
            input_dir=input_dir,
            file_path=file_path,
            file_hash=file_hash,
        )
        if isinstance(cached, dict) and cached.get("archetype"):
            cached_parsing_plan, cached_incumbent_by_seat = _apply_cached_archetype_payload(
                cached,
                general_rows=general_rows,
                primary_rows=primary_rows,
                national_targeting_by_seat=national_targeting_by_seat,
            )
            archetype_value = str(cached.get("archetype") or "")
            archetype_counts[archetype_value] = archetype_counts.get(archetype_value, 0) + 1
            if cached_parsing_plan is not None:
                parsing_plan = cached_parsing_plan
            if cached_incumbent_by_seat:
                national_incumbent_by_seat = cached_incumbent_by_seat
            continue

        archetype = detect_archetype(page_html, office=office)
        archetype_counts[archetype.value] = archetype_counts.get(archetype.value, 0) + 1

        if archetype == Archetype.DISTRICT_DETAIL:
            general_row, primaries = parse_district_detail_file(page_html, file_path.name, office=office)
            if general_row:
                general_rows.append(general_row)
            primary_rows.extend(primaries)
            _cache_store_entry(
                cache_payload,
                input_dir=input_dir,
                file_path=file_path,
                file_hash=file_hash,
                payload=_cache_payload_for_archetype(
                    archetype=archetype,
                    general_row=general_row,
                    primary_rows=primaries,
                ),
            )
            cache_dirty = bool(cache_payload is not None)
        elif archetype == Archetype.STATE_ROLLUP:
            state_general, state_primary = parse_state_rollup_file(page_html, file_path.name, office=office)
            general_rows.extend(state_general)
            primary_rows.extend(state_primary)
            _cache_store_entry(
                cache_payload,
                input_dir=input_dir,
                file_path=file_path,
                file_hash=file_hash,
                payload=_cache_payload_for_archetype(
                    archetype=archetype,
                    state_general_rows=state_general,
                    state_primary_rows=state_primary,
                ),
            )
            cache_dirty = bool(cache_payload is not None)
        elif archetype == Archetype.NATIONAL_OVERVIEW:
            national_targeting_by_seat, parsing_plan = parse_national_targeting(page_html)
            metadata = extract_meta(page_html, file_path)
            national_incumbent_by_seat, _departures = parse_national_incumbent_tables(
                page_html,
                metadata.get("source_url"),
                office=office,
            )
            _cache_store_entry(
                cache_payload,
                input_dir=input_dir,
                file_path=file_path,
                file_hash=file_hash,
                payload=_cache_payload_for_archetype(
                    archetype=archetype,
                    national_targeting_by_seat=national_targeting_by_seat,
                    parsing_plan=parsing_plan,
                    national_incumbent_by_seat=national_incumbent_by_seat,
                ),
            )
            cache_dirty = bool(cache_payload is not None)
        else:
            _cache_store_entry(
                cache_payload,
                input_dir=input_dir,
                file_path=file_path,
                file_hash=file_hash,
                payload=_cache_payload_for_archetype(archetype=archetype),
            )
            cache_dirty = bool(cache_payload is not None)

    if cache_dirty and cache_payload is not None:
        _save_parse_cache(cache_path, cache_payload)
    timings["parse_pages_seconds"] = round(time.perf_counter() - t_parse_start, 4)

    t_consolidate_start = time.perf_counter()
    consolidated_general = consolidate_general_rows(general_rows)
    consolidated_primary = consolidate_primary_rows(primary_rows)
    primary_only_rows, runoff_rows = split_and_link_primary_rows(consolidated_primary)
    backfill_primary_links(consolidated_general, primary_only_rows)
    timings["consolidate_seconds"] = round(time.perf_counter() - t_consolidate_start, 4)

    t_fec_start = time.perf_counter()
    effective_fec_candidates = fec_candidates if fec_candidates is not None else load_fec_candidates(rows=fec_rows, office=office)
    fec_matcher = build_fec_matcher(effective_fec_candidates)
    fec_candidate_by_id = build_fec_candidate_id_index(effective_fec_candidates)
    unmatched_candidates = enrich_rows_with_fec_candidate_maps(
        primary_only_rows,
        runoff_rows,
        effective_fec_candidates,
        matcher=fec_matcher,
        office=office,
    )
    fec_incumbent_by_seat = _build_fec_incumbent_index(fec_rows=fec_rows, office=office)
    _enrich_general_rows_with_fec_candidate_maps(
        consolidated_general,
        effective_fec_candidates,
        matcher=fec_matcher,
    )

    for row in consolidated_general:
        targets = national_targeting_by_seat.get(row["seat"], {})
        row["dccc_target"] = bool(targets.get("dccc_target", False))
        row["nrcc_target"] = bool(targets.get("nrcc_target", False))
        row["dscc_target"] = bool(targets.get("dscc_target", False))
        row["nrsc_target"] = bool(targets.get("nrsc_target", False))
        _apply_national_incumbent_overlay(row, national_incumbent_by_seat.get(row["seat"]))
        fec_entry = fec_incumbent_by_seat.get(row["seat"], {})
        if not fec_entry:
            fec_entry = _fallback_fec_incumbent_from_name(
                row,
                effective_fec_candidates,
                matcher=fec_matcher,
                candidate_by_id=fec_candidate_by_id,
            )
        row["fec_incumbent_name"] = fec_entry.get("fec_incumbent_name", "")
        row["fec_incumbent_party"] = fec_entry.get("fec_incumbent_party", "")
        row["fec_incumbent_conflict"] = fec_entry.get("fec_incumbent_conflict", "")
        _fec_notes_applicable = office in {"us_house", "us_senate", "us_president"}
        if _fec_notes_applicable:
            if not fec_entry:
                row.setdefault("parser_notes", []).append("fec_incumbent_unavailable")
            elif row["fec_incumbent_conflict"]:
                row.setdefault("parser_notes", []).append("fec_incumbent_conflict")
            incumbent_status = str(row.get("incumbent_status") or "").strip().lower()
            if incumbent_status in {"running", "defeated_primary"} and not row["fec_incumbent_name"]:
                row.setdefault("parser_notes", []).append("incumbent_running_without_fec")
            if not row["fec_incumbent_name"] and incumbent_status != "vacant_or_unknown":
                row.setdefault("parser_notes", []).append("incumbent_missing_fec_without_departure_record")
        _ensure_incumbent_completeness(row)
        if parsing_plan is not None:
            row["targeting_parse_plan"] = parsing_plan

    unmatched_lookup = {
        (
            item.get("seat") or "",
            item.get("party") or "",
            item.get("ballotpedia_name") or "",
        )
        for item in unmatched_candidates
    }
    for row in primary_only_rows + runoff_rows:
        for name in row.get("candidates") or []:
            key = (
                row.get("seat") or "",
                str((row.get("candidate_party_map") or {}).get(name) or row.get("party") or "").upper(),
                name,
            )
            if key in unmatched_lookup:
                row.setdefault("parser_notes", []).append("fec_candidate_name_conflict")
                break
    for row in primary_only_rows + runoff_rows:
        targets = national_targeting_by_seat.get(row["seat"], {})
        row["dccc_target"] = bool(targets.get("dccc_target", False))
        row["nrcc_target"] = bool(targets.get("nrcc_target", False))
        row["dscc_target"] = bool(targets.get("dscc_target", False))
        row["nrsc_target"] = bool(targets.get("nrsc_target", False))
    timings["fec_enrich_seconds"] = round(time.perf_counter() - t_fec_start, 4)

    t_kalshi_start = time.perf_counter()
    _attach_kalshi_rollup_metadata(
        consolidated_general,
        primary_only_rows,
        runoff_rows,
        kalshi_indexes=kalshi_indexes,
        office=office,
    )
    timings["kalshi_attach_seconds"] = round(time.perf_counter() - t_kalshi_start, 4)

    t_kalshi_integrity_start = time.perf_counter()
    annotate_rows_with_kalshi_integrity(consolidated_general, primary_only_rows, runoff_rows)
    timings["kalshi_integrity_seconds"] = round(time.perf_counter() - t_kalshi_integrity_start, 4)

    _annotate_contention_fields(consolidated_general, primary_only_rows)

    return consolidated_general, primary_only_rows, runoff_rows, archetype_counts


def build_rollup_context(
    input_dir: Path,
    *,
    office: str = "us_house",
    fec_rows: list[dict] | None = None,
    fec_candidates: list[FecCandidate] | None = None,
    kalshi_indexes: dict[str, Any] | None = None,
    incremental: bool = False,
    cache_path: Path = DEFAULT_PARSE_CACHE_FILE,
    profile: bool = False,
) -> RollupBuildContext:
    parse_profile: dict[str, float] = {}
    effective_fec_rows = fec_rows if fec_rows is not None else load_fec_rows()
    effective_fec_candidates = (
        fec_candidates
        if fec_candidates is not None
        else load_fec_candidates(rows=effective_fec_rows, office=office)
    )

    general_rows, primary_rows, runoff_rows, archetype_counts = parse_all(
        input_dir,
        office=office,
        fec_candidates=effective_fec_candidates,
        fec_rows=effective_fec_rows,
        kalshi_indexes=kalshi_indexes,
        incremental=incremental,
        cache_path=cache_path,
        profile=parse_profile if profile else None,
    )
    incumbent_departures = parse_national_incumbent_departures(input_dir, office=office)
    fec_unmatched = parse_ballotpedia_fec_unmatched(
        input_dir,
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
        fec_candidates=effective_fec_candidates,
        office=office,
    )
    kalshi_join_audit = collect_kalshi_rollup_join_audit(general_rows, primary_rows, runoff_rows)
    ballotpedia_kalshi_unmatched = collect_ballotpedia_kalshi_unmatched_candidates(primary_rows, runoff_rows)
    historical_vote_total_violations = collect_historical_vote_total_violations(general_rows)
    primary_kalshi_join_anomalies = collect_primary_kalshi_join_anomalies(primary_rows)
    fec_match_audit, incumbent_metrics = build_fec_match_audit(
        general_rows,
        primary_rows,
        runoff_rows,
        effective_fec_candidates,
        office=office,
    )
    ballotpedia_metrics = _compute_ballotpedia_candidate_match_metrics(primary_rows, runoff_rows)
    fec_match_metrics = {
        office: {
            **ballotpedia_metrics,
            "incumbent_total": int(incumbent_metrics.get("incumbent_total", 0)),
            "incumbent_matched": int(incumbent_metrics.get("incumbent_matched", 0)),
            "incumbent_unmatched": int(incumbent_metrics.get("incumbent_unmatched", 0)),
            "incumbent_hard_failures": int(incumbent_metrics.get("incumbent_hard_failures", 0)),
        }
    }

    return RollupBuildContext(
        general_rows=general_rows,
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
        archetype_counts=archetype_counts,
        incumbent_departures=incumbent_departures,
        fec_unmatched=fec_unmatched,
        kalshi_join_audit=kalshi_join_audit,
        ballotpedia_kalshi_unmatched=ballotpedia_kalshi_unmatched,
        historical_vote_total_violations=historical_vote_total_violations,
        primary_kalshi_join_anomalies=primary_kalshi_join_anomalies,
        fec_match_audit=fec_match_audit,
        fec_match_metrics=fec_match_metrics,
        parse_profile=parse_profile if profile else {},
    )
