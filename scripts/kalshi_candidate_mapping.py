"""Shared candidate-level Kalshi -> Ballotpedia name mapping exports."""
from __future__ import annotations

import csv
import difflib
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

UNRESOLVED_ODDS_THRESHOLD = 2.0
SIMILARITY_TIER_A = 0.93
SIMILARITY_TIER_B = 0.88
SIMILARITY_TIER_C = 0.80
NAME_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}
NICKNAME_TO_FORMAL = {
    "ALEX": "ALEXANDER",
    "ANDY": "ANDREW",
    "BEN": "BENJAMIN",
    "BETH": "ELIZABETH",
    "BILL": "WILLIAM",
    "BOB": "ROBERT",
    "CHRIS": "CHRISTOPHER",
    "DAN": "DANIEL",
    "DAVE": "DAVID",
    "DICK": "RICHARD",
    "ED": "EDWARD",
    "JACK": "JOHN",
    "JIM": "JAMES",
    "JOE": "JOSEPH",
    "JON": "JONATHAN",
    "KATE": "KATHERINE",
    "KATIE": "KATHERINE",
    "LIZ": "ELIZABETH",
    "MATT": "MATTHEW",
    "MIKE": "MICHAEL",
    "PAT": "PATRICK",
    "RICK": "RICHARD",
    "SAM": "SAMUEL",
    "SUE": "SUSAN",
    "TOM": "THOMAS",
}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE_OVERRIDE_FILE = REPO_ROOT / "apps" / "web" / "data" / "kalshi-candidate-match-overrides.json"


def normalize_name(value: str | None) -> str:
    text = html.unescape(str(value or "")).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper()
    if not text:
        return ""
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_house_seat(value: str | None) -> str:
    text = str(value or "").strip().upper()
    match = re.match(r"^([A-Z]{2})-(AL|\d{1,2})$", text)
    if not match:
        return text
    state, district = match.groups()
    if district == "AL":
        return f"{state}-AL"
    return f"{state}-{int(district):02d}"


def _normalize_senate_seat(value: str | None) -> str:
    return str(value or "").strip().upper()


def _normalize_party(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"D", "DEM", "DEMOCRATIC", "DEMOCRAT"}:
        return "D"
    if text in {"R", "REP", "REPUBLICAN", "GOP"}:
        return "R"
    if text in {"G", "GRE", "GREEN"}:
        return "G"
    if text in {"L", "LIB", "LIBERTARIAN"}:
        return "L"
    return text or "OTH"


