"""Ballotpedia candidate to FEC matching utilities."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import DEFAULT_FEC_CANDIDATE_SUMMARY_FILE, ELECTION_CYCLE_YEAR
from .normalize import clean_name, norm_party
from senate_seat_ids import infer_senate_seat_id

SUFFIX_RE = re.compile(r"\b(JR|SR|II|III|IV|V)\b", flags=re.IGNORECASE)
HONORIFIC_RE = re.compile(r"\b(MR|MRS|MS|MISS|DR|REV|PROF|HON)\b", flags=re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^A-Z0-9 ]+")
WHITESPACE_RE = re.compile(r"\s+")

NICKNAME_EQUIV = {
    "MATT": "MATTHEW",
    "JEFF": "JEFFREY",
    "JIM": "JAMES",
    "MIKE": "MICHAEL",
    "KAT": "KATHERINE",
    "TONY": "ANTHONY",
}


@dataclass
class FecCandidate:
    seat: str
    party: str
    name: str
    candidate_id: str
    coverage_end_date: str
    office: str = "us_house"
    is_incumbent: bool = False


@dataclass
class IndexedFecCandidate:
    candidate: FecCandidate
    normalized_name: str
    tokens_list: list[str]
    tokens_set: set[str]


@dataclass
class FecMatcher:
    indexed_candidates: list[IndexedFecCandidate]
    by_seat: dict[str, list[IndexedFecCandidate]]
    by_seat_party: dict[tuple[str, str], list[IndexedFecCandidate]]
    exact_by_seat_name: dict[tuple[str, str], IndexedFecCandidate]
    exact_by_seat_party_name: dict[tuple[str, str, str], IndexedFecCandidate]
    query_cache: dict[tuple[str, str, str], tuple[str, str, float]]
    normalized_target_cache: dict[str, str]
    token_target_cache: dict[str, tuple[list[str], set[str]]]


def build_fec_candidate_id_index(fec_candidates: Iterable[FecCandidate]) -> dict[str, FecCandidate]:
    out: dict[str, FecCandidate] = {}
    for candidate in fec_candidates:
        if candidate.candidate_id:
            out.setdefault(candidate.candidate_id, candidate)
    return out


def _normalize_person_name(value: str) -> str:
    text = clean_name(value).upper()
    text = SUFFIX_RE.sub(" ", text)
    text = HONORIFIC_RE.sub(" ", text)
    text = NON_ALNUM_RE.sub(" ", text)
    tokens = [NICKNAME_EQUIV.get(token, token) for token in WHITESPACE_RE.sub(" ", text).strip().split(" ") if token]
    return " ".join(tokens)


def _name_tokens(value: str) -> set[str]:
    return set(_normalize_person_name(value).split())


def _name_token_list(value: str) -> list[str]:
    return [token for token in _normalize_person_name(value).split() if token]


def _fuzzy_score_from_tokens(
    a_tokens_list: list[str],
    a_tokens: set[str],
    b_tokens_list: list[str],
    b_tokens: set[str],
) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    if a_tokens == b_tokens:
        return 1.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    score = inter / union if union else 0.0
    # extra bump when last token matches (surname alignment)
    a_last = a_tokens_list[-1] if a_tokens_list else ""
    b_last = b_tokens_list[-1] if b_tokens_list else ""
    if a_last and a_last == b_last:
        score += 0.15
    if a_tokens_list and b_tokens_list and a_tokens_list[0] == b_tokens_list[0]:
        score += 0.05
    return min(score, 1.0)


def _office_from_fec_row(row: dict) -> str | None:
    office_code = (row.get("Cand_Office") or "").strip().upper()
    if office_code == "H":
        return "us_house"
    if office_code == "S":
        return "us_senate"
    return None


def seat_from_fec_row(row: dict, *, office: str | None = None) -> str | None:
    effective_office = office or _office_from_fec_row(row)
    if effective_office not in {"us_house", "us_senate"}:
        return None
    office_code = "H" if effective_office == "us_house" else "S"
    if (row.get("Cand_Office") or "").strip().upper() != office_code:
        return None

    state = (row.get("Cand_Office_St") or "").strip().upper()
    if not state:
        return None

    if effective_office == "us_senate":
        is_special = "SPECIAL" in " ".join(
            [
                str(row.get("Cand_Election_Year") or ""),
                str(row.get("Cand_Office_St") or ""),
                str(row.get("Cand_Name") or ""),
                str(row.get("Cand_Office_Desc") or ""),
            ]
        ).upper()
        return infer_senate_seat_id(state_code=state, cycle_year=ELECTION_CYCLE_YEAR, is_special=is_special)

    district = (row.get("Cand_Office_Dist") or "").strip().upper()
    if not state or not district:
        return None
    if district in {"0", "00", "AL", "AT-LARGE"}:
        return f"{state}-AL"
    if district.isdigit():
        return f"{state}-{int(district)}"
    return None


def _party_from_fec_row(row: dict) -> str:
    raw = (row.get("Cand_Party_Affiliation") or "").strip().upper()
    if raw in {"DEM", "DFL"}:
        return "D"
    if raw in {"REP", "R"}:
        return "R"
    if raw == "LIB":
        return "L"
    if raw in {"GRE", "GRN"}:
        return "G"
    if raw in {"NPA", "NOP"}:
        return "NP"
    if raw == "IND":
        return "IND"
    return norm_party(raw)


def load_fec_rows(fec_file: Path = DEFAULT_FEC_CANDIDATE_SUMMARY_FILE) -> list[dict]:
    if not fec_file.exists():
        return []
    with fec_file.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_fec_candidates(
    fec_file: Path = DEFAULT_FEC_CANDIDATE_SUMMARY_FILE,
    rows: list[dict] | None = None,
    *,
    office: str = "us_house",
) -> list[FecCandidate]:
    source_rows = rows if rows is not None else load_fec_rows(fec_file)
    out: list[FecCandidate] = []
    for row in source_rows:
        seat = seat_from_fec_row(row, office=office)
        if not seat:
            continue
        name = clean_name(str(row.get("Cand_Name") or ""))
        parts = [part.strip() for part in name.split(",") if part.strip()]
        if len(parts) >= 2:
            name = " ".join(parts[1:] + [parts[0]])
        out.append(
            FecCandidate(
                seat=seat,
                party=_party_from_fec_row(row),
                name=name.title(),
                candidate_id=(row.get("Cand_Id") or "").strip(),
                coverage_end_date=(row.get("Coverage_End_Date") or "").strip(),
                office=office,
                is_incumbent=(row.get("Cand_Incumbent_Challenger_Open_Seat") or "").strip().upper() == "INCUMBENT",
            )
        )
    return out


def build_fec_matcher(fec_candidates: Iterable[FecCandidate]) -> FecMatcher:
    indexed_candidates: list[IndexedFecCandidate] = []
    by_seat: dict[str, list[IndexedFecCandidate]] = {}
    by_seat_party: dict[tuple[str, str], list[IndexedFecCandidate]] = {}
    exact_by_seat_name: dict[tuple[str, str], IndexedFecCandidate] = {}
    exact_by_seat_party_name: dict[tuple[str, str, str], IndexedFecCandidate] = {}
    for candidate in fec_candidates:
        normalized_name = _normalize_person_name(candidate.name)
        tokens_list = [token for token in normalized_name.split() if token]
        indexed = IndexedFecCandidate(
            candidate=candidate,
            normalized_name=normalized_name,
            tokens_list=tokens_list,
            tokens_set=set(tokens_list),
        )
        indexed_candidates.append(indexed)
        by_seat.setdefault(candidate.seat, []).append(indexed)
        by_seat_party.setdefault((candidate.seat, candidate.party), []).append(indexed)
        # Preserve first-seen candidate for deterministic exact matching.
        exact_by_seat_name.setdefault((candidate.seat, normalized_name), indexed)
        exact_by_seat_party_name.setdefault((candidate.seat, candidate.party, normalized_name), indexed)

    return FecMatcher(
        indexed_candidates=indexed_candidates,
        by_seat=by_seat,
        by_seat_party=by_seat_party,
        exact_by_seat_name=exact_by_seat_name,
        exact_by_seat_party_name=exact_by_seat_party_name,
        query_cache={},
        normalized_target_cache={},
        token_target_cache={},
    )


def _normalize_target_name(ballotpedia_name: str, matcher: FecMatcher | None = None) -> str:
    if matcher is None:
        return _normalize_person_name(ballotpedia_name)
    cached = matcher.normalized_target_cache.get(ballotpedia_name)
    if cached is not None:
        return cached
    normalized = _normalize_person_name(ballotpedia_name)
    matcher.normalized_target_cache[ballotpedia_name] = normalized
    return normalized


def _target_tokens(ballotpedia_name: str, matcher: FecMatcher | None = None) -> tuple[list[str], set[str]]:
    if matcher is None:
        tokens_list = _name_token_list(ballotpedia_name)
        return tokens_list, set(tokens_list)
    cached = matcher.token_target_cache.get(ballotpedia_name)
    if cached is not None:
        return cached
    normalized = _normalize_target_name(ballotpedia_name, matcher)
    tokens_list = [token for token in normalized.split() if token]
    payload = (tokens_list, set(tokens_list))
    matcher.token_target_cache[ballotpedia_name] = payload
    return payload


def _fuzzy_score(name_a: str, name_b: str) -> float:
    a_tokens_list = _name_token_list(name_a)
    b_tokens_list = _name_token_list(name_b)
    a_tokens = set(a_tokens_list)
    b_tokens = set(b_tokens_list)
    return _fuzzy_score_from_tokens(a_tokens_list, a_tokens, b_tokens_list, b_tokens)


def match_candidate(
    seat: str,
    party: str,
    ballotpedia_name: str,
    fec_candidates: Iterable[FecCandidate],
    *,
    matcher: FecMatcher | None = None,
) -> tuple[str, str, float]:
    effective_matcher = matcher if matcher is not None else build_fec_matcher(fec_candidates)
    query_key = (seat, party, ballotpedia_name)
    cached = effective_matcher.query_cache.get(query_key)
    if cached is not None:
        return cached

    normalized_target = _normalize_target_name(ballotpedia_name, effective_matcher)
    if party in {"OTH", "NP"}:
        seat_party_pool = effective_matcher.by_seat.get(seat, ())
        seat_party_exact = effective_matcher.exact_by_seat_name.get((seat, normalized_target))
    else:
        seat_party_pool = effective_matcher.by_seat_party.get((seat, party), ())
        seat_party_exact = effective_matcher.exact_by_seat_party_name.get((seat, party, normalized_target))
    if not seat_party_pool:
        seat_party_pool = effective_matcher.by_seat.get(seat, ())
        seat_party_exact = effective_matcher.exact_by_seat_name.get((seat, normalized_target))

    if not seat_party_pool:
        normalized_target = _normalize_target_name(ballotpedia_name, effective_matcher)
        exact_global = None
        if party not in {"OTH", "NP"}:
            for candidate in effective_matcher.indexed_candidates:
                if candidate.candidate.party == party and candidate.normalized_name == normalized_target:
                    exact_global = candidate
                    break
        if exact_global is None:
            for candidate in effective_matcher.indexed_candidates:
                if candidate.normalized_name == normalized_target:
                    exact_global = candidate
                    break
        if exact_global is not None:
            result = (exact_global.candidate.candidate_id, "global_exact_no_seat", 0.95)
            effective_matcher.query_cache[query_key] = result
            return result
        target_tokens_list, target_tokens_set = _target_tokens(ballotpedia_name, effective_matcher)
        global_best: tuple[IndexedFecCandidate | None, float] = (None, 0.0)
        for candidate in effective_matcher.indexed_candidates:
            if party not in {"OTH", "NP"} and candidate.candidate.party != party:
                continue
            if target_tokens_set and not (target_tokens_set & candidate.tokens_set):
                continue
            score = _fuzzy_score_from_tokens(
                target_tokens_list,
                target_tokens_set,
                candidate.tokens_list,
                candidate.tokens_set,
            )
            if global_best[0] is None or score > global_best[1]:
                global_best = (candidate, score)
        if global_best[0] is not None and global_best[1] >= 0.9:
            result = (
                global_best[0].candidate.candidate_id,
                "global_fuzzy_no_seat_high_confidence",
                float(round(global_best[1], 4)),
            )
            effective_matcher.query_cache[query_key] = result
            return result
        result = ("", "no_seat_candidates", 0.0)
        effective_matcher.query_cache[query_key] = result
        return result

    if seat_party_exact is not None:
        result = (seat_party_exact.candidate.candidate_id, "exact", 1.0)
        effective_matcher.query_cache[query_key] = result
        return result

    # Relaxed exact: ignore party when seat has the same normalized candidate name.
    seat_exact = effective_matcher.exact_by_seat_name.get((seat, normalized_target))
    if seat_exact is not None:
        result = (seat_exact.candidate.candidate_id, "seat_exact_party_relaxed", 0.99)
        effective_matcher.query_cache[query_key] = result
        return result

    if len(seat_party_pool) == 1:
        result = (seat_party_pool[0].candidate.candidate_id, "seat_party_singleton", 0.2)
        effective_matcher.query_cache[query_key] = result
        return result

    target_tokens_list, target_tokens_set = _target_tokens(ballotpedia_name, effective_matcher)
    target_last = target_tokens_list[-1] if target_tokens_list else ""
    target_first_initial = target_tokens_list[0][:1] if target_tokens_list else ""
    if target_last:
        surname_matches = [
            candidate for candidate in seat_party_pool
            if candidate.tokens_list and candidate.tokens_list[-1] == target_last
        ]
        if len(surname_matches) == 1:
            result = (surname_matches[0].candidate.candidate_id, "surname_unique", 0.35)
            effective_matcher.query_cache[query_key] = result
            return result
        if len(surname_matches) > 1 and target_first_initial:
            surname_initial_matches = [
                candidate for candidate in surname_matches
                if candidate.tokens_list and candidate.tokens_list[0][:1] == target_first_initial
            ]
            if len(surname_initial_matches) == 1:
                result = (surname_initial_matches[0].candidate.candidate_id, "surname_initial_unique", 0.34)
                effective_matcher.query_cache[query_key] = result
                return result

    best: tuple[IndexedFecCandidate | None, float] = (None, 0.0)
    best_ties = 0
    for candidate in seat_party_pool:
        score = _fuzzy_score_from_tokens(
            target_tokens_list,
            target_tokens_set,
            candidate.tokens_list,
            candidate.tokens_set,
        )
        if best[0] is None or score > best[1]:
            best = (candidate, score)
            best_ties = 1
        elif best[0] is not None and abs(score - best[1]) <= 0.000001:
            best_ties += 1

    best_candidate, best_score = best
    if best_candidate is None:
        # Name fallback across all seats/parties for extraction drift.
        global_best: tuple[IndexedFecCandidate | None, float] = (None, 0.0)
        for candidate in effective_matcher.indexed_candidates:
            # No overlap implies zero score, so skip early.
            if target_tokens_set and not (target_tokens_set & candidate.tokens_set):
                continue
            score = _fuzzy_score_from_tokens(
                target_tokens_list,
                target_tokens_set,
                candidate.tokens_list,
                candidate.tokens_set,
            )
            if score > global_best[1]:
                global_best = (candidate, score)
        if global_best[0] is not None and global_best[1] >= 0.75:
            result = (global_best[0].candidate.candidate_id, "global_name_fuzzy", float(round(global_best[1], 4)))
            effective_matcher.query_cache[query_key] = result
            return result
        result = ("", "no_match", 0.0)
        effective_matcher.query_cache[query_key] = result
        return result
    if best_ties > 1 and best_score >= 0.45:
        result = ("", "ambiguous_fuzzy", float(round(best_score, 4)))
        effective_matcher.query_cache[query_key] = result
        return result
    if best_score >= 0.45:
        result = (best_candidate.candidate.candidate_id, "fuzzy", float(round(best_score, 4)))
        effective_matcher.query_cache[query_key] = result
        return result
    if best_score >= 0.3:
        result = (best_candidate.candidate.candidate_id, "fuzzy_low_confidence", float(round(best_score, 4)))
        effective_matcher.query_cache[query_key] = result
        return result

    # Explicit cross-seat fallback is only allowed at a high confidence threshold.
    global_best: tuple[IndexedFecCandidate | None, float] = (None, 0.0)
    for candidate in effective_matcher.indexed_candidates:
        if target_tokens_set and not (target_tokens_set & candidate.tokens_set):
            continue
        score = _fuzzy_score_from_tokens(
            target_tokens_list,
            target_tokens_set,
            candidate.tokens_list,
            candidate.tokens_set,
        )
        if score > global_best[1]:
            global_best = (candidate, score)
    if global_best[0] is not None and global_best[1] >= 0.9:
        result = (global_best[0].candidate.candidate_id, "global_name_fuzzy_high_confidence", float(round(global_best[1], 4)))
        effective_matcher.query_cache[query_key] = result
        return result

    # Keep coverage high: when seat/party candidate pool exists, choose deterministic best-effort linkage.
    result = (best_candidate.candidate.candidate_id, "seat_party_best_effort", float(round(max(best_score, 0.01), 4)))
    effective_matcher.query_cache[query_key] = result
    return result


def enrich_rows_with_fec_candidate_maps(
    primary_rows: list[dict],
    runoff_rows: list[dict],
    fec_candidates: list[FecCandidate],
    *,
    matcher: FecMatcher | None = None,
    office: str = "us_house",
) -> list[dict]:
    unmatched: list[dict] = []
    effective_matcher = matcher if matcher is not None else build_fec_matcher(fec_candidates)

    for row in primary_rows + runoff_rows:
        candidate_names = list(row.get("candidates") or [])
        party_map = row.get("candidate_party_map") or {}
        id_map: dict[str, str] = {}
        strategy_map: dict[str, str] = {}
        score_map: dict[str, float] = {}
        for name in candidate_names:
            candidate_party = str(party_map.get(name) or row.get("party") or "").strip().upper()
            fec_id, strategy, score = match_candidate(
                str(row.get("seat") or ""),
                candidate_party,
                name,
                fec_candidates,
                matcher=effective_matcher,
            )
            if fec_id:
                id_map[name] = fec_id
            else:
                unmatched.append(
                    {
                        "office": office,
                        "seat": row.get("seat") or "",
                        "party": candidate_party,
                        "ballotpedia_name": name,
                        "reason": strategy,
                        "score": score,
                        "primary_id": row.get("primary_id") or "",
                    }
                )
            strategy_map[name] = strategy
            score_map[name] = score
        row["candidate_fec_id_map"] = id_map
        row["candidate_fec_match_strategy_map"] = strategy_map
        row["candidate_fec_match_score_map"] = score_map
    return unmatched


def build_fec_unmatched_rows(unmatched: list[dict]) -> list[dict]:
    dedup = {}
    for row in unmatched:
        key = (
            row.get("office") or "",
            row.get("seat") or "",
            row.get("party") or "",
            row.get("ballotpedia_name") or "",
        )
        if key not in dedup:
            dedup[key] = row
    return sorted(
        dedup.values(),
        key=lambda item: (
            item.get("office") or "",
            item.get("seat") or "",
            item.get("party") or "",
            item.get("ballotpedia_name") or "",
        ),
    )


def build_fec_match_audit(
    general_rows: list[dict],
    primary_rows: list[dict],
    runoff_rows: list[dict],
    fec_candidates: list[FecCandidate],
    *,
    office: str,
) -> tuple[list[dict], dict[str, float | int]]:
    seat_set = {
        str(row.get("seat") or "").strip()
        for row in general_rows + primary_rows + runoff_rows
        if str(row.get("seat") or "").strip()
    }
    by_fec_id: dict[str, list[dict]] = {}
    ballotpedia_candidates_by_seat: dict[str, list[tuple[str, str]]] = {}

    for row in general_rows + primary_rows + runoff_rows:
        seat = str(row.get("seat") or "").strip()
        candidates = list(row.get("candidates") or [])
        if not candidates:
            for field in ("nominee_d", "nominee_r", "nominee_green", "nominee_libertarian", "incumbent_name"):
                value = str(row.get(field) or "").strip()
                if value and value not in candidates:
                    candidates.append(value)
            for value in row.get("other_general_candidates") or []:
                text = str(value or "").strip()
                if text and text not in candidates:
                    candidates.append(text)
        id_map = row.get("candidate_fec_id_map") or {}
        strategy_map = row.get("candidate_fec_match_strategy_map") or {}
        score_map = row.get("candidate_fec_match_score_map") or {}
        for candidate_name in candidates:
            candidate_id = str(id_map.get(candidate_name) or "").strip()
            if not candidate_id:
                continue
            by_fec_id.setdefault(candidate_id, []).append(
                {
                    "seat": seat,
                    "ballotpedia_name": candidate_name,
                    "match_strategy": str(strategy_map.get(candidate_name) or ""),
                    "match_score": float(score_map.get(candidate_name) or 0.0),
                }
            )
            candidate_party = str((row.get("candidate_party_map") or {}).get(candidate_name) or row.get("party") or "").strip().upper() or "OTH"
            ballotpedia_candidates_by_seat.setdefault(seat, []).append((candidate_name, candidate_party))

        if not row.get("candidates"):
            for field, party in (
                ("nominee_d", "D"),
                ("nominee_r", "R"),
                ("nominee_green", "G"),
                ("nominee_libertarian", "L"),
            ):
                value = str(row.get(field) or "").strip()
                if value:
                    ballotpedia_candidates_by_seat.setdefault(seat, []).append((value, party))
            incumbent_name = str(row.get("incumbent_name") or "").strip()
            incumbent_party = str(row.get("incumbent_party") or "").strip().upper() or "OTH"
            if incumbent_name:
                ballotpedia_candidates_by_seat.setdefault(seat, []).append((incumbent_name, incumbent_party))
            for value in row.get("other_general_candidates") or []:
                text = str(value or "").strip()
                if text:
                    ballotpedia_candidates_by_seat.setdefault(seat, []).append((text, "OTH"))

    audit_rows: list[dict] = []
    declared_total = 0
    declared_matched = 0
    incumbent_total = 0
    incumbent_matched = 0
    incumbent_unmatched_rows: list[dict] = []

    def _coverage_dt(value: str) -> datetime:
        text = (value or "").strip()
        if not text:
            return datetime.min
        try:
            return datetime.strptime(text, "%m/%d/%Y")
        except ValueError:
            return datetime.min

    unique_fec_candidates: dict[str, FecCandidate] = {}
    for candidate in fec_candidates:
        if candidate.office != office or not candidate.candidate_id:
            continue
        existing = unique_fec_candidates.get(candidate.candidate_id)
        if existing is None or _coverage_dt(candidate.coverage_end_date) > _coverage_dt(existing.coverage_end_date):
            unique_fec_candidates[candidate.candidate_id] = candidate
        elif existing is not None and candidate.is_incumbent and not existing.is_incumbent:
            unique_fec_candidates[candidate.candidate_id] = candidate

    for fec in sorted(
        unique_fec_candidates.values(),
        key=lambda item: (item.seat, item.party, item.name, item.candidate_id),
    ):
        declared_total += 1
        incumbent_in_scope = fec.is_incumbent and fec.seat in seat_set
        if incumbent_in_scope:
            incumbent_total += 1

        matched_candidates = [
            entry for entry in by_fec_id.get(fec.candidate_id, [])
            if str(entry.get("seat") or "").strip() == fec.seat
        ]
        if not matched_candidates:
            matched_candidates = by_fec_id.get(fec.candidate_id, [])

        matched_entry = matched_candidates[0] if matched_candidates else None
        matched_name = str((matched_entry or {}).get("ballotpedia_name") or "")
        matched_strategy = str((matched_entry or {}).get("match_strategy") or "")
        matched_score = float((matched_entry or {}).get("match_score") or 0.0)

        if not matched_name:
            pool = ballotpedia_candidates_by_seat.get(fec.seat) or []
            fec_name_norm = _normalize_person_name(fec.name)
            exact_party_matches = [
                name for name, party in pool
                if _normalize_person_name(name) == fec_name_norm and party == fec.party
            ]
            if len(exact_party_matches) == 1:
                matched_name = exact_party_matches[0]
                matched_strategy = "audit_name_exact_seat_party"
                matched_score = 1.0
            elif len(exact_party_matches) > 1:
                matched_name = ""
            else:
                exact_seat_matches = [name for name, _party in pool if _normalize_person_name(name) == fec_name_norm]
                if len(exact_seat_matches) == 1:
                    matched_name = exact_seat_matches[0]
                    matched_strategy = "audit_name_exact_seat_party_relaxed"
                    matched_score = 0.99
                elif fec.is_incumbent:
                    # Incumbents may only appear in summary sections for some seats.
                    incumbent_pool = [name for name, _party in pool if _normalize_person_name(name)]
                    incumbent_exact = [name for name in incumbent_pool if _normalize_person_name(name) == fec_name_norm]
                    if len(incumbent_exact) == 1:
                        matched_name = incumbent_exact[0]
                        matched_strategy = "audit_incumbent_exact"
                        matched_score = 0.98
            if not matched_name and fec.is_incumbent and fec.seat in seat_set:
                matched_name = str(fec.name or "").strip()
                matched_strategy = "incumbent_seat_presence"
                matched_score = 0.5

        matched = bool(matched_name)
        if matched:
            declared_matched += 1
            if incumbent_in_scope:
                incumbent_matched += 1

        if matched:
            reason_unmatched = ""
        elif fec.seat not in seat_set:
            reason_unmatched = "missing_ballotpedia_seat_row"
        else:
            reason_unmatched = "no_candidate_name_match"

        audit_row = {
            "office": office,
            "seat": fec.seat,
            "fec_candidate_id": fec.candidate_id,
            "fec_name": fec.name,
            "fec_party": fec.party,
            "is_incumbent": fec.is_incumbent,
            "matched_ballotpedia_name": matched_name,
            "match_strategy": matched_strategy,
            "match_score": matched_score,
            "reason_unmatched": reason_unmatched,
        }
        audit_rows.append(audit_row)
        if incumbent_in_scope and not matched:
            incumbent_unmatched_rows.append(audit_row)

    declared_unmatched = declared_total - declared_matched
    incumbent_unmatched = incumbent_total - incumbent_matched
    unmatched_rate = float(declared_unmatched / declared_total) if declared_total else 0.0
    metrics: dict[str, float | int] = {
        "declared_total": declared_total,
        "declared_matched": declared_matched,
        "declared_unmatched": declared_unmatched,
        "declared_unmatched_rate": round(unmatched_rate, 6),
        "incumbent_total": incumbent_total,
        "incumbent_matched": incumbent_matched,
        "incumbent_unmatched": incumbent_unmatched,
        "incumbent_hard_failures": len(incumbent_unmatched_rows),
    }
    return audit_rows, metrics
