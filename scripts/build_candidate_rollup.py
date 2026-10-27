#!/usr/bin/env python3
"""Build candidate-level 2026 U.S. House rollups.

Inputs:
- apps/web/data/us-house-seats.json
- apps/web/data/ballotpedia-primary-election-rollup.csv
- apps/web/data/ballotpedia-runoff-election-rollup.csv
- apps/web/data/ballotpedia-general-election-rollup.csv
- test_data/candidates/candidate_summary_2026.csv

Outputs:
- apps/web/data/candidate-rollup-2026.csv
- apps/web/data/candidate-rollup-2026.json
"""
from __future__ import annotations

import argparse
import csv
import difflib
import html
import importlib.util
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ballotpedia_rollup.kalshi import (
    build_kalshi_contest_indexes,
    load_kalshi_us_rep_contests,
    match_candidate_to_contest_markets,
    normalize_party as normalize_kalshi_party,
    odds_map_sum_status,
    select_contest_for_row,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEATS_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-seats.json"
DEFAULT_PRIMARY_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.csv"
DEFAULT_RUNOFF_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-runoff-election-rollup.csv"
DEFAULT_GENERAL_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-general-election-rollup.csv"
DEFAULT_FINANCE_FILE = REPO_ROOT / "test_data" / "candidates" / "candidate_summary_2026.csv"
DEFAULT_OUT_CSV = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-2026.csv"
DEFAULT_OUT_JSON = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-2026.json"
DEFAULT_SNAPSHOT_DATE_FILE = REPO_ROOT / "apps" / "web" / "data" / "rollup-snapshot-date.txt"
DEFAULT_KALSHI_CONTEST_INDEX = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-rep-contest-index.json"
RECONCILE_BALLOTPEDIA_PATH = REPO_ROOT / "scripts" / "candidates" / "reconcile_ballotpedia_candidates.py"

CANONICAL_STATUSES = {
    "general-nominated": "general (nominated)",
    "general-other": "general (other)",
    "primary-active": "primary",
}

PARTY_NORMALIZATION = {
    "DEM": "DEM",
    "DEMOCRATIC": "DEM",
    "D": "DEM",
    "REP": "REP",
    "REPUBLICAN": "REP",
    "R": "REP",
    "LIB": "LIB",
    "LIBERTARIAN": "LIB",
    "L": "LIB",
    "GRE": "GRE",
    "GREEN": "GRE",
    "G": "GRE",
    "IND": "IND",
    "INDEPENDENT": "IND",
    "NP": "NPA",
    "NPA": "NPA",
    "OWN": "OWN",
}

@dataclass
class MatchResult:
    record: dict[str, Any] | None
    strategy: str
    score: float


@dataclass
class CandidateLinkResult:
    candidate: dict[str, Any]
    strategy: str
    score: float
    suppress: bool = False


_ballotpedia_spec = importlib.util.spec_from_file_location(
    "reconcile_ballotpedia_candidates",
    RECONCILE_BALLOTPEDIA_PATH,
)
assert _ballotpedia_spec and _ballotpedia_spec.loader
_ballotpedia_module = importlib.util.module_from_spec(_ballotpedia_spec)
_ballotpedia_spec.loader.exec_module(_ballotpedia_module)


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = html.unescape(str(value))
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = normalized.lower()
    normalized = re.sub(r"\(.*?\)", " ", normalized)
    normalized = normalized.replace("'", "")
    normalized = re.sub(
        r"\b(dr|mr|mrs|ms|miss|rev|prof|jr|sr|ii|iii|iv|v|incumbent|honorable|[a-z])\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_party(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^A-Za-z]", "", value).upper()
    if not cleaned:
        return None
    return PARTY_NORMALIZATION.get(cleaned, cleaned)


def normalize_seat_id(value: str | None) -> str:
    if not value:
        return ""
    cleaned = str(value).strip().upper()
    match = re.match(r"^([A-Z]{2})-(AL|\d{1,2})$", cleaned)
    if not match:
        return cleaned
    state_code, district = match.groups()
    if district == "AL":
        return f"{state_code}-AL"
    return f"{state_code}-{int(district):02d}"


def parse_percent_map(raw: str | None) -> dict[str, float]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    output: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            output[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return output


def parse_int_map(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    output: dict[str, int] = {}
    for key, value in parsed.items():
        try:
            output[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return output


def parse_string_map(raw: str | None) -> dict[str, str]:
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
        value_text = str(value).strip()
        if key_text and value_text:
            output[key_text] = value_text
    return output


def parse_float_map(raw: str | None) -> dict[str, float]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    output: dict[str, float] = {}
    for key, value in parsed.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        try:
            output[key_text] = float(value)
        except (TypeError, ValueError):
            continue
    return output


def parse_bool_map(raw: str | None) -> dict[str, bool]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    output: dict[str, bool] = {}
    for key, value in parsed.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        if isinstance(value, bool):
            output[key_text] = value
        else:
            value_text = str(value).strip().lower()
            output[key_text] = value_text in {"1", "true", "yes", "y"}
    return output


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_iso_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_snapshot_validation_date(path: Path = DEFAULT_SNAPSHOT_DATE_FILE) -> date:
    if not path.exists():
        raise FileNotFoundError(f"Snapshot date file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    parsed = parse_iso_date(text)
    if parsed is None:
        raise ValueError(f"Invalid snapshot date in {path}: {text!r}")
    return parsed


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        seat = str(row.get("seat") or "").strip()
        if seat:
            row["seat"] = normalize_seat_id(seat)
    return rows


def load_seat_candidates(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    seats = payload.get("seats") or []
    candidates: list[dict[str, Any]] = []
    for seat in seats:
        election = seat.get("election") or {}
        seat_id = seat.get("seatId") or election.get("seatId")
        for candidate in election.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            entry = dict(candidate)
            entry["seatId"] = normalize_seat_id(str(entry.get("seatId") or seat_id or ""))
            entry["nameNorm"] = normalize_name(entry.get("name"))
            entry["partyCodeNorm"] = normalize_party(entry.get("partyCode"))
            candidates.append(entry)
    return candidates


def build_candidate_indexes(candidates: list[dict[str, Any]]) -> dict[str, dict[Any, list[dict[str, Any]]]]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_key: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    by_name_seat: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        candidate_id = str(candidate.get("candidateId") or "").strip()
        if candidate_id:
            by_id[candidate_id].append(candidate)
        seat_id = str(candidate.get("seatId") or "")
        name_norm = str(candidate.get("nameNorm") or "")
        party_norm = candidate.get("partyCodeNorm")
        if seat_id and name_norm:
            by_key[(seat_id, name_norm, party_norm)].append(candidate)
            by_name_seat[(seat_id, name_norm)].append(candidate)
        for alias in candidate.get("aliases") or []:
            alias_norm = normalize_name(str(alias))
            if alias_norm:
                by_key[(seat_id, alias_norm, party_norm)].append(candidate)
                by_name_seat[(seat_id, alias_norm)].append(candidate)
    return {
        "by_id": by_id,
        "by_key": by_key,
        "by_name_seat": by_name_seat,
    }


def match_candidate(
    seat_id: str,
    name: str | None,
    party_code: str | None,
    indexes: dict[str, dict[Any, list[dict[str, Any]]]],
) -> MatchResult:
    name_norm = normalize_name(name)
    party_norm = normalize_party(party_code)
    exact = indexes["by_key"].get((seat_id, name_norm, party_norm), [])
    if len(exact) == 1:
        return MatchResult(exact[0], "seat_name_party_exact", 1.0)
    alias = indexes["by_name_seat"].get((seat_id, name_norm), [])
    if len(alias) == 1:
        return MatchResult(alias[0], "seat_name_alias", 0.92)
    if len(alias) > 1 and party_norm:
        same_party = [c for c in alias if normalize_party(c.get("partyCode")) == party_norm]
        if len(same_party) == 1:
            return MatchResult(same_party[0], "seat_name_party_filtered", 0.9)
    return MatchResult(None, "unmatched", 0.0)


def infer_is_incumbent(candidate: dict[str, Any]) -> bool:
    incumbent_status = str(candidate.get("incumbentStatus") or candidate.get("canonicalIncumbentStatus") or "").strip().lower()
    return incumbent_status == "incumbent"


def infer_status_from_canonical(candidate: dict[str, Any]) -> str:
    status_code = ((candidate.get("currentElectionStatus") or {}).get("code") if isinstance(candidate.get("currentElectionStatus"), dict) else None)
    return CANONICAL_STATUSES.get(str(status_code), "general (other)")


def parse_primary_round_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    by_seat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        parsed = dict(row)
        parsed["party"] = normalize_party(row.get("party"))
        parsed["primary_vote_share_map"] = parse_percent_map(row.get("primary_vote_share"))
        parsed["primary_vote_count_map"] = parse_int_map(row.get("primary_vote_count"))
        parsed["candidate_party_map"] = parse_string_map(row.get("candidate_party_map"))
        parsed["candidate_incumbent_map"] = parse_bool_map(row.get("candidate_incumbent_map"))
        parsed["seat"] = normalize_seat_id(row.get("seat"))
        parsed["primary_date"] = parse_date(row.get("primary_date") or row.get("election_date") or row.get("date"))
        parsed["runoff_date"] = parse_date(row.get("runoff_date"))
        parsed["general_date"] = parse_date(row.get("general_date"))
        by_seat[parsed["seat"]].append(parsed)
    return by_seat


def _kalshi_party_from_candidate_party(party: str | None) -> str | None:
    normalized = normalize_party(party)
    if normalized == "DEM":
        return "D"
    if normalized == "REP":
        return "R"
    return normalize_kalshi_party(party)


def _dedupe_kalshi_market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("marketTicker") or "").strip()
        if not ticker:
            continue
        existing = by_ticker.get(ticker)
        if existing is None:
            by_ticker[ticker] = dict(row)
            continue
        existing_odds = parse_number(existing.get("oddsPercent")) or 0.0
        contender_odds = parse_number(row.get("oddsPercent")) or 0.0
        if contender_odds > existing_odds:
            by_ticker[ticker] = dict(row)
    return sorted(
        by_ticker.values(),
        key=lambda item: (
            (item.get("status") or "").lower() != "active",
            -(parse_number(item.get("oddsPercent")) or 0.0),
            item.get("marketTicker") or "",
        ),
    )


def _best_odds(rows: list[dict[str, Any]]) -> float | None:
    values = [parse_number(item.get("oddsPercent")) for item in rows]
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return max(filtered)


def _candidate_names_for_kalshi_matching(row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    append_unique(names, row.get("BallotpediaName"))
    for value in row.get("FilingName") or []:
        append_unique(names, value)
    for value in row.get("KalshiName") or []:
        append_unique(names, value)
    for value in row.get("aliases") or []:
        append_unique(names, value)
    return names


def _match_candidate_to_contest_with_aliases(
    contest: dict[str, Any] | None,
    candidate_names: list[str],
) -> tuple[list[dict[str, Any]], str, float]:
    best_rows: list[dict[str, Any]] = []
    best_strategy = "no_candidate_name"
    best_score = 0.0
    for candidate_name in candidate_names:
        rows, strategy, score = match_candidate_to_contest_markets(contest, candidate_name)
        if rows and score >= best_score:
            best_rows = rows
            best_strategy = strategy
            best_score = score
    return best_rows, best_strategy, best_score


def enrich_rows_with_kalshi_markets(records: list[dict[str, Any]], contests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexes = build_kalshi_contest_indexes(contests)
    for row in records:
        seat = normalize_seat_id(row.get("2026 Seat"))
        lane = _kalshi_party_from_candidate_party(row.get("Party"))
        candidate_names = _candidate_names_for_kalshi_matching(row)

        primary_contest = None
        primary_select_strategy = "none"
        if (row.get("Primary ID") or "").strip():
            primary_contest, primary_select_strategy = select_contest_for_row(
                indexes,
                seat=seat,
                round_name="primary",
                party_lane=lane,
            )
        primary_markets, primary_match_strategy, primary_match_score = _match_candidate_to_contest_with_aliases(primary_contest, candidate_names)
        primary_markets = _dedupe_kalshi_market_rows(primary_markets)

        runoff_contest = None
        runoff_select_strategy = "none"
        if (row.get("RunoffID") or "").strip() or str(row.get("Status") or "").strip().lower() == "runoff":
            runoff_contest, runoff_select_strategy = select_contest_for_row(
                indexes,
                seat=seat,
                round_name="runoff",
                party_lane=lane,
            )
        runoff_markets, runoff_match_strategy, runoff_match_score = _match_candidate_to_contest_with_aliases(runoff_contest, candidate_names)
        runoff_markets = _dedupe_kalshi_market_rows(runoff_markets)

        general_markets: list[dict[str, Any]] = []
        general_strategy = "none"
        general_score = 0.0
        general_contests = list(indexes["by_seat_round"].get((seat, "general")) or [])
        for contest in general_contests:
            market_role = str(contest.get("market_role") or "").strip().lower()
            if market_role != "candidate_winner":
                continue
            matched_rows, match_strategy, match_score = _match_candidate_to_contest_with_aliases(contest, candidate_names)
            if matched_rows:
                general_markets.extend(matched_rows)
                general_strategy = match_strategy
                general_score = max(general_score, match_score)
        general_markets = _dedupe_kalshi_market_rows(general_markets)
        if not general_markets:
            general_strategy = "no_candidate_market"

        combined_markets = _dedupe_kalshi_market_rows(primary_markets + runoff_markets + general_markets)
        row["KalshiPrimaryMarkets"] = primary_markets
        row["KalshiRunoffMarkets"] = runoff_markets
        row["KalshiGeneralMarkets"] = general_markets
        row["KalshiMarkets"] = combined_markets
        row["KalshiSeries"] = sorted(
            {
                str(market.get("seriesTicker") or "").strip()
                for market in combined_markets
                if str(market.get("seriesTicker") or "").strip()
            }
        )
        row["KalshiBestPrimaryOdds"] = _best_odds(primary_markets)
        row["KalshiBestRunoffOdds"] = _best_odds(runoff_markets)
        row["KalshiBestGeneralOdds"] = _best_odds(general_markets)
        row["KalshiLinkStrategy"] = (
            f"primary:{primary_select_strategy}/{primary_match_strategy};"
            f"runoff:{runoff_select_strategy}/{runoff_match_strategy};"
            f"general:{general_strategy}"
        )
        row["KalshiLinkScore"] = max(primary_match_score, runoff_match_score, general_score)

    return records


def _parse_candidates_json(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    output: list[str] = []
    for item in parsed:
        text = str(item).strip()
        if text:
            output.append(text)
    return output


def _collect_ballotpedia_candidates_by_seat_party(
    primary_rows: list[dict[str, str]],
    runoff_rows: list[dict[str, str]],
    general_rows: list[dict[str, str]],
) -> dict[tuple[str, str], set[str]]:
    by_seat_party: dict[tuple[str, str], set[str]] = defaultdict(set)

    def add(seat_id: str, party_code: str | None, candidate_name: str | None) -> None:
        seat_norm = normalize_seat_id(seat_id)
        party_norm = normalize_party(party_code)
        name_text = str(candidate_name or "").strip()
        if not seat_norm or not party_norm or not name_text:
            return
        by_seat_party[(seat_norm, party_norm)].add(name_text)

    for row in primary_rows:
        seat = row.get("seat")
        party = row.get("party")
        for name in parse_int_map(row.get("primary_vote_count")).keys():
            add(seat, party, name)
        for name in _parse_candidates_json(row.get("candidates")):
            add(seat, party, name)
        add(seat, party, row.get("runoff_candidate_1"))
        add(seat, party, row.get("runoff_candidate_2"))

    for row in runoff_rows:
        seat = row.get("seat")
        party = row.get("party")
        for name in parse_int_map(row.get("primary_vote_count")).keys():
            add(seat, party, name)
        for name in _parse_candidates_json(row.get("candidates")):
            add(seat, party, name)
        add(seat, party, row.get("runoff_candidate_1"))
        add(seat, party, row.get("runoff_candidate_2"))

    general_party_fields = (
        ("DEM", "nominee_d"),
        ("REP", "nominee_r"),
        ("GRE", "nominee_green"),
        ("LIB", "nominee_libertarian"),
    )
    for row in general_rows:
        seat = row.get("seat")
        for party_code, field in general_party_fields:
            add(seat, party_code, row.get(field))

    return by_seat_party


def augment_candidates_with_ballotpedia_sources(
    candidates: list[dict[str, Any]],
    primary_rows: list[dict[str, str]],
    runoff_rows: list[dict[str, str]],
    general_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    # Build the row universe strictly from Ballotpedia election candidate entries.
    # Canonical candidates are used only for enrichment/matching.
    anchored_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    def upsert_ballotpedia_name(
        seat_id: str | None,
        party_code: str | None,
        raw_name: str | None,
        source_round: str,
        source_candidate_party: str | None = None,
        source_candidate_incumbent: bool | None = None,
    ) -> None:
        seat_norm = normalize_seat_id(seat_id)
        party_norm = normalize_party(party_code)
        name_text = str(raw_name or "").strip()
        if not seat_norm or not party_norm or not name_text:
            return
        name_norm = normalize_name(name_text)
        if not name_norm:
            return
        key = (seat_norm, party_norm, name_norm)
        existing = anchored_by_key.get(key)
        if existing is None:
            existing = {
                "seatId": seat_norm,
                "partyCode": party_norm,
                "name": name_text,
                "ballotpediaName": name_text,
                "aliases": [],
                "candidateId": None,
                "nameNorm": name_norm,
                "matchedCanonicalName": None,
                "matchedKalshiName": None,
                "filingNameMatches": [],
                "kalshiNameMatches": [],
                "reconcileIdentityStrategy": "ballotpedia_source",
                "reconcileIdentityScore": 1.0,
                "sourceRounds": [],
                "ballotpediaPartyCode": None,
                "ballotpediaIncumbent": False,
            }
            anchored_by_key[key] = existing

        append_unique(existing["aliases"], name_text)
        append_unique(existing["sourceRounds"], source_round)
        party_from_source = normalize_party(source_candidate_party)
        if party_from_source:
            existing["ballotpediaPartyCode"] = party_from_source
        if source_candidate_incumbent is True:
            existing["ballotpediaIncumbent"] = True
        # Use shortest non-empty variant as the stable display label.
        current_display = str(existing.get("ballotpediaName") or "").strip()
        if current_display and len(name_text) < len(current_display):
            existing["ballotpediaName"] = name_text
            existing["name"] = name_text

    for row in primary_rows:
        seat = row.get("seat")
        party = row.get("party")
        lane_party = normalize_party(party) or "OWN"
        row_party_map = parse_string_map(row.get("candidate_party_map"))
        row_incumbent_map = parse_bool_map(row.get("candidate_incumbent_map"))
        for name in parse_int_map(row.get("primary_vote_count")).keys():
            upsert_ballotpedia_name(
                seat,
                party,
                name,
                "primary",
                source_candidate_party=row_party_map.get(name) if lane_party in {"NPA", "OWN"} else None,
                source_candidate_incumbent=row_incumbent_map.get(name),
            )
        for name in _parse_candidates_json(row.get("candidates")):
            upsert_ballotpedia_name(
                seat,
                party,
                name,
                "primary",
                source_candidate_party=row_party_map.get(name) if lane_party in {"NPA", "OWN"} else None,
                source_candidate_incumbent=row_incumbent_map.get(name),
            )
        upsert_ballotpedia_name(
            seat,
            party,
            row.get("runoff_candidate_1"),
            "primary",
            source_candidate_party=row_party_map.get(str(row.get("runoff_candidate_1") or "").strip()) if lane_party in {"NPA", "OWN"} else None,
            source_candidate_incumbent=row_incumbent_map.get(str(row.get("runoff_candidate_1") or "").strip()),
        )
        upsert_ballotpedia_name(
            seat,
            party,
            row.get("runoff_candidate_2"),
            "primary",
            source_candidate_party=row_party_map.get(str(row.get("runoff_candidate_2") or "").strip()) if lane_party in {"NPA", "OWN"} else None,
            source_candidate_incumbent=row_incumbent_map.get(str(row.get("runoff_candidate_2") or "").strip()),
        )

    for row in runoff_rows:
        seat = row.get("seat")
        party = row.get("party")
        lane_party = normalize_party(party) or "OWN"
        row_party_map = parse_string_map(row.get("candidate_party_map"))
        row_incumbent_map = parse_bool_map(row.get("candidate_incumbent_map"))
        for name in parse_int_map(row.get("primary_vote_count")).keys():
            upsert_ballotpedia_name(
                seat,
                party,
                name,
                "runoff",
                source_candidate_party=row_party_map.get(name) if lane_party in {"NPA", "OWN"} else None,
                source_candidate_incumbent=row_incumbent_map.get(name),
            )
        for name in _parse_candidates_json(row.get("candidates")):
            upsert_ballotpedia_name(
                seat,
                party,
                name,
                "runoff",
                source_candidate_party=row_party_map.get(name) if lane_party in {"NPA", "OWN"} else None,
                source_candidate_incumbent=row_incumbent_map.get(name),
            )
        upsert_ballotpedia_name(
            seat,
            party,
            row.get("runoff_candidate_1"),
            "runoff",
            source_candidate_party=row_party_map.get(str(row.get("runoff_candidate_1") or "").strip()) if lane_party in {"NPA", "OWN"} else None,
            source_candidate_incumbent=row_incumbent_map.get(str(row.get("runoff_candidate_1") or "").strip()),
        )
        upsert_ballotpedia_name(
            seat,
            party,
            row.get("runoff_candidate_2"),
            "runoff",
            source_candidate_party=row_party_map.get(str(row.get("runoff_candidate_2") or "").strip()) if lane_party in {"NPA", "OWN"} else None,
            source_candidate_incumbent=row_incumbent_map.get(str(row.get("runoff_candidate_2") or "").strip()),
        )

    for row in general_rows:
        seat = row.get("seat")
        incumbent_name = str(row.get("incumbent_name") or "").strip()
        for party_code, field in (("DEM", "nominee_d"), ("REP", "nominee_r"), ("GRE", "nominee_green"), ("LIB", "nominee_libertarian")):
            nominee_name = str(row.get(field) or "").strip()
            upsert_ballotpedia_name(
                seat,
                party_code,
                nominee_name,
                "general",
                source_candidate_party=party_code,
                source_candidate_incumbent=bool(incumbent_name and normalize_name(incumbent_name) == normalize_name(nominee_name)),
            )

    canonical_by_seat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        seat_norm = normalize_seat_id(candidate.get("seatId"))
        if not seat_norm:
            continue
        canonical_by_seat[seat_norm].append(candidate)

    score_by_confidence = {"high": 0.98, "medium": 0.9, "low": 0.75}
    anchored = list(anchored_by_key.values())
    for candidate in anchored:
        seat_id = normalize_seat_id(candidate.get("seatId"))
        source_name = str(candidate.get("ballotpediaName") or "").strip()
        if not seat_id or not source_name:
            continue
        canonical_pool = canonical_by_seat.get(seat_id, [])
        reconciled = _ballotpedia_module.reconcile_ballotpedia_candidate(source_name, canonical_pool, seat_id)
        matched_candidate = reconciled.get("matchedCandidate")
        match_strategy = str(reconciled.get("matchStrategy") or "unmatched")
        confidence = str(reconciled.get("confidence") or "").strip().lower()
        candidate["reconcileIdentityStrategy"] = f"ballotpedia_{match_strategy}"
        candidate["reconcileIdentityScore"] = score_by_confidence.get(confidence, 0.0 if match_strategy == "unmatched" else 0.8)

        if not isinstance(matched_candidate, dict):
            continue

        matched_party = normalize_party(matched_candidate.get("partyCode"))
        candidate_party = normalize_party(candidate.get("partyCode")) or "OWN"
        if candidate_party not in {"NPA", "OWN"} and matched_party and matched_party != candidate_party:
            continue

        candidate_id = str(matched_candidate.get("candidateId") or "").strip()
        if candidate_id:
            candidate["candidateId"] = candidate_id

        canonical_name = str(matched_candidate.get("name") or "").strip()
        if canonical_name:
            candidate["matchedCanonicalName"] = canonical_name
            append_unique(candidate["filingNameMatches"], canonical_name)
            append_unique(candidate["aliases"], canonical_name)
        candidate["canonicalIncumbentStatus"] = matched_candidate.get("incumbentStatus")

        kalshi_name = str(matched_candidate.get("kalshiName") or "").strip()
        if kalshi_name:
            candidate["matchedKalshiName"] = kalshi_name
            append_unique(candidate["kalshiNameMatches"], kalshi_name)
            append_unique(candidate["aliases"], kalshi_name)

        for alias in matched_candidate.get("aliases") or []:
            append_unique(candidate["aliases"], alias)

    return anchored


def normalized_candidate_variants(candidate: dict[str, Any]) -> set[str]:
    variants: set[str] = set()
    for value in (
        candidate.get("ballotpediaName"),
        candidate.get("name"),
        candidate.get("kalshiName"),
        *(candidate.get("kalshiNameMatches") or []),
        *(candidate.get("filingNameMatches") or []),
        *(candidate.get("aliases") or []),
    ):
        normalized = normalize_name(str(value)) if value is not None else ""
        if normalized:
            variants.add(normalized)
    return variants


def find_matching_round_row(candidate: dict[str, Any], round_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidate_name_variants = normalized_candidate_variants(candidate)
    if not candidate_name_variants:
        return None
    for row in round_rows:
        votes = row.get("primary_vote_count_map") or {}
        shares = row.get("primary_vote_share_map") or {}
        vote_name_keys = {normalize_name(key) for key in votes.keys()}
        share_name_keys = {normalize_name(key) for key in shares.keys()}

        if candidate_name_variants & vote_name_keys or candidate_name_variants & share_name_keys:
            return row

        row_candidate_names = set()
        candidates_field = row.get("candidates")
        if isinstance(candidates_field, str) and candidates_field.strip():
            try:
                parsed_candidates = json.loads(candidates_field)
                if isinstance(parsed_candidates, list):
                    for c in parsed_candidates:
                        row_candidate_names.add(normalize_name(str(c)))
            except json.JSONDecodeError:
                pass

        for run_field in ("runoff_candidate_1", "runoff_candidate_2"):
            candidate_name = row.get(run_field)
            if candidate_name:
                row_candidate_names.add(normalize_name(candidate_name))

        if candidate_name_variants & row_candidate_names:
            return row

    return None


def first_matching_round_value(round_map: dict[str, Any], candidate_name_variants: set[str]) -> Any:
    for candidate_name, value in round_map.items():
        if normalize_name(candidate_name) in candidate_name_variants:
            return value
    return None


def first_matching_round_party(round_map: dict[str, Any], candidate_name_variants: set[str]) -> str | None:
    for candidate_name, value in (round_map or {}).items():
        if normalize_name(candidate_name) in candidate_name_variants:
            return normalize_party(value)
    return None


def first_matching_round_bool(round_map: dict[str, Any], candidate_name_variants: set[str]) -> bool:
    for candidate_name, value in (round_map or {}).items():
        if normalize_name(candidate_name) in candidate_name_variants:
            return bool(value)
    return False


def _primary_round_concluded(
    primary_row: dict[str, Any] | None,
    runoff_row: dict[str, Any] | None,
    snapshot_date: date,
) -> bool:
    if not primary_row:
        return False
    primary_status = str(primary_row.get("status") or "").strip().lower()
    primary_round = str(primary_row.get("round") or "").strip().lower()
    primary_date = parse_iso_date(primary_row.get("primary_date"))
    primary_date_passed = bool(primary_date and primary_date <= snapshot_date)
    primary_vote_total = parse_number(primary_row.get("primary_vote_total")) or 0.0

    if primary_status == "runoff" and primary_date_passed:
        return True
    if primary_status == "complete" and primary_round in {"primary", "top_two"} and primary_date_passed:
        return True
    if primary_vote_total > 0 and primary_date_passed:
        return True

    if runoff_row:
        runoff_status = str(runoff_row.get("status") or "").strip().lower()
        runoff_date = parse_iso_date(runoff_row.get("runoff_date"))
        if runoff_status == "complete" and runoff_date and runoff_date <= snapshot_date:
            return True
    return False


def _null_out_future_votes(record: dict[str, Any], snapshot_date: date) -> None:
    primary_date = parse_iso_date(record.get("primaryDate"))
    if record.get("Votes in Primary") is not None and (primary_date is None or primary_date > snapshot_date):
        record["Votes in Primary"] = None
        record["Share of Primary"] = None

    runoff_date = parse_iso_date(record.get("runoffDate"))
    if record.get("Votes in Runoff") is not None and (runoff_date is None or runoff_date > snapshot_date):
        record["Votes in Runoff"] = None
        record["Share of Runoff"] = None


def _best_index_for_target_name(
    target_name_norm: str,
    candidate_rows: list[dict[str, Any]],
    already_selected: set[int],
) -> int | None:
    best_index = None
    best_score = 0.0
    for index, row in enumerate(candidate_rows):
        if index in already_selected:
            continue
        candidate_name_norm = normalize_name(row.get("BallotpediaName"))
        if not candidate_name_norm:
            continue
        score = difflib.SequenceMatcher(a=target_name_norm, b=candidate_name_norm).ratio()
        if candidate_name_norm == target_name_norm:
            score += 1.0
        if score > best_score:
            best_score = score
            best_index = index
    if best_index is None or best_score < 0.75:
        return None
    return best_index


def enforce_primary_outcome_constraints(
    records: list[dict[str, Any]],
    primary_rows: list[dict[str, Any]],
    runoff_rows: list[dict[str, Any]],
    snapshot_date: date,
) -> None:
    records_by_primary: dict[str, list[dict[str, Any]]] = defaultdict(list)
    primary_by_id: dict[str, dict[str, Any]] = {}
    runoff_by_id: dict[str, dict[str, Any]] = {}
    for row in primary_rows:
        primary_id = str(row.get("primary_id") or "").strip()
        if primary_id:
            primary_by_id[primary_id] = row
    for row in runoff_rows:
        runoff_id = str(row.get("primary_id") or "").strip()
        if runoff_id:
            runoff_by_id[runoff_id] = row
    for record in records:
        primary_id = str(record.get("Primary ID") or "").strip()
        if primary_id:
            records_by_primary[primary_id].append(record)

    for primary_id, primary_candidates in records_by_primary.items():
        primary_row = primary_by_id.get(primary_id, {})
        runoff_id = str(primary_row.get("runoff_id") or "").strip()
        linked_runoff_row = runoff_by_id.get(runoff_id) if runoff_id else None
        primary_concluded = _primary_round_concluded(primary_row, linked_runoff_row, snapshot_date)

        if runoff_id and primary_concluded:
            target_names = [
                normalize_name(primary_row.get("runoff_candidate_1")),
                normalize_name(primary_row.get("runoff_candidate_2")),
            ]
            target_names = [name for name in target_names if name]
            selected: set[int] = set()
            for target_name in target_names[:2]:
                chosen = _best_index_for_target_name(target_name, primary_candidates, selected)
                if chosen is not None:
                    selected.add(chosen)
            for index, candidate in enumerate(primary_candidates):
                if index in selected:
                    candidate["Status"] = "runoff"
                    candidate["RunoffID"] = runoff_id
                    candidate["ballotAccessStatus"] = "qualified"
                    candidate["statusReason"] = "appears_in_runoff_candidate_list"
                else:
                    candidate["RunoffID"] = None
                    if candidate.get("Status") != "did not make ballot":
                        candidate["Status"] = "eliminated"
                        candidate["ballotAccessStatus"] = "qualified"
                        candidate["statusReason"] = "in_completed_primary_not_in_runoff_or_general"
            continue

        if not primary_concluded:
            continue

        nominees = [
            candidate for candidate in primary_candidates
            if str(candidate.get("Status") or "").strip() == "general (nominated)"
        ]
        if len(nominees) == 1:
            continue

        winner = None
        winner_votes = -1.0
        for candidate in primary_candidates:
            votes = parse_number(candidate.get("Votes in Primary"))
            if votes is None:
                continue
            if votes > winner_votes:
                winner = candidate
                winner_votes = votes
        if winner is None:
            continue

        for candidate in primary_candidates:
            if candidate is winner:
                candidate["Status"] = "general (nominated)"
                candidate["ballotAccessStatus"] = "qualified"
                candidate["statusReason"] = "winner_of_completed_primary"
            else:
                if candidate.get("Status") != "did not make ballot":
                    candidate["Status"] = "eliminated"
                    candidate["ballotAccessStatus"] = "qualified"
                    candidate["statusReason"] = "in_completed_primary_not_in_runoff_or_general"


def finance_number(row: dict[str, str], key: str) -> float | None:
    raw = (row.get(key) or "").replace(",", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_finance_indexes(rows: list[dict[str, str]]) -> dict[str, dict[Any, list[dict[str, Any]]]]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_key: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    by_name_seat: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        if (row.get("Cand_Office") or "").strip().upper() != "H":
            continue
        state = (row.get("Cand_Office_St") or "").strip().upper()
        dist_raw = (row.get("Cand_Office_Dist") or "").strip()
        dist_num = 0
        if dist_raw and dist_raw.isdigit():
            dist_num = int(dist_raw)
        seat_id = f"{state}-AL" if dist_num == 0 else f"{state}-{dist_num:02d}"
        seat_id = normalize_seat_id(seat_id)

        party = normalize_party(row.get("Cand_Party_Affiliation"))
        name = str(row.get("Cand_Name") or "").strip()
        name_norm = normalize_name(name)
        cand_id = str(row.get("Cand_Id") or "").strip()

        parsed = {
            "candidateId": cand_id or None,
            "seatId": seat_id,
            "name": name,
            "nameNorm": name_norm,
            "partyCode": party,
            "receipts": finance_number(row, "Total_Receipt"),
            "disbursement": finance_number(row, "Total_Disbursement"),
            "cashOnHand": finance_number(row, "Cash_On_Hand_COP"),
            "coverageEndDate": parse_date(row.get("Coverage_End_Date")),
            "raw": row,
        }

        if cand_id:
            by_id[cand_id].append(parsed)
        if seat_id and name_norm:
            by_key[(seat_id, name_norm, party)].append(parsed)
            by_name_seat[(seat_id, name_norm)].append(parsed)

    return {
        "by_id": by_id,
        "by_key": by_key,
        "by_name_seat": by_name_seat,
    }


def _candidate_finance_match_score(candidate: dict[str, Any], finance_record: dict[str, Any]) -> tuple[float, str]:
    candidate_variants = normalized_candidate_variants(candidate)
    finance_name_norm = str(finance_record.get("nameNorm") or "")
    if not candidate_variants or not finance_name_norm:
        return 0.0, "unmatched"

    if finance_name_norm in candidate_variants:
        return 1.0, "name_or_alias_exact"

    best_ratio = max(difflib.SequenceMatcher(a=variant, b=finance_name_norm).ratio() for variant in candidate_variants)
    variant_last_names = {variant.split()[-1] for variant in candidate_variants if variant.split()}
    finance_tokens = finance_name_norm.split()
    finance_last_name = finance_tokens[-1] if finance_tokens else ""

    if best_ratio >= 0.93 and finance_last_name and finance_last_name in variant_last_names:
        return 0.94, "name_or_alias_similarity"

    for variant in candidate_variants:
        candidate_tokens = variant.split()
        if len(candidate_tokens) < 2 or len(finance_tokens) < 2:
            continue
        candidate_first = candidate_tokens[0]
        candidate_last = candidate_tokens[-1]
        finance_first = finance_tokens[0]
        finance_second = finance_tokens[1]
        if candidate_last == finance_first and candidate_first[:1] == finance_second[:1]:
            return 0.95, "name_reversed_initial_match"
    return 0.0, "unmatched"


def reconcile_candidates(candidates: list[dict[str, Any]], finance_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    finance_indexes = build_finance_indexes(finance_rows)
    finance_by_seat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finance_record_list in finance_indexes["by_name_seat"].values():
        for finance_record in finance_record_list:
            finance_by_seat[str(finance_record.get("seatId") or "")].append(finance_record)

    resolved: list[CandidateLinkResult] = []
    for candidate in candidates:
        candidate_copy = dict(candidate)
        seat_id = normalize_seat_id(candidate_copy.get("seatId"))
        candidate_copy["seatId"] = seat_id
        party_norm = normalize_party(candidate_copy.get("partyCode")) or "OWN"
        candidate_copy["partyCode"] = party_norm
        candidate_copy.setdefault("aliases", [])
        candidate_copy["nameNorm"] = normalize_name(candidate_copy.get("name"))
        link_strategy = "canonical_candidate"
        link_score = 1.0

        candidate_id = str(candidate_copy.get("candidateId") or "").strip()
        if not candidate_id:
            best_match: dict[str, Any] | None = None
            best_score = 0.0
            best_strategy = "unmatched"
            for finance_record in finance_by_seat.get(seat_id, []):
                score, strategy = _candidate_finance_match_score(candidate_copy, finance_record)
                if score > best_score:
                    best_match = finance_record
                    best_score = score
                    best_strategy = strategy
            if best_match is not None and best_score >= 0.94:
                candidate_copy["candidateId"] = best_match.get("candidateId")
                if (normalize_party(candidate_copy.get("partyCode")) or "OWN") == "OWN":
                    candidate_copy["partyCode"] = normalize_party(best_match.get("partyCode")) or candidate_copy["partyCode"]
                append_unique(candidate_copy["aliases"], best_match.get("name"))
                link_strategy = f"reconciled_{best_strategy}"
                link_score = best_score

        resolved.append(CandidateLinkResult(candidate=candidate_copy, strategy=link_strategy, score=link_score))

    grouped_by_identity: dict[tuple[str, str, str], list[CandidateLinkResult]] = defaultdict(list)
    for link in resolved:
        candidate = link.candidate
        seat_id = normalize_seat_id(candidate.get("seatId"))
        party_norm = normalize_party(candidate.get("partyCode")) or "OWN"
        # Group by normalized seat+party+name identity so source augmentation
        # cannot emit duplicate rows for the same candidate identity.
        identity_key = (seat_id, f"name:{normalize_name(candidate.get('name'))}", party_norm)
        grouped_by_identity[identity_key].append(link)

    reconciled: list[dict[str, Any]] = []
    for identity_candidates in grouped_by_identity.values():
        identity_candidates.sort(
            key=lambda link: (
                str(link.candidate.get("candidateId") or "") == "",
                normalize_party(link.candidate.get("partyCode")) == "OWN",
                -link.score,
            )
        )
        canonical = identity_candidates[0]
        canonical_candidate = canonical.candidate
        for duplicate in identity_candidates[1:]:
            append_unique(canonical_candidate["aliases"], duplicate.candidate.get("name"))
            for alias in duplicate.candidate.get("aliases") or []:
                append_unique(canonical_candidate["aliases"], alias)
            duplicate_party = normalize_party(duplicate.candidate.get("partyCode")) or "OWN"
            if duplicate_party == "OWN" and duplicate.score < 0.94:
                duplicate.suppress = True
            else:
                duplicate.suppress = True

        canonical_candidate["reconcileIdentityStrategy"] = canonical.strategy
        canonical_candidate["reconcileIdentityScore"] = canonical.score
        if not canonical.suppress:
            reconciled.append(canonical_candidate)

    return reconciled


def match_finance(row: dict[str, Any], indexes: dict[str, dict[Any, list[dict[str, Any]]]]) -> MatchResult:
    candidate_id = str(row.get("CandidateID") or "")
    if candidate_id:
        by_id = indexes["by_id"].get(candidate_id, [])
        if len(by_id) == 1:
            return MatchResult(by_id[0], "candidateId_exact", 1.0)
    seat_id = str(row.get("2026 Seat") or "")
    candidate_variants: list[str] = []
    append_unique(candidate_variants, row.get("BallotpediaName"))
    for name in row.get("FilingName") or []:
        append_unique(candidate_variants, name)
    for name in row.get("KalshiName") or []:
        append_unique(candidate_variants, name)
    party_norm = normalize_party(row.get("Party"))
    for candidate_name in candidate_variants:
        name_norm = normalize_name(candidate_name)
        if not name_norm:
            continue
        keyed = indexes["by_key"].get((seat_id, name_norm, party_norm), [])
        if len(keyed) == 1:
            return MatchResult(keyed[0], "seat_name_party_exact", 0.96)
        aliases = indexes["by_name_seat"].get((seat_id, name_norm), [])
        if len(aliases) == 1:
            return MatchResult(aliases[0], "seat_name_exact", 0.88)
    return MatchResult(None, "unmatched", 0.0)


def append_unique(values: list[str], value: str | None) -> None:
    if value is None:
        return
    cleaned = str(value).strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)


def build_identity_metadata(candidate: dict[str, Any], finance_match: MatchResult | None = None) -> dict[str, Any]:
    kalshi_aliases: list[str] = []
    filing_aliases: list[str] = []
    fec_aliases: list[str] = []

    append_unique(kalshi_aliases, candidate.get("kalshiName"))
    append_unique(kalshi_aliases, candidate.get("matchedKalshiName"))
    for value in candidate.get("kalshiNameMatches") or []:
        append_unique(kalshi_aliases, value)
    append_unique(filing_aliases, candidate.get("matchedCanonicalName"))
    for value in candidate.get("filingNameMatches") or []:
        append_unique(filing_aliases, value)
    for alias in candidate.get("aliases") or []:
        append_unique(kalshi_aliases, alias)
        append_unique(filing_aliases, alias)

    matched_finance = finance_match.record if finance_match else None
    if matched_finance:
        append_unique(fec_aliases, matched_finance.get("name"))
        append_unique(filing_aliases, matched_finance.get("name"))

    all_aliases: list[str] = []
    for alias in kalshi_aliases:
        append_unique(all_aliases, alias)
    for alias in fec_aliases:
        append_unique(all_aliases, alias)

    candidate_ids: list[str] = []
    append_unique(candidate_ids, candidate.get("candidateId"))
    if matched_finance:
        append_unique(candidate_ids, matched_finance.get("candidateId"))

    return {
        "aliases": all_aliases,
        "sourceAliases": {
            "kalshi": kalshi_aliases,
            "fec": fec_aliases,
        },
        "candidateIds": candidate_ids,
        "filingNames": filing_aliases,
        "kalshiNames": kalshi_aliases,
    }


def _status_priority(status: str | None) -> int:
    return {
        "runoff": 5,
        "general (nominated)": 4,
        "primary": 3,
        "eliminated": 2,
        "did not make ballot": 1,
        "general (other)": 0,
    }.get(str(status or "").strip(), -1)


def dedupe_records_by_ballotpedia_key(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in records:
        key = (
            str(row.get("Primary ID") or "").strip(),
            str(row.get("RunoffID") or "").strip(),
            normalize_seat_id(row.get("2026 Seat")),
            normalize_party(row.get("Party")) or "OWN",
            normalize_name(row.get("BallotpediaName")),
        )
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = row
            continue

        preferred = existing
        contender = row
        existing_priority = _status_priority(existing.get("Status"))
        contender_priority = _status_priority(contender.get("Status"))
        if contender_priority > existing_priority:
            preferred, contender = contender, existing
        elif contender_priority == existing_priority:
            existing_votes = parse_number(existing.get("Votes in Primary")) or 0.0
            contender_votes = parse_number(contender.get("Votes in Primary")) or 0.0
            if contender_votes > existing_votes:
                preferred, contender = contender, existing

        for field in ("FilingName", "KalshiName", "aliases", "candidateIds"):
            preferred.setdefault(field, [])
            for value in contender.get(field) or []:
                append_unique(preferred[field], value)
        preferred.setdefault("sourceAliases", {"kalshi": [], "fec": []})
        contender_source_aliases = contender.get("sourceAliases") or {}
        for field in ("kalshi", "fec"):
            preferred["sourceAliases"].setdefault(field, [])
            for value in contender_source_aliases.get(field) or []:
                append_unique(preferred["sourceAliases"][field], value)
        preferred.setdefault("sourceFlags", {})
        contender_source_flags = contender.get("sourceFlags") or {}
        for flag_key, flag_value in contender_source_flags.items():
            preferred["sourceFlags"][flag_key] = bool(preferred["sourceFlags"].get(flag_key) or flag_value)
        preferred["BallotpediaIsIncumbent"] = bool(preferred.get("BallotpediaIsIncumbent") or contender.get("BallotpediaIsIncumbent"))
        preferred["CanonicalIsIncumbent"] = bool(preferred.get("CanonicalIsIncumbent") or contender.get("CanonicalIsIncumbent"))
        preferred["IsIncumbent"] = bool(preferred.get("BallotpediaIsIncumbent") or preferred.get("CanonicalIsIncumbent"))
        preferred_party = normalize_party(preferred.get("Party")) or "OWN"
        contender_party = normalize_party(contender.get("Party")) or "OWN"
        if preferred_party in {"NPA", "OWN"} and contender_party not in {"NPA", "OWN"}:
            preferred["Party"] = contender_party

        if not preferred.get("CandidateID") and contender.get("CandidateID"):
            preferred["CandidateID"] = contender.get("CandidateID")

        by_key[key] = preferred
    return list(by_key.values())


def build_rollup(
    candidates: list[dict[str, Any]],
    primary_rows: list[dict[str, str]],
    runoff_rows: list[dict[str, str]],
    general_rows: list[dict[str, str]],
    finance_rows: list[dict[str, str]],
    kalshi_contests: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    snapshot_date = load_snapshot_validation_date()
    primary_by_seat = parse_primary_round_rows(primary_rows)
    runoff_by_seat = parse_primary_round_rows(runoff_rows)
    primary_odds_map_by_primary_id: dict[str, dict[str, float]] = {}
    primary_odds_map_out_of_band_by_primary_id: dict[str, bool] = {}
    runoff_by_id: dict[str, dict[str, Any]] = {}
    for seat_rows in runoff_by_seat.values():
        for row in seat_rows:
            runoff_id = str(row.get("primary_id") or "").strip()
            if runoff_id:
                runoff_by_id[runoff_id] = row
    for row in primary_rows:
        primary_id = str(row.get("primary_id") or "").strip()
        if not primary_id:
            continue
        odds_map = parse_float_map(row.get("kalshi_primary_odds_map"))
        primary_odds_map_by_primary_id[primary_id] = odds_map
        _, _status = odds_map_sum_status(odds_map)
        primary_odds_map_out_of_band_by_primary_id[primary_id] = _status == "out_of_band"
    general_date_by_seat: dict[str, str | None] = {}
    general_odds_map_by_seat: dict[str, dict[str, float]] = {}
    general_odds_map_out_of_band_by_seat: dict[str, bool] = {}
    for row in general_rows:
        seat = normalize_seat_id(row.get("seat"))
        if not seat:
            continue
        general_date_by_seat[seat] = parse_date(row.get("general_date"))
        odds_map = parse_float_map(row.get("kalshi_general_odds_map"))
        general_odds_map_by_seat[seat] = odds_map
        _, _status = odds_map_sum_status(odds_map)
        general_odds_map_out_of_band_by_seat[seat] = _status == "out_of_band"

    general_nominees_by_seat_party: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in general_rows:
        seat = normalize_seat_id(row.get("seat"))
        for party_code, field in (("DEM", "nominee_d"), ("REP", "nominee_r"), ("GRE", "nominee_green"), ("LIB", "nominee_libertarian")):
            value = str(row.get(field) or "").strip()
            if value:
                general_nominees_by_seat_party[(seat, party_code)].add(normalize_name(value))

    # Build a lookup of runoff candidate names by runoff_id so we can assign concrete runoff status
    # even when the election did not have an explicit runoff row.
    runoff_candidates_by_runoff_id: dict[str, set[str]] = defaultdict(set)
    for row in runoff_rows:
        runoff_id = str(row.get("runoff_id") or row.get("primary_id") or "").strip()
        if not runoff_id:
            continue
        for candidate_name in (row.get("runoff_candidate_1"), row.get("runoff_candidate_2")):
            if candidate_name:
                runoff_candidates_by_runoff_id[runoff_id].add(normalize_name(candidate_name))
        candidates_json = row.get("candidates")
        if isinstance(candidates_json, str) and candidates_json.strip():
            try:
                parsed = json.loads(candidates_json)
                if isinstance(parsed, list):
                    for candidate_name in parsed:
                        runoff_candidates_by_runoff_id[runoff_id].add(normalize_name(str(candidate_name)))
            except json.JSONDecodeError:
                pass

    # Include primary-row runoff candidate references (for cases where runoff file is missing)
    for row in primary_rows:
        runoff_id = str(row.get("runoff_id") or "").strip()
        if not runoff_id:
            continue
        for candidate_name in (row.get("runoff_candidate_1"), row.get("runoff_candidate_2")):
            if candidate_name:
                runoff_candidates_by_runoff_id[runoff_id].add(normalize_name(candidate_name))

    # Determine primary winners for completed primaries lacking runoff information,
    # so we can mark expected general nominees.
    primary_winners_by_primary_id: dict[str, set[str]] = defaultdict(set)
    for row in primary_rows:
        primary_id = str(row.get("primary_id") or "").strip()
        if not primary_id:
            continue

        status = str(row.get("status") or "").strip().lower()
        round_value = str(row.get("round") or "").strip().lower()
        if status != "complete" or round_value != "primary":
            continue

        runoff_id = str(row.get("runoff_id") or "").strip()
        if runoff_id:
            # runoffs are handled separately; do not pre-assign deferred winners here
            continue

        primary_vote_count_map = row.get("primary_vote_count_map")
        if isinstance(primary_vote_count_map, str):
            primary_vote_count_map = parse_int_map(primary_vote_count_map)
        if not isinstance(primary_vote_count_map, dict) or not primary_vote_count_map:
            # if vote map not available, fallback to candidates list
            candidates_json = row.get("candidates")
            if isinstance(candidates_json, str) and candidates_json.strip():
                try:
                    parsed = json.loads(candidates_json)
                    if isinstance(parsed, list):
                        for candidate in parsed[:1]:
                            primary_winners_by_primary_id[primary_id].add(normalize_name(str(candidate)))
                except json.JSONDecodeError:
                    pass
            continue

        # pick winners: top 2 in nonpartisan races, top 1 in partisan races
        sorted_candidates = sorted(primary_vote_count_map.items(), key=lambda item: float(item[1] or 0), reverse=True)
        party_norm = normalize_party(row.get("party"))
        if party_norm == "NPA":
            winners = [name for name, _ in sorted_candidates[:2]]
        else:
            winners = [name for name, _ in sorted_candidates[:1]]

        for winner in winners:
            primary_winners_by_primary_id[primary_id].add(normalize_name(str(winner)))

    records: list[dict[str, Any]] = []
    for candidate in candidates:
        seat_id = normalize_seat_id(candidate.get("seatId"))
        canonical_party = normalize_party(candidate.get("partyCode")) or "OWN"
        party = normalize_party(candidate.get("ballotpediaPartyCode")) or canonical_party
        name = str(candidate.get("name") or "").strip()
        candidate_name_variants = normalized_candidate_variants(candidate)
        canonical_is_incumbent = infer_is_incumbent(candidate)
        ballotpedia_is_incumbent = bool(candidate.get("ballotpediaIncumbent"))

        reconcile_strategy = str(candidate.get("reconcileIdentityStrategy") or "canonical_candidate")
        reconcile_score = float(candidate.get("reconcileIdentityScore") or 1.0)
        base = {
            "BallotpediaName": str(candidate.get("ballotpediaName") or name),
            "CandidateID": candidate.get("candidateId"),
            "2026 Seat": seat_id,
            "Party": party,
            "CanonicalIsIncumbent": canonical_is_incumbent,
            "BallotpediaIsIncumbent": ballotpedia_is_incumbent,
            "IsIncumbent": bool(canonical_is_incumbent or ballotpedia_is_incumbent),
            "Status": "general (other)",
            "Primary ID": None,
            "Votes in Primary": None,
            "Share of Primary": None,
            "RunoffID": None,
            "Votes in Runoff": None,
            "Share of Runoff": None,
            "Finance (Receipts)": None,
            "Finance (Dispursment)": None,
            "Finance (Cash in hand)": None,
            "Finance (Date)": None,
            "identityMatchStrategy": reconcile_strategy,
            "identityMatchScore": reconcile_score,
            "financeMatchStrategy": "unmatched",
            "financeMatchScore": 0.0,
            "FilingName": [],
            "KalshiName": [],
            "KalshiSeries": [],
            "KalshiMarkets": [],
            "KalshiPrimaryMarkets": [],
            "KalshiRunoffMarkets": [],
            "KalshiGeneralMarkets": [],
            "KalshiBestPrimaryOdds": None,
            "KalshiBestRunoffOdds": None,
            "KalshiBestGeneralOdds": None,
            "KalshiPrimaryOddsMap": {},
            "KalshiPrimaryOddsMapOutOfBand": False,
            "KalshiGeneralOddsMap": general_odds_map_by_seat.get(seat_id, {}),
            "KalshiGeneralOddsMapOutOfBand": general_odds_map_out_of_band_by_seat.get(seat_id, False),
            "KalshiLinkStrategy": "",
            "KalshiLinkScore": 0.0,
            "aliases": [],
            "sourceAliases": {"kalshi": [], "fec": []},
            "candidateIds": [],
            "sourceFlags": {
                "hasPrimaryResults": False,
                "hasRunoffResults": False,
                "hasFinance": False,
            },
            "ballotAccessStatus": "unknown",
            "statusReason": "unresolved",
            "primaryDate": None,
            "runoffDate": None,
            "generalDate": general_date_by_seat.get(seat_id),
        }

        seat_primaries = primary_by_seat.get(seat_id, [])
        party_primaries = [row for row in seat_primaries if normalize_party(row.get("party")) == party]
        matched_primary = find_matching_round_row(candidate, party_primaries)
        if matched_primary is None and any(normalize_party(row.get("party")) == "NPA" for row in seat_primaries):
            matched_primary = find_matching_round_row(candidate, seat_primaries)
        if matched_primary:
            base["Primary ID"] = matched_primary.get("primary_id")
            _pid = str(base["Primary ID"] or "").strip()
            base["KalshiPrimaryOddsMap"] = primary_odds_map_by_primary_id.get(_pid, {})
            base["KalshiPrimaryOddsMapOutOfBand"] = primary_odds_map_out_of_band_by_primary_id.get(_pid, False)
            votes_map = matched_primary.get("primary_vote_count_map") or {}
            share_map = matched_primary.get("primary_vote_share_map") or {}
            base["Votes in Primary"] = first_matching_round_value(votes_map, candidate_name_variants)
            base["Share of Primary"] = first_matching_round_value(share_map, candidate_name_variants)
            base["RunoffID"] = matched_primary.get("runoff_id")
            base["sourceFlags"]["hasPrimaryResults"] = True
            base["primaryDate"] = matched_primary.get("primary_date")
            primary_lane_party = normalize_party(matched_primary.get("party")) or "OWN"
            party_from_primary = None
            if primary_lane_party in {"NPA", "OWN"}:
                party_from_primary = first_matching_round_party(matched_primary.get("candidate_party_map") or {}, candidate_name_variants)
            if party_from_primary:
                party = party_from_primary
                base["Party"] = party
            ballotpedia_from_primary = first_matching_round_bool(matched_primary.get("candidate_incumbent_map") or {}, candidate_name_variants)
            base["BallotpediaIsIncumbent"] = bool(base["BallotpediaIsIncumbent"] or ballotpedia_from_primary)
            base["IsIncumbent"] = bool(base["BallotpediaIsIncumbent"] or base["CanonicalIsIncumbent"])

        seat_runoffs = runoff_by_seat.get(seat_id, [])
        party_runoffs = [row for row in seat_runoffs if normalize_party(row.get("party")) == party]
        matched_runoff = find_matching_round_row(candidate, party_runoffs)
        if matched_runoff is None and any(normalize_party(row.get("party")) == "NPA" for row in seat_runoffs):
            matched_runoff = find_matching_round_row(candidate, seat_runoffs)
        if matched_runoff:
            base["RunoffID"] = matched_runoff.get("primary_id") or base["RunoffID"]
            votes_map = matched_runoff.get("primary_vote_count_map") or {}
            share_map = matched_runoff.get("primary_vote_share_map") or {}
            base["Votes in Runoff"] = first_matching_round_value(votes_map, candidate_name_variants)
            base["Share of Runoff"] = first_matching_round_value(share_map, candidate_name_variants)
            base["sourceFlags"]["hasRunoffResults"] = True
            base["runoffDate"] = matched_runoff.get("runoff_date") or (matched_primary or {}).get("runoff_date")
            runoff_lane_party = normalize_party(matched_runoff.get("party")) or "OWN"
            party_from_runoff = None
            if runoff_lane_party in {"NPA", "OWN"}:
                party_from_runoff = first_matching_round_party(matched_runoff.get("candidate_party_map") or {}, candidate_name_variants)
            if party_from_runoff:
                party = party_from_runoff
                base["Party"] = party
            ballotpedia_from_runoff = first_matching_round_bool(matched_runoff.get("candidate_incumbent_map") or {}, candidate_name_variants)
            base["BallotpediaIsIncumbent"] = bool(base["BallotpediaIsIncumbent"] or ballotpedia_from_runoff)
            base["IsIncumbent"] = bool(base["BallotpediaIsIncumbent"] or base["CanonicalIsIncumbent"])

        is_general_nominee = bool(candidate_name_variants & general_nominees_by_seat_party.get((seat_id, party), set()))

        matched_primary_id = str((matched_primary or {}).get("primary_id") or "").strip()
        if not is_general_nominee and matched_primary_id:
            if candidate_name_norm := normalize_name(name):
                if candidate_name_norm in primary_winners_by_primary_id.get(matched_primary_id, set()):
                    is_general_nominee = True
                    base["generalDate"] = general_date_by_seat.get(seat_id) or base.get("generalDate")

        if is_general_nominee:
            base["generalDate"] = general_date_by_seat.get(seat_id) or base.get("generalDate")

        candidate_name_norm = normalize_name(name)

        # If the candidate is explicitly part of runoff candidates, mark as runoff.
        is_runoff_candidate = False
        if matched_runoff:
            is_runoff_candidate = True
            base["sourceFlags"]["hasRunoffResults"] = True
        elif base.get("RunoffID"):
            runoff_id = str(base.get("RunoffID") or "").strip()
            if runoff_id and candidate_name_norm in runoff_candidates_by_runoff_id.get(runoff_id, set()):
                is_runoff_candidate = True
                base["sourceFlags"]["hasRunoffResults"] = True

        # Candidates with RunoffID that didn't make the two-runoff candidate list are not runoff advancees.
        if base.get("RunoffID") and not is_runoff_candidate:
            base["RunoffID"] = None

        _null_out_future_votes(base, snapshot_date)

        canonical_status = infer_status_from_canonical(candidate)
        primary_cancellation_reason = str((matched_primary or {}).get("cancellation_reason") or "").strip().lower()
        linked_runoff_row = runoff_by_id.get(str(base.get("RunoffID") or "").strip())
        primary_concluded = _primary_round_concluded(matched_primary, linked_runoff_row, snapshot_date)
        unopposed_advanced = primary_cancellation_reason == "unopposed"

        if is_general_nominee:
            if matched_primary and (not primary_concluded) and (not unopposed_advanced):
                base["Status"] = "primary"
                base["statusReason"] = "nominee_suppressed_until_primary_concludes"
                base["ballotAccessStatus"] = "qualified"
            else:
                base["Status"] = "general (nominated)"
                base["statusReason"] = "matches_general_nominee"
                base["ballotAccessStatus"] = "qualified"
                # Runoff identifiers are only retained on active runoff rows.
                base["RunoffID"] = None
        elif is_runoff_candidate:
            if primary_concluded:
                base["Status"] = "runoff"
                base["statusReason"] = "appears_in_runoff_candidate_list"
                base["ballotAccessStatus"] = "qualified"
            else:
                base["Status"] = "primary"
                base["statusReason"] = "runoff_suppressed_until_primary_concludes"
                base["ballotAccessStatus"] = "qualified"
        elif base["sourceFlags"]["hasPrimaryResults"]:
            if primary_concluded:
                base["Status"] = "eliminated"
                base["statusReason"] = "in_completed_primary_not_in_runoff_or_general"
                base["ballotAccessStatus"] = "qualified"
            else:
                base["Status"] = "primary"
                base["statusReason"] = "appears_in_primary_results"
                base["ballotAccessStatus"] = "qualified"
        elif canonical_status in {"general (nominated)", "primary"}:
            base["Status"] = canonical_status
            base["statusReason"] = "canonical_status"
            base["ballotAccessStatus"] = "qualified" if canonical_status == "general (nominated)" else "unknown"
        else:
            base["Status"] = "did not make ballot"
            base["statusReason"] = "not_present_in_ballotpedia_election_sets"
            base["ballotAccessStatus"] = "unknown"

        records.append(base)

    records = dedupe_records_by_ballotpedia_key(records)
    parsed_primary_rows = [row for seat_rows in primary_by_seat.values() for row in seat_rows]
    parsed_runoff_rows = [row for seat_rows in runoff_by_seat.values() for row in seat_rows]
    enforce_primary_outcome_constraints(records, parsed_primary_rows, parsed_runoff_rows, snapshot_date)

    # finance enrichment
    finance_indexes = build_finance_indexes(finance_rows)
    finance_matches_by_row: dict[int, MatchResult] = {}
    for index, row in enumerate(records):
        match = match_finance(row, finance_indexes)
        finance_matches_by_row[index] = match
        row["financeMatchStrategy"] = match.strategy
        row["financeMatchScore"] = match.score
        row["identityMatchStrategy"] = match.strategy if match.record is not None else row["identityMatchStrategy"]
        row["identityMatchScore"] = match.score if match.record is not None else row["identityMatchScore"]
        if match.record is None:
            continue
        row["Finance (Receipts)"] = match.record.get("receipts")
        row["Finance (Dispursment)"] = match.record.get("disbursement")
        row["Finance (Cash in hand)"] = match.record.get("cashOnHand")
        row["Finance (Date)"] = match.record.get("coverageEndDate")
        row["sourceFlags"]["hasFinance"] = True

    # Populate aliases/candidate IDs from canonical + finance data.
    candidates_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        key = (
            normalize_seat_id(candidate.get("seatId")),
            normalize_name(candidate.get("name")),
        )
        candidates_by_key[key].append(candidate)
    for index, row in enumerate(records):
        row_key = (
            normalize_seat_id(row.get("2026 Seat")),
            normalize_name(row.get("BallotpediaName")),
        )
        candidate_pool = candidates_by_key.get(row_key, [])
        canonical_candidate = None
        row_party = normalize_party(row.get("Party")) or "OWN"
        for candidate_option in candidate_pool:
            if (normalize_party(candidate_option.get("partyCode")) or "OWN") == row_party:
                canonical_candidate = candidate_option
                break
        if canonical_candidate is None and candidate_pool:
            canonical_candidate = candidate_pool[0]
        if canonical_candidate is None:
            canonical_candidate = {
            "candidateId": row.get("CandidateID"),
            "kalshiName": None,
            "aliases": [],
        }
        finance_match = finance_matches_by_row.get(index)
        row_identity = build_identity_metadata(canonical_candidate, finance_match)
        row["aliases"] = row_identity["aliases"]
        row["sourceAliases"] = row_identity["sourceAliases"]
        row["candidateIds"] = row_identity["candidateIds"]
        row["FilingName"] = sorted(set(row_identity["filingNames"]), key=lambda value: normalize_name(value))
        row["KalshiName"] = sorted(set(row_identity["kalshiNames"]), key=lambda value: normalize_name(value))

    contests = kalshi_contests if kalshi_contests is not None else load_kalshi_us_rep_contests(DEFAULT_KALSHI_CONTEST_INDEX)
    enrich_rows_with_kalshi_markets(records, contests)

    records.sort(
        key=lambda item: (
            item.get("2026 Seat") or "",
            (item.get("Party") or "") not in {"DEM", "REP"},
            item.get("Party") or "",
            item.get("BallotpediaName") or "",
        )
    )
    return records


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "BallotpediaName",
        "CandidateID",
        "2026 Seat",
        "Party",
        "BallotpediaIsIncumbent",
        "CanonicalIsIncumbent",
        "IsIncumbent",
        "Status",
        "Primary ID",
        "Votes in Primary",
        "Share of Primary",
        "RunoffID",
        "Votes in Runoff",
        "Share of Runoff",
        "Finance (Receipts)",
        "Finance (Dispursment)",
        "Finance (Cash in hand)",
        "Finance (Date)",
        "identityMatchStrategy",
        "identityMatchScore",
        "financeMatchStrategy",
        "financeMatchScore",
        "FilingName",
        "KalshiName",
        "KalshiSeries",
        "KalshiMarkets",
        "KalshiPrimaryMarkets",
        "KalshiRunoffMarkets",
        "KalshiGeneralMarkets",
        "KalshiBestPrimaryOdds",
        "KalshiBestRunoffOdds",
        "KalshiBestGeneralOdds",
        "KalshiPrimaryOddsMap",
        "KalshiPrimaryOddsMapOutOfBand",
        "KalshiGeneralOddsMap",
        "KalshiGeneralOddsMapOutOfBand",
        "KalshiLinkStrategy",
        "KalshiLinkScore",
        "aliases",
        "sourceAliases",
        "candidateIds",
        "sourceFlags",
        "ballotAccessStatus",
        "statusReason",
        "primaryDate",
        "runoffDate",
        "generalDate",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["aliases"] = json.dumps(out["aliases"], separators=(",", ":"), ensure_ascii=False)
            out["sourceAliases"] = json.dumps(out["sourceAliases"], separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            out["candidateIds"] = json.dumps(out["candidateIds"], separators=(",", ":"), ensure_ascii=False)
            out["FilingName"] = json.dumps(out["FilingName"], separators=(",", ":"), ensure_ascii=False)
            out["KalshiName"] = json.dumps(out["KalshiName"], separators=(",", ":"), ensure_ascii=False)
            out["KalshiSeries"] = json.dumps(out["KalshiSeries"], separators=(",", ":"), ensure_ascii=False)
            out["KalshiMarkets"] = json.dumps(out["KalshiMarkets"], separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            out["KalshiPrimaryMarkets"] = json.dumps(out["KalshiPrimaryMarkets"], separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            out["KalshiRunoffMarkets"] = json.dumps(out["KalshiRunoffMarkets"], separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            out["KalshiGeneralMarkets"] = json.dumps(out["KalshiGeneralMarkets"], separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            out["KalshiPrimaryOddsMap"] = json.dumps(out["KalshiPrimaryOddsMap"], separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            out["KalshiGeneralOddsMap"] = json.dumps(out["KalshiGeneralOddsMap"], separators=(",", ":"), ensure_ascii=False, sort_keys=True)
            out["sourceFlags"] = json.dumps(out["sourceFlags"], separators=(",", ":"), sort_keys=True)
            writer.writerow(out)


def write_json(path: Path, rows: list[dict[str, Any]], input_files: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "electionCycle": 2026,
        "rowCount": len(rows),
        "sources": [str(file.relative_to(REPO_ROOT)) for file in input_files],
        "rows": rows,
    }
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate-level House rollup files")
    parser.add_argument("--seats", type=Path, default=DEFAULT_SEATS_FILE)
    parser.add_argument("--primary", type=Path, default=DEFAULT_PRIMARY_FILE)
    parser.add_argument("--runoff", type=Path, default=DEFAULT_RUNOFF_FILE)
    parser.add_argument("--general", type=Path, default=DEFAULT_GENERAL_FILE)
    parser.add_argument("--finance", type=Path, default=DEFAULT_FINANCE_FILE)
    parser.add_argument("--kalshi-contests", type=Path, default=DEFAULT_KALSHI_CONTEST_INDEX)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates = load_seat_candidates(args.seats)
    primary_rows = load_csv(args.primary)
    runoff_rows = load_csv(args.runoff)
    general_rows = load_csv(args.general)
    finance_rows = load_csv(args.finance)
    kalshi_contests = load_kalshi_us_rep_contests(args.kalshi_contests)

    augmented_candidates = augment_candidates_with_ballotpedia_sources(
        candidates=candidates,
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
        general_rows=general_rows,
    )
    reconciled_candidates = reconcile_candidates(augmented_candidates, finance_rows)

    rollup = build_rollup(
        candidates=reconciled_candidates,
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
        general_rows=general_rows,
        finance_rows=finance_rows,
        kalshi_contests=kalshi_contests,
    )

    input_files = [args.seats, args.primary, args.runoff, args.general, args.finance]
    write_csv(args.out_csv, rollup)
    write_json(args.out_json, rollup, input_files)

    print(f"Candidate rows emitted: {len(rollup)}")
    print(f"CSV: {args.out_csv}")
    print(f"JSON: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
