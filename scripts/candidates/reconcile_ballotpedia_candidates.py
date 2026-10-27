#!/usr/bin/env python3
"""Reconcile Ballotpedia candidate strings against canonical U.S. House candidates."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

PARTY_CODE_BY_BALLOTPEDIA_LABEL = {
    "democratic": "DEM",
    "democratic party": "DEM",
    "republican": "REP",
    "republican party": "REP",
    "independent": "IND",
    "libertarian": "LIB",
    "green": "GRE",
    "no political party": "NPA",
    "minor party": "OWN",
}

CHECKMARK_CHARACTERS = "✔✓✅☑"
PUNCTUATION_NOISE = re.compile(r"[^A-Z0-9' -]+")
MULTISPACE = re.compile(r"\s+")
PARTY_SUFFIX_PATTERN = re.compile(r"\(([^()]*)\)\s*$")
INCUMBENT_PATTERN = re.compile(r"\(\s*INCUMBENT\s*\)", re.IGNORECASE)

COMMON_NICKNAME_GROUPS = (
    ("BRAD", "BRADLEY"),
    ("DAVE", "DAVID"),
    ("ED", "EDWARD"),
    ("JEFF", "JEFFREY"),
    ("JIM", "JAMES"),
    ("JOE", "JOSEPH"),
    ("KAT", "KATHERINE"),
    ("SAM", "SAMUEL", "SAMMY"),
)
HONORIFIC_TOKENS = {
    "DR", "MR", "MRS", "MS", "MISS", "SEN", "SENATOR", "REP", "REPRESENTATIVE", "GOV", "GOVERNOR",
    "LT", "LTGOV", "MAYOR", "JUDGE", "REV",
}
NAME_SUFFIX_TOKENS = {"JR", "SR", "II", "III", "IV", "V"}


def build_nickname_lookup() -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for group in COMMON_NICKNAME_GROUPS:
        normalized = {token.upper() for token in group}
        for token in normalized:
            lookup.setdefault(token, set()).update(normalized)
    return lookup


NICKNAME_LOOKUP = build_nickname_lookup()


def normalize_ballotpedia_candidate_name(raw_name: str | None) -> str:
    if not raw_name:
        return ""

    cleaned = str(raw_name)
    cleaned = cleaned.translate({ord(char): " " for char in CHECKMARK_CHARACTERS})
    cleaned = INCUMBENT_PATTERN.sub(" ", cleaned)

    while True:
        match = PARTY_SUFFIX_PATTERN.search(cleaned)
        if not match:
            break
        label = MULTISPACE.sub(" ", match.group(1).strip()).lower()
        if label in PARTY_CODE_BY_BALLOTPEDIA_LABEL:
            cleaned = cleaned[:match.start()]
            continue
        break

    cleaned = cleaned.replace("•", " ")
    cleaned = PUNCTUATION_NOISE.sub(" ", cleaned.upper())
    cleaned = MULTISPACE.sub(" ", cleaned).strip(" -',.;:")
    return cleaned


def infer_ballotpedia_party_code(raw_name: str | None) -> str | None:
    if not raw_name:
        return None

    for label in re.findall(r"\(([^()]*)\)", str(raw_name)):
        normalized = MULTISPACE.sub(" ", label.strip()).lower()
        party_code = PARTY_CODE_BY_BALLOTPEDIA_LABEL.get(normalized)
        if party_code:
            return party_code
    return None




def normalize_person_tokens(raw_name: str | None) -> list[str]:
    normalized = normalize_ballotpedia_candidate_name(raw_name)
    return [token for token in normalized.split(" ") if token]


def strip_middle_initial_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) < 3:
        return list(tokens)
    return [token for index, token in enumerate(tokens) if not (0 < index < len(tokens) - 1 and len(token) == 1)]


def strip_middle_name_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) <= 2:
        return list(tokens)
    return [tokens[0], tokens[-1]]


def strip_honorific_tokens(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token not in HONORIFIC_TOKENS and token not in NAME_SUFFIX_TOKENS]


def first_name_matches_with_nickname(left: str, right: str) -> bool:
    if left == right:
        return True
    return right in NICKNAME_LOOKUP.get(left, set()) or left in NICKNAME_LOOKUP.get(right, set())


def names_match_with_alias_rules(left_name: str | None, right_name: str | None) -> bool:
    left_tokens = strip_honorific_tokens(strip_middle_initial_tokens(normalize_person_tokens(left_name)))
    right_tokens = strip_honorific_tokens(strip_middle_initial_tokens(normalize_person_tokens(right_name)))
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    if strip_middle_name_tokens(left_tokens) == strip_middle_name_tokens(right_tokens):
        return first_name_matches_with_nickname(left_tokens[0], right_tokens[0])
    if left_tokens[-1] != right_tokens[-1]:
        return False
    return first_name_matches_with_nickname(left_tokens[0], right_tokens[0]) and (not left_tokens[1:-1] or not right_tokens[1:-1] or set(left_tokens[1:-1]) == set(right_tokens[1:-1]))

def candidate_aliases(candidate: dict) -> list[str]:
    aliases = [candidate.get("name"), candidate.get("kalshiName")]
    aliases.extend(candidate.get("aliases") or [])
    return [alias for alias in aliases if alias]


def build_candidate_reference(candidate: dict) -> dict:
    return {
        "candidateId": candidate.get("candidateId"),
        "name": candidate.get("name"),
        "kalshiName": candidate.get("kalshiName"),
        "aliases": candidate.get("aliases") or [],
        "partyCode": candidate.get("partyCode"),
        "seatId": candidate.get("seatId"),
        "incumbentStatus": candidate.get("incumbentStatus"),
    }


def _last_name(value: str) -> str:
    parts = [part for part in value.split(" ") if part]
    return parts[-1] if parts else ""


def _first_initial(value: str) -> str:
    parts = [part for part in value.split(" ") if part]
    return parts[0][:1] if parts else ""


def _fuzzy_score(source_name: str, candidate_name: str) -> float:
    return SequenceMatcher(None, source_name, candidate_name).ratio()


def reconcile_ballotpedia_candidate(
    source_name: str,
    canonical_candidates: Iterable[dict],
    seat_id: str,
) -> dict:
    normalized_source_name = normalize_ballotpedia_candidate_name(source_name)
    likely_party = infer_ballotpedia_party_code(source_name)
    candidates = [candidate for candidate in canonical_candidates if candidate.get("seatId") == seat_id]

    exact_match = next(
        (
            candidate
            for candidate in candidates
            if normalize_ballotpedia_candidate_name(candidate.get("name")) == normalized_source_name
        ),
        None,
    )
    if exact_match:
        return {
            "sourceName": source_name,
            "normalizedSourceName": normalized_source_name,
            "likelyPartyCode": likely_party,
            "matchStrategy": "exact_name",
            "matchedCandidate": build_candidate_reference(exact_match),
            "unmatchedSourceName": None,
            "confidence": "high",
        }

    alias_match = next(
        (
            candidate
            for candidate in candidates
            for alias in candidate_aliases(candidate)
            if names_match_with_alias_rules(alias, source_name)
        ),
        None,
    )
    if alias_match:
        return {
            "sourceName": source_name,
            "normalizedSourceName": normalized_source_name,
            "likelyPartyCode": likely_party,
            "matchStrategy": "alias",
            "matchedCandidate": build_candidate_reference(alias_match),
            "unmatchedSourceName": None,
            "confidence": "high",
        }

    fuzzy_pool = [candidate for candidate in candidates if not likely_party or candidate.get("partyCode") == likely_party]
    scored_candidates: list[tuple[float, dict]] = []
    for candidate in fuzzy_pool:
        candidate_name = normalize_ballotpedia_candidate_name(candidate.get("name"))
        if _last_name(candidate_name) != _last_name(normalized_source_name):
            continue
        if _first_initial(candidate_name) != _first_initial(normalized_source_name):
            continue
        score = max(
            _fuzzy_score(normalized_source_name, normalize_ballotpedia_candidate_name(alias))
            for alias in candidate_aliases(candidate)
        )
        if score >= 0.88:
            scored_candidates.append((score, candidate))

    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    if scored_candidates:
        best_score, best_candidate = scored_candidates[0]
        runner_up_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0
        if best_score >= 0.92 and (best_score - runner_up_score) >= 0.03:
            return {
                "sourceName": source_name,
                "normalizedSourceName": normalized_source_name,
                "likelyPartyCode": likely_party,
                "matchStrategy": "fuzzy_seat_party",
                "matchedCandidate": build_candidate_reference(best_candidate),
                "unmatchedSourceName": None,
                "confidence": "medium",
            }

    return {
        "sourceName": source_name,
        "normalizedSourceName": normalized_source_name,
        "likelyPartyCode": likely_party,
        "matchStrategy": None,
        "matchedCandidate": None,
        "unmatchedSourceName": source_name,
        "confidence": "low",
    }


def reconcile_ballotpedia_candidates_by_seat(
    ballotpedia_candidates_by_seat: dict[str, list[str]],
    canonical_candidates_by_seat: dict[str, list[dict]],
) -> dict[str, dict]:
    reconciliation: dict[str, dict] = {}
    for seat_id, source_names in ballotpedia_candidates_by_seat.items():
        canonical_candidates = canonical_candidates_by_seat.get(seat_id, [])
        reconciled = [
            reconcile_ballotpedia_candidate(source_name, canonical_candidates, seat_id)
            for source_name in source_names
        ]
        has_unmatched = any(item["matchedCandidate"] is None for item in reconciled)
        reconciliation[seat_id] = {
            "seatId": seat_id,
            "confidence": "low" if has_unmatched else "high",
            "needsReview": has_unmatched,
            "pruningEnabled": False,
            "sourceCandidates": reconciled,
        }
    return reconciliation