def _parse_json_array(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    return []


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class BallotpediaCandidate:
    seat: str
    round_name: str
    party: str
    name: str
    source: str
    normalized: str


def load_candidate_match_override_registry(path: Path = DEFAULT_CANDIDATE_OVERRIDE_FILE) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    records = payload.get("overrides") if isinstance(payload, dict) else []
    registry: dict[str, dict[str, Any]] = {}
    if not isinstance(records, list):
        return {}
    for row in records:
        if not isinstance(row, dict):
            continue
        key = _override_key(
            office=row.get("office"),
            cycle_year=row.get("cycle_year"),
            seat=row.get("seat"),
            round_name=row.get("round"),
            party=row.get("party"),
            kalshi_name=row.get("kalshi_candidate_name"),
        )
        if not key:
            continue
        registry[key] = dict(row)
    return registry


def _override_key(
    *,
    office: Any,
    cycle_year: Any,
    seat: Any,
    round_name: Any,
    party: Any,
    kalshi_name: Any,
) -> str:
    office_text = str(office or "").strip().lower()
    cycle_text = str(cycle_year or "").strip()
    seat_text = str(seat or "").strip().upper()
    round_text = str(round_name or "").strip().lower()
    party_text = _normalize_party(party)
    kalshi_text = normalize_name(kalshi_name)
    if not (office_text and cycle_text and seat_text and round_text and kalshi_text):
        return ""
    return "|".join([office_text, cycle_text, seat_text, round_text, party_text, kalshi_text])


def build_ballotpedia_candidate_pool(
    *,
    office: str,
    primary_csv: Path,
    runoff_csv: Path,
    general_csv: Path,
) -> dict[str, list[BallotpediaCandidate]]:
    seat_norm = _normalize_senate_seat if office == "us_senate" else _normalize_house_seat
    by_key: dict[str, list[BallotpediaCandidate]] = {}

    def add(seat: str, round_name: str, party: str, name: str, source: str) -> None:
        name_text = str(name or "").strip()
        if not name_text:
            return
        seat_text = seat_norm(seat)
        party_text = _normalize_party(party)
        item = BallotpediaCandidate(
            seat=seat_text,
            round_name=round_name,
            party=party_text,
            name=name_text,
            source=source,
            normalized=normalize_name(name_text),
        )
        key = f"{seat_text}|{round_name}|{party_text}"
        by_key.setdefault(key, []).append(item)

    for row in _load_csv_rows(primary_csv):
        seat = str(row.get("seat") or "")
        party = str(row.get("party") or "")
        for name in _parse_json_array(row.get("candidates")):
            add(seat, "primary", party, name, "primary")

    for row in _load_csv_rows(runoff_csv):
        seat = str(row.get("seat") or "")
        party = str(row.get("party") or "")
        for name in _parse_json_array(row.get("candidates")):
            add(seat, "runoff", party, name, "runoff")

    for row in _load_csv_rows(general_csv):
        seat = str(row.get("seat") or "")
        nominee_fields = (
            ("nominee_d", "D"),
            ("nominee_r", "R"),
            ("nominee_green", "G"),
            ("nominee_libertarian", "L"),
        )
        for field, party in nominee_fields:
            add(seat, "general", party, str(row.get(field) or ""), "general_nominee")
        for name in _parse_json_array(row.get("other_general_candidates")):
            add(seat, "general", "OTH", name, "general_other")

    for key, values in by_key.items():
        unique: dict[str, BallotpediaCandidate] = {}
        for value in values:
            unique[f"{value.normalized}|{value.source}"] = value
        by_key[key] = sorted(unique.values(), key=lambda item: (item.name, item.source))
    return by_key


def _candidate_similarity(left: str, right: str) -> float:
    left_tokens = set(token for token in left.split() if token)
    right_tokens = set(token for token in right.split() if token)
    if not left_tokens or not right_tokens:
        return 0.0
    left_parts = _name_parts(left)
    right_parts = _name_parts(right)
    if left_parts and right_parts:
        if left_parts[-1] == right_parts[-1]:
            left_first = left_parts[0]
            right_first = right_parts[0]
            if _first_name_compatible(left_first, right_first):
                return 0.96
            if left_first and right_first and left_first[0] == right_first[0]:
                return 0.9
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    token_score = float(overlap / union) if union else 0.0
    sequence_score = difflib.SequenceMatcher(None, left, right).ratio()
    return max(token_score, sequence_score)


def _canonical_first_name(token: str) -> str:
    text = str(token or "").strip().upper()
    if not text:
        return ""
    return NICKNAME_TO_FORMAL.get(text, text)


def _name_parts(value: str) -> list[str]:
    tokens = [token for token in normalize_name(value).split(" ") if token]
    return [token for token in tokens if token not in NAME_SUFFIXES]


def _first_name_compatible(left: str, right: str) -> bool:
    left_canon = _canonical_first_name(left)
    right_canon = _canonical_first_name(right)
    if not left_canon or not right_canon:
        return False
    if left_canon == right_canon:
        return True
    if len(left_canon) >= 3 and len(right_canon) >= 3:
        if left_canon.startswith(right_canon) or right_canon.startswith(left_canon):
            return True
    return False


def _normalized_signature(name: str) -> str:
    parts = _name_parts(name)
    if not parts:
        return ""
    if len(parts) >= 3:
        core = [parts[0]] + [token for token in parts[1:-1] if len(token) > 1] + [parts[-1]]
    else:
        core = list(parts)
    core[0] = _canonical_first_name(core[0])
    return " ".join(core)


def _name_parts_for_compare(value: str) -> list[str]:
    return [token for token in normalize_name(value).split() if token]


def _is_punctuation_or_diacritic_delta(left: str, right: str) -> bool:
    def compact(value: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "", normalize_name(value))

    left_compact = compact(left)
    right_compact = compact(right)
    if not left_compact or not right_compact:
        return False
    return left_compact == right_compact


def _top_candidate_suggestions(
    *,
    kalshi_name: str,
    candidates: list[BallotpediaCandidate],
    limit: int = 3,
) -> list[dict[str, Any]]:
    kalshi_norm = normalize_name(kalshi_name)
    scored: list[tuple[float, BallotpediaCandidate]] = []
    for candidate in candidates:
        score = round(_candidate_similarity(kalshi_norm, candidate.normalized), 4)
        scored.append((score, candidate))
    scored.sort(key=lambda row: (-row[0], row[1].name))
    return [
        {
            "candidate_name": item.name,
            "source": item.source,
            "score": score,
        }
        for score, item in scored[:limit]
    ]


def match_ballotpedia_candidate(
    *,
    kalshi_name: str,
    seat: str,
    round_name: str,
    party: str,
    pool_by_key: dict[str, list[BallotpediaCandidate]],
) -> dict[str, Any]:
    round_text = str(round_name or "").strip().lower()
    party_text = _normalize_party(party)
    seat_text = str(seat or "").strip().upper()
    candidate_key = f"{seat_text}|{round_text}|{party_text}"
    candidates = list(pool_by_key.get(candidate_key) or [])

    if not candidates:
        fallback: list[BallotpediaCandidate] = []
        prefix = f"{seat_text}|{round_text}|"
        for key, values in pool_by_key.items():
            if key.startswith(prefix):
                fallback.extend(values)
        candidates = fallback
        candidate_key = f"{seat_text}|{round_text}|ANY"

    if not candidates:
        # Some Senate general pages omit nominee fields. Fall back to seat-wide candidate pool.
        seat_fallback: list[BallotpediaCandidate] = []
        seat_prefix = f"{seat_text}|"
        for key, values in pool_by_key.items():
            if key.startswith(seat_prefix):
                seat_fallback.extend(values)
        candidates = seat_fallback
        candidate_key = f"{seat_text}|ANY|ANY"

    kalshi_norm = normalize_name(kalshi_name)
    kalshi_signature = _normalized_signature(kalshi_name)
    review_recommendation = "pending"
    if not kalshi_norm:
        return {
            "ballotpedia_candidate_name": "",
            "ballotpedia_match_status": "unmatched",
            "ballotpedia_match_strategy": "blank_kalshi_name",
            "ballotpedia_match_score": 0.0,
            "ballotpedia_match_source": "",
            "ballotpedia_candidate_pool_key": candidate_key,
            "match_confidence_tier": "D",
            "match_reason_code": "blank_kalshi_name",
            "review_status": "pending",
            "review_recommendation": "pending",
            "top_candidate_suggestions": [],
        }

    if not candidates:
        return {
            "ballotpedia_candidate_name": "",
            "ballotpedia_match_status": "unmatched",
            "ballotpedia_match_strategy": "no_match",
            "ballotpedia_match_score": 0.0,
            "ballotpedia_match_source": "",
            "ballotpedia_candidate_pool_key": candidate_key,
            "match_confidence_tier": "D",
            "match_reason_code": "no_pool_for_seat",
            "review_status": "pending",
            "review_recommendation": "needs_source_update",
            "top_candidate_suggestions": [],
        }

    exact = [item for item in candidates if item.normalized == kalshi_norm]
    if not exact and kalshi_signature:
        exact = [item for item in candidates if _normalized_signature(item.name) == kalshi_signature]
    if len(exact) == 1:
        matched = exact[0]
        reason = "signature_match" if matched.normalized != kalshi_norm else "exact_normalized"
        return {
            "ballotpedia_candidate_name": matched.name,
            "ballotpedia_match_status": "matched",
            "ballotpedia_match_strategy": "exact_normalized_signature" if matched.normalized != kalshi_norm else "exact_normalized",
            "ballotpedia_match_score": 1.0,
            "ballotpedia_match_source": matched.source,
            "ballotpedia_candidate_pool_key": candidate_key,
            "match_confidence_tier": "A",
            "match_reason_code": reason,
            "review_status": "not_required",
            "review_recommendation": "not_required",
            "top_candidate_suggestions": [],
        }
    if len(exact) > 1:
        return {
            "ballotpedia_candidate_name": "",
            "ballotpedia_match_status": "ambiguous",
            "ballotpedia_match_strategy": "exact_ambiguous",
            "ballotpedia_match_score": 1.0,
            "ballotpedia_match_source": "",
            "ballotpedia_candidate_pool_key": candidate_key,
            "match_confidence_tier": "C",
            "match_reason_code": "ambiguous_top_score",
            "review_status": "pending",
            "review_recommendation": review_recommendation,
            "top_candidate_suggestions": _top_candidate_suggestions(kalshi_name=kalshi_name, candidates=exact),
        }

    scored = [(round(_candidate_similarity(kalshi_norm, item.normalized), 4), item) for item in candidates]
    scored = [item for item in scored if item[0] >= SIMILARITY_TIER_C]
    if not scored:
        has_last_name_overlap = False
        kalshi_parts = _name_parts_for_compare(kalshi_name)
        kalshi_last = kalshi_parts[-1] if kalshi_parts else ""
        if kalshi_last:
            has_last_name_overlap = any((_name_parts_for_compare(item.name)[-1:] == [kalshi_last]) for item in candidates)
        return {
            "ballotpedia_candidate_name": "",
            "ballotpedia_match_status": "unmatched",
            "ballotpedia_match_strategy": "no_match",
            "ballotpedia_match_score": 0.0,
            "ballotpedia_match_source": "",
            "ballotpedia_candidate_pool_key": candidate_key,
            "match_confidence_tier": "D",
            "match_reason_code": "last_name_only_conflict" if has_last_name_overlap else "no_candidate_above_threshold",
            "review_status": "pending",
            "review_recommendation": review_recommendation,
            "top_candidate_suggestions": _top_candidate_suggestions(kalshi_name=kalshi_name, candidates=candidates),
        }
    scored.sort(key=lambda row: (-row[0], row[1].name))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return {
            "ballotpedia_candidate_name": "",
            "ballotpedia_match_status": "ambiguous",
            "ballotpedia_match_strategy": "fuzzy_ambiguous",
            "ballotpedia_match_score": scored[0][0],
            "ballotpedia_match_source": "",
            "ballotpedia_candidate_pool_key": candidate_key,
            "match_confidence_tier": "C",
            "match_reason_code": "ambiguous_top_score",
            "review_status": "pending",
            "review_recommendation": review_recommendation,
            "top_candidate_suggestions": _top_candidate_suggestions(
                kalshi_name=kalshi_name,
                candidates=[scored[0][1], scored[1][1]],
            ),
        }
    score, matched = scored[0]
    kalshi_last = _name_parts_for_compare(kalshi_name)[-1:] or [""]
    matched_last = _name_parts_for_compare(matched.name)[-1:] or [""]
    same_last = kalshi_last[0] and kalshi_last[0] == matched_last[0]
    first_parts = _name_parts_for_compare(kalshi_name)
    matched_first_parts = _name_parts_for_compare(matched.name)
    first_compatible = bool(first_parts and matched_first_parts and _first_name_compatible(first_parts[0], matched_first_parts[0]))
    punctuation_only = _is_punctuation_or_diacritic_delta(kalshi_name, matched.name)

    if score >= SIMILARITY_TIER_A:
        tier = "A"
        reason = "near_typo"
        review_status = "not_required"
    elif score >= SIMILARITY_TIER_B and ((same_last and first_compatible) or punctuation_only):
        tier = "B"
        reason = "conditional_high_similarity"
        review_status = "not_required"
    elif score >= SIMILARITY_TIER_C:
        tier = "C"
        reason = "review_similarity_band"
        review_status = "pending"
    else:
        tier = "D"
        reason = "no_candidate_above_threshold"
        review_status = "pending"

    if same_last and not first_compatible and tier in {"A", "B"}:
        tier = "C"
        reason = "last_name_only_conflict"
        review_status = "pending"

    if tier in {"C", "D"}:
        return {
            "ballotpedia_candidate_name": matched.name if tier == "C" else "",
            "ballotpedia_match_status": "ambiguous" if tier == "C" else "unmatched",
            "ballotpedia_match_strategy": "review_required",
            "ballotpedia_match_score": score,
            "ballotpedia_match_source": matched.source if tier == "C" else "",
            "ballotpedia_candidate_pool_key": candidate_key,
            "match_confidence_tier": tier,
            "match_reason_code": reason,
            "review_status": review_status,
            "review_recommendation": review_recommendation,
            "top_candidate_suggestions": _top_candidate_suggestions(kalshi_name=kalshi_name, candidates=candidates),
        }

    return {
        "ballotpedia_candidate_name": matched.name,
        "ballotpedia_match_status": "matched",
        "ballotpedia_match_strategy": "token_fuzzy",
        "ballotpedia_match_score": score,
        "ballotpedia_match_source": matched.source,
        "ballotpedia_candidate_pool_key": candidate_key,
        "match_confidence_tier": tier,
        "match_reason_code": reason,
        "review_status": review_status,
        "review_recommendation": "not_required",
        "top_candidate_suggestions": [],
    }


def build_candidate_market_rows(
    *,
    contests: list[dict[str, Any]],
    office: str,
    market_type_field: str,
    market_type_value: str,
    seat_field: str,
    party_field: str,
    ballotpedia_primary_csv: Path,
    ballotpedia_runoff_csv: Path,
    ballotpedia_general_csv: Path,
    match_override_registry: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    pool = build_ballotpedia_candidate_pool(
        office=office,
        primary_csv=ballotpedia_primary_csv,
        runoff_csv=ballotpedia_runoff_csv,
        general_csv=ballotpedia_general_csv,
    )
    seat_norm = _normalize_senate_seat if office == "us_senate" else _normalize_house_seat
    rows: list[dict[str, Any]] = []
    overrides = match_override_registry or load_candidate_match_override_registry()
    for contest in contests:
        if str(contest.get(market_type_field) or "").strip().lower() != market_type_value:
            continue
        round_name = str(contest.get("round") or "").strip().lower()
        seat = seat_norm(str(contest.get(seat_field) or ""))
        party = str(contest.get(party_field) or "")
        for market in contest.get("markets") or []:
            ticker = str(market.get("marketTicker") or "").strip()
            if not ticker:
                continue
            kalshi_name = str(market.get("entityName") or "").strip()
            match = match_ballotpedia_candidate(
                kalshi_name=kalshi_name,
                seat=seat,
                round_name=round_name,
                party=party,
                pool_by_key=pool,
            )
            override_key = _override_key(
                office=office,
                cycle_year=contest.get("cycle_year"),
                seat=seat,
                round_name=round_name,
                party=party,
                kalshi_name=kalshi_name,
            )
            override = overrides.get(override_key or "")
            if not override:
                wildcard_key = _override_key(
                    office=office,
                    cycle_year="*",
                    seat=seat,
                    round_name=round_name,
                    party=party,
                    kalshi_name=kalshi_name,
                )
                override = overrides.get(wildcard_key or "")
            if override:
                override_action = str(override.get("action") or "match").strip().lower()
                override_name = str(override.get("ballotpedia_candidate_name") or "").strip()
                override_status = str(override.get("review_status") or "accepted").strip().lower()
                if override_action == "waive":
                    waiver_reason = str(override.get("waiver_reason") or "source_data_issue").strip() or "source_data_issue"
                    match.update(
                        {
                            "ballotpedia_candidate_name": "",
                            "ballotpedia_match_status": "unmatched",
                            "ballotpedia_match_strategy": "override_waive",
                            "ballotpedia_match_score": 0.0,
                            "ballotpedia_match_source": str(override.get("source") or "override"),
                            "match_confidence_tier": "D",
                            "match_reason_code": "waived_unresolved",
                            "review_status": "waived",
                            "review_recommendation": waiver_reason,
                            "waiver_reason": waiver_reason,
                        }
                    )
                elif override_name:
                    match.update(
                        {
                            "ballotpedia_candidate_name": override_name,
                            "ballotpedia_match_status": "matched",
                            "ballotpedia_match_strategy": "override",
                            "ballotpedia_match_score": 1.0,
                            "ballotpedia_match_source": str(override.get("source") or "override"),
                            "match_confidence_tier": "A",
                            "match_reason_code": "override_match",
                            "review_status": "accepted" if override_status == "accepted" else override_status,
                            "review_recommendation": "not_required",
                            "top_candidate_suggestions": [],
                        }
                    )
            rows.append(
                {
                    "office": office,
                    "contest_id": contest.get("contest_id"),
                    "cycle_year": contest.get("cycle_year"),
                    "state": contest.get("state"),
                    "seat": seat,
                    "round": round_name,
                    "party": party or "",
                    "market_type": market_type_value,
                    "market_ticker": ticker,
                    "event_ticker": market.get("eventTicker"),
                    "series_ticker": market.get("seriesTicker"),
                    "status": market.get("status"),
                    "oddsPercent": market.get("oddsPercent"),
                    "source_file": market.get("sourceFile"),
                    "kalshi_candidate_name": kalshi_name,
                    "candidate_name_kalshi": kalshi_name,
                    "candidate_name_ballotpedia": match.get("ballotpedia_candidate_name"),
                    **match,
                }
            )
    rows.sort(
        key=lambda item: (
            str(item.get("seat") or ""),
            str(item.get("round") or ""),
            str(item.get("party") or ""),
            str(item.get("kalshi_candidate_name") or ""),
            str(item.get("market_ticker") or ""),
        )
    )
    return rows


def build_candidate_match_report(
    rows: list[dict[str, Any]],
    *,
    office: str,
    market_type: str,
    unresolved_odds_threshold: float = UNRESOLVED_ODDS_THRESHOLD,
) -> dict[str, Any]:
    def _odds_value(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    status_counts = {"matched": 0, "unmatched": 0, "ambiguous": 0}
    status_counts_positive = {"matched": 0, "unmatched": 0, "ambiguous": 0}
    status_counts_threshold = {"matched": 0, "unmatched": 0, "ambiguous": 0}
    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    tier_counts_threshold = {"A": 0, "B": 0, "C": 0, "D": 0}
    unresolved_by_seat: dict[str, int] = {}
    unresolved_examples: list[dict[str, Any]] = []
    waived_examples: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("ballotpedia_match_status") or "unmatched")
        tier = str(row.get("match_confidence_tier") or "").strip().upper()
        review_status = str(row.get("review_status") or "").strip().lower()
        if tier not in tier_counts:
            tier = "D"
        odds = row.get("oddsPercent")
        try:
            odds_value = float(odds)
        except (TypeError, ValueError):
            odds_value = 0.0
        if status not in status_counts:
            status = "unmatched"
        status_counts[status] += 1
        tier_counts[tier] += 1
        if odds_value > 0:
            status_counts_positive[status] += 1
        if odds_value > unresolved_odds_threshold:
            status_counts_threshold[status] += 1
            tier_counts_threshold[tier] += 1
        if tier in {"C", "D"}:
            review_queue.append(
                {
                    "market_ticker": row.get("market_ticker"),
                    "seat": row.get("seat"),
                    "round": row.get("round"),
                    "party": row.get("party"),
                    "oddsPercent": row.get("oddsPercent"),
                    "kalshi_candidate_name": row.get("kalshi_candidate_name"),
                    "ballotpedia_candidate_name": row.get("ballotpedia_candidate_name"),
                    "match_confidence_tier": tier,
                    "match_reason_code": row.get("match_reason_code"),
                    "review_status": row.get("review_status"),
                    "review_recommendation": row.get("review_recommendation"),
                    "top_candidate_suggestions": row.get("top_candidate_suggestions"),
                }
            )
        if status != "matched" and odds_value > unresolved_odds_threshold:
            seat = str(row.get("seat") or "")
            unresolved_payload = {
                "market_ticker": row.get("market_ticker"),
                "seat": row.get("seat"),
                "round": row.get("round"),
                "party": row.get("party"),
                "oddsPercent": row.get("oddsPercent"),
                "kalshi_candidate_name": row.get("kalshi_candidate_name"),
                "ballotpedia_match_status": status,
                "ballotpedia_match_strategy": row.get("ballotpedia_match_strategy"),
                "ballotpedia_candidate_pool_key": row.get("ballotpedia_candidate_pool_key"),
                "match_confidence_tier": tier,
                "match_reason_code": row.get("match_reason_code"),
                "review_status": row.get("review_status"),
                "review_recommendation": row.get("review_recommendation"),
                "top_candidate_suggestions": row.get("top_candidate_suggestions"),
                "waiver_reason": row.get("waiver_reason"),
            }
            if review_status == "waived":
                waived_examples.append(unresolved_payload)
            else:
                unresolved_by_seat[seat] = int(unresolved_by_seat.get(seat) or 0) + 1
                unresolved_examples.append(unresolved_payload)
    unresolved_examples.sort(
        key=lambda item: (
            -_odds_value(item.get("oddsPercent")),
            str(item.get("seat") or ""),
            str(item.get("kalshi_candidate_name") or ""),
        )
    )
    review_queue.sort(
        key=lambda item: (
            -_odds_value(item.get("oddsPercent")),
            str(item.get("seat") or ""),
            str(item.get("kalshi_candidate_name") or ""),
        )
    )
    blocking_candidates = [
        item
        for item in unresolved_examples
        if str(item.get("match_confidence_tier") or "") in {"C", "D"}
    ]
    return {
        "office": office,
        "market_type": market_type,
        "row_count": len(rows),
        "matched_count": status_counts["matched"],
        "unmatched_count": status_counts["unmatched"],
        "ambiguous_count": status_counts["ambiguous"],
        "positive_odds_matched_count": status_counts_positive["matched"],
        "positive_odds_unmatched_count": status_counts_positive["unmatched"],
        "positive_odds_ambiguous_count": status_counts_positive["ambiguous"],
        "tier_counts": tier_counts,
        "threshold_tier_counts": tier_counts_threshold,
        "unresolved_odds_threshold": unresolved_odds_threshold,
        "threshold_odds_matched_count": status_counts_threshold["matched"],
        "threshold_odds_unmatched_count": status_counts_threshold["unmatched"],
        "threshold_odds_ambiguous_count": status_counts_threshold["ambiguous"],
        "threshold_unresolved_count": status_counts_threshold["unmatched"] + status_counts_threshold["ambiguous"],
        "below_threshold_unresolved_count": (status_counts["unmatched"] + status_counts["ambiguous"])
        - (status_counts_threshold["unmatched"] + status_counts_threshold["ambiguous"]),
        "blocking_issue_count": len(blocking_candidates),
        "waived_issue_count": len(waived_examples),
        "ambiguous_auto_match_issue_count": sum(1 for item in unresolved_examples if str(item.get("match_confidence_tier") or "") in {"A", "B"} and str(item.get("ballotpedia_match_status") or "") == "ambiguous"),
        "per_seat_unresolved_counts": dict(sorted(unresolved_by_seat.items(), key=lambda row: (-row[1], row[0]))),
        "unresolved_examples": unresolved_examples[:200],
        "waived_examples": waived_examples[:200],
        "review_queue": review_queue[:1000],
    }
