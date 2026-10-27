from __future__ import annotations

from dataclasses import dataclass, replace
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from house_seat_parsing import STATE_CODES, STATE_NAMES, build_primary_nomination_key, infer_us_house_parsing


def build_kalshi_event_url(
    series_ticker: str | None,
    series_title: str | None,
    event_ticker: str | None,
) -> str | None:
    """Construct the canonical Kalshi web URL for an election event.

    Pattern: https://kalshi.com/markets/{series}/{title-slug}/{event}
    """
    if not series_ticker or not series_title or not event_ticker:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", series_title.lower().replace("?", "").strip()).strip("-")
    return f"https://kalshi.com/markets/{series_ticker.lower()}/{slug}/{event_ticker.lower()}"



@dataclass(frozen=True)
class KalshiPrimaryElection:
    parent_series_ticker: str | None
    event_ticker: str
    cycle_year: int | None
    state_code: str | None
    seat_id: str | None
    office_family: str | None
    party: str | None
    normalized_contest_key: str | None
    election_kind: str
    election_label: str
    parent_series_title: str | None = None
    settlement_source_names: tuple[str, ...] = ()


_PARTY_LABELS = {"D": "Democratic", "R": "Republican"}


def build_statewide_seat_id(*, state_code: str | None, office_family: str | None) -> str | None:
    if not state_code or not office_family or office_family in {"US-REP", "Statewide"}:
        return None
    if office_family == "US-SEN":
        return f"{state_code}-SEN"
    return f"{state_code}-{office_family}"


def build_normalized_contest_key(*, office_family: str | None, state_code: str | None, district_code: str | None, is_at_large: bool, cycle_year: int | None, party: str | None) -> str | None:
    seat_id = None
    if office_family == "US-REP":
        if state_code and is_at_large:
            seat_id = f"{state_code}-AL"
        elif state_code and district_code:
            seat_id = f"{state_code}-{district_code}"
    else:
        seat_id = build_statewide_seat_id(state_code=state_code, office_family=office_family)
    return build_primary_nomination_key(office_family=office_family or "", seat_id=seat_id, cycle_year=cycle_year, party=party)


def _normalize_party_label(value: str | None) -> str | None:
    if not value:
        return None
    upper = str(value).strip().upper()
    if upper.startswith("D"):
        return "D"
    if upper.startswith("R") or upper.startswith("GOP"):
        return "R"
    return None


def _extract_cycle_year(upper: str) -> int | None:
    for pattern in (re.compile(r"[DR](\d{2})(?:-|$)"), re.compile(r"-(\d{2})(?:-|$)"), re.compile(r"\b(20\d{2})\b")):
        match = pattern.search(upper)
        if match:
            value = match.group(1)
            return int(value) if len(value) == 4 else 2000 + int(value)
    return None


def parse_primary_election_event(*, event_ticker: str, parent_series_ticker: str = "", parent_series_title: str = "", settlement_source_names: list[str] | tuple[str, ...] | None = None) -> KalshiPrimaryElection | None:
    normalized_event_ticker = str(event_ticker or "").strip().upper()
    if not normalized_event_ticker:
        return None

    parsed = parse_kalshi_election_metadata(
        event_ticker=normalized_event_ticker,
        series_ticker=str(parent_series_ticker or "").strip(),
        series_title=str(parent_series_title or "").strip(),
        settlement_source_names=[str(name) for name in (settlement_source_names or []) if str(name).strip()],
    )

    combined = " ".join(
        part
        for part in (
            normalized_event_ticker,
            str(parent_series_ticker or "").upper(),
            str(parent_series_title or "").upper(),
            " ".join(str(name).upper() for name in (settlement_source_names or []) if str(name).strip()),
        )
        if part
    )
    election_kind = "primary" if any(token in combined for token in ("PRIMARY", "NOMINEE", "NOM")) else "general"
    if election_kind != "primary":
        return None

    party = parsed.party
    if not party:
        for source_name in settlement_source_names or []:
            party = _normalize_party_label(str(source_name))
            if party:
                break

    cycle_year = parsed.cycle_year or _extract_cycle_year(normalized_event_ticker)
    office_family = parsed.office_family
    if office_family == "Statewide":
        office_family = infer_statewide_office_code(normalized_event_ticker, parent_series_ticker, parent_series_title, *(settlement_source_names or [])) or office_family

    parent_series_ticker_value = str(parent_series_ticker or "").strip() or None
    parent_series_title_value = str(parent_series_title or "").strip() or None
    party_label = _PARTY_LABELS.get(party, "Other")
    office_label = office_family or "Election"
    election_label_parts = [str(cycle_year) if cycle_year else "Unknown", office_label]
    if parsed.seat_id:
        election_label_parts.append(parsed.seat_id)
    election_label_parts.append(f"{party_label} primary")

    normalized_contest_key = parsed.normalized_contest_key or build_normalized_contest_key(
        office_family=office_family,
        state_code=parsed.state_code,
        district_code=parsed.district_code,
        is_at_large=parsed.is_at_large,
        cycle_year=cycle_year,
        party=party,
    )

    return KalshiPrimaryElection(
        parent_series_ticker=parent_series_ticker_value,
        event_ticker=normalized_event_ticker,
        cycle_year=cycle_year,
        state_code=parsed.state_code,
        seat_id=parsed.seat_id,
        office_family=office_family,
        party=party,
        normalized_contest_key=normalized_contest_key,
        election_kind=election_kind,
        election_label=" | ".join(election_label_parts),
        parent_series_title=parent_series_title_value,
        settlement_source_names=tuple(str(name).strip() for name in (settlement_source_names or []) if str(name).strip()),
    )


def enrich_primary_election_event(primary: KalshiPrimaryElection | None, *, parent_series_title: str = "", settlement_source_names: list[str] | tuple[str, ...] | None = None) -> KalshiPrimaryElection | None:
    if primary is None:
        return None
    incoming_names = tuple(str(name).strip() for name in (settlement_source_names or []) if str(name).strip())
    party = primary.party
    if not party:
        for name in incoming_names:
            party = _normalize_party_label(name)
            if party:
                break
    party_label = _PARTY_LABELS.get(party, "Other")
    office_label = primary.office_family or "Election"
    label_parts = [str(primary.cycle_year) if primary.cycle_year else "Unknown", office_label]
    if primary.seat_id:
        label_parts.append(primary.seat_id)
    label_parts.append(f"{party_label} primary")
    return replace(
        primary,
        party=party,
        normalized_contest_key=primary.normalized_contest_key or build_normalized_contest_key(
            office_family=primary.office_family,
            state_code=primary.state_code,
            district_code=primary.seat_id.split("-", 1)[1] if primary.office_family == "US-REP" and primary.seat_id and "-" in primary.seat_id else None,
            is_at_large=bool(primary.seat_id and primary.seat_id.endswith("-AL")),
            cycle_year=primary.cycle_year,
            party=party,
        ),
        parent_series_title=str(parent_series_title or "").strip() or primary.parent_series_title,
        settlement_source_names=incoming_names or primary.settlement_source_names,
        election_label=" | ".join(label_parts),
    )


@dataclass(frozen=True)
class KalshiElectionMetadata:
    state_code: str | None
    district_code: str | None
    is_at_large: bool
    office_family: str | None
    party: str | None
    cycle_year: int | None
    seat_id: str | None
    normalized_contest_key: str | None
    seat_hint_source: str | None
    combined_text: str


@dataclass(frozen=True)
class KalshiTickerNormalization:
    parent_series_ticker: str | None
    child_event_ticker: str | None
    contract_ticker: str | None
    event_key: str | None


STATEWIDE_OFFICE_PATTERNS: list[tuple[str, list[str]]] = [
    ("LTGOV", [r"LTGOV", r"LTGOV[A-Z]{2}", r"LIEUTENANT\s+GOVERNOR"]),
    ("GOV", [r"\bGOV(?:ERNOR)?\b", r"GOV[A-Z]{2}"]),
    ("ATTGEN", [r"\bATTYGEN\b", r"ATTYGEN[A-Z]{2}", r"ATTORNEY\s+GENERAL", r"\bAG\s+RACE\b"]),
    ("SECSTATE", [r"\bSECSTATE\b", r"SECSTATE[A-Z]{2}", r"SECRETARY\s+OF\s+STATE"]),
    ("COMPTROLLER", [r"\bCOMP(TROLLER)?\b"]),
    ("TREASURER", [r"\bTREAS(URER)?\b"]),
    ("AUDITOR", [r"\bAUDITOR\b"]),
    ("INS-COMM", [r"INSURANCE\s+COMMISSIONER", r"\bINSCOMM\b"]),
    ("SUPT", [r"SUPERINTENDENT", r"\bSUPT\b"]),
]


def parse_kalshi_ticker_hierarchy(
    *,
    parent_series_ticker: str = "",
    event_ticker: str = "",
    market_ticker: str = "",
) -> KalshiTickerNormalization:
    parent = str(parent_series_ticker or "").strip() or None
    child_event = str(event_ticker or "").strip() or None
    contract = str(market_ticker or "").strip() or None

    if child_event and not parent:
        parent = child_event.split("-", 1)[0].strip() or None

    if contract and child_event and not contract.startswith(f"{child_event}-"):
        child_event = None

    if contract and not child_event:
        candidate_child = contract.rsplit("-", 1)[0].strip()
        if candidate_child:
            child_event = candidate_child

    if child_event and not parent:
        parent = child_event.split("-", 1)[0].strip() or None

    event_key = None
    if child_event and parent and child_event.startswith(f"{parent}-"):
        event_key = child_event[len(parent) + 1 :].strip() or None
    elif child_event:
        parts = child_event.split("-", 1)
        event_key = parts[1].strip() if len(parts) == 2 and parts[1].strip() else None

    return KalshiTickerNormalization(
        parent_series_ticker=parent,
        child_event_ticker=child_event,
        contract_ticker=contract,
        event_key=event_key,
    )


def collect_context_segments(market_payload: dict, series_payload: dict | None) -> list[str]:
    series_payload = series_payload or {}
    settlement_sources = series_payload.get("settlement_sources", [])
    settlement_names = [str(source.get("name", "")) for source in settlement_sources if source.get("name")]
    segments = [
        str(market_payload.get("event_ticker") or ""),
        str(market_payload.get("ticker") or ""),
        str(market_payload.get("title") or ""),
        str(market_payload.get("rules_primary") or ""),
        str(series_payload.get("ticker") or ""),
        str(series_payload.get("title") or ""),
        " ".join(settlement_names),
    ]
    return [segment.strip() for segment in segments if segment and segment.strip()]


def infer_statewide_office_code(*texts: str) -> str | None:
    combined = " ".join(str(text or "") for text in texts).upper()
    for office_code, patterns in STATEWIDE_OFFICE_PATTERNS:
        if any(re.search(pattern, combined) for pattern in patterns):
            return office_code
    return None


def _extract_state_from_text(upper: str) -> str | None:
    for state_name, code in STATE_NAMES.items():
        if state_name.upper() in upper:
            return code

    title_district_match = re.search(r"\b([A-Z]{2})[-\s]?(?:AL|\d{1,2})\b", upper)
    if title_district_match and title_district_match.group(1) in STATE_CODES:
        return title_district_match.group(1)

    for match in re.findall(r"\b([A-Z]{2})\b", upper):
        if match in STATE_CODES:
            return match

    ticker_hint = re.search(r"(?:GOV|SENATE|ATTYGEN|SECSTATE)([A-Z]{2})", upper)
    if ticker_hint and ticker_hint.group(1) in STATE_CODES:
        return ticker_hint.group(1)

    return None


def _extract_seat_hint(upper: str) -> tuple[str | None, str | None, bool, str | None]:
    house = infer_us_house_parsing(event_ticker=upper, market_ticker=upper, series_ticker=upper, title=upper, rules_primary=upper)
    if house.state_code and (house.district_code or house.is_at_large):
        district_code = "AL" if house.is_at_large else house.district_code
        return house.state_code, district_code, house.is_at_large, f"structured:{upper}"

    match = re.search(r"\b([A-Z]{2})-(AL|\d{1,2})\b", upper)
    if match and match.group(1) in STATE_CODES:
        district_code = "AL" if match.group(2) == "AL" else f"{int(match.group(2)):02d}"
        return match.group(1), district_code, district_code == "AL", f"text:{match.group(0)}"

    return None, None, False, None


def parse_kalshi_election_metadata(*, event_ticker: str = "", market_ticker: str = "", series_ticker: str = "", title: str = "", rules_primary: str = "", series_title: str = "", settlement_source_names: list[str] | None = None) -> KalshiElectionMetadata:
    texts = [event_ticker, market_ticker, title, rules_primary, series_ticker, series_title, *(settlement_source_names or [])]
    uppercase_texts = [str(text or "").upper() for text in texts if str(text or "").strip()]
    combined = " ".join(uppercase_texts)

    # Precedence 1: trust explicit event_ticker district/party/cycle signals over series-level labels.
    state_code = None
    district_code = None
    is_at_large = False
    seat_hint_source = None
    if event_ticker:
        state_code, district_code, is_at_large, seat_hint_source = _extract_seat_hint(str(event_ticker).upper())

    # Precedence 2: confirm with title/rules mentions like IN-05 / IL-05 / AZ-01.
    confirming_state = None
    confirming_district = None
    confirming_at_large = False
    for text in (str(title).upper(), str(rules_primary).upper(), combined):
        confirming_state, confirming_district, confirming_at_large, confirming_source = _extract_seat_hint(text)
        if confirming_state and (confirming_district or confirming_at_large):
            if not state_code:
                state_code, district_code, is_at_large, seat_hint_source = (
                    confirming_state,
                    confirming_district,
                    confirming_at_large,
                    confirming_source,
                )
            elif state_code == confirming_state and district_code == confirming_district:
                seat_hint_source = seat_hint_source or confirming_source
            break

    # Fallbacks.
    if not state_code or (not district_code and not is_at_large):
        for upper in uppercase_texts:
            fallback_state, fallback_district, fallback_at_large, fallback_source = _extract_seat_hint(upper)
            if fallback_state and (fallback_district or fallback_at_large):
                state_code = state_code or fallback_state
                district_code = district_code or fallback_district
                is_at_large = is_at_large or fallback_at_large
                seat_hint_source = seat_hint_source or fallback_source
                break

    if not state_code:
        for upper in uppercase_texts:
            state_code = _extract_state_from_text(upper)
            if state_code:
                break

    house = infer_us_house_parsing(
        event_ticker=event_ticker,
        market_ticker=market_ticker,
        series_ticker=series_ticker,
        title=title,
        rules_primary=rules_primary,
    )
    if not state_code:
        state_code = house.state_code
    if not district_code and not is_at_large and (house.district_code or house.is_at_large):
        district_code = "AL" if house.is_at_large else house.district_code
        is_at_large = house.is_at_large
        seat_hint_source = seat_hint_source or "house_parser"

    party = house.party
    if not party:
        if re.search(r"\b(DEMOCRAT|DEMOCRATIC)\b", combined):
            party = "D"
        elif re.search(r"\b(REPUBLICAN|GOP)\b", combined):
            party = "R"

    cycle_year = house.cycle_year
    if not cycle_year:
        for pattern in (re.compile(r"[DR](\d{2})(?:-|$)"), re.compile(r"-(\d{2})(?:-|$)"), re.compile(r"\b(20\d{2})\b")):
            match = pattern.search(combined)
            if match:
                value = match.group(1)
                cycle_year = int(value) if len(value) == 4 else 2000 + int(value)
                break

    office_family = None
    if district_code or is_at_large:
        # District code is definitive evidence of a US House seat.
        # Short-circuit before statewide_office inference so that boilerplate
        # settlement source text (e.g. "Attorney General of the United States",
        # which Kalshi includes on every election contract) cannot produce a
        # false ATTGEN/GOV/etc. classification for congressional markets.
        office_family = "US-REP"
    else:
        statewide_office = infer_statewide_office_code(combined)
        if statewide_office:
            office_family = statewide_office
        elif re.search(r"\bSTATE\s+SEN(?:ATE)?\b", combined):
            office_family = "State-SEN"
        elif re.search(r"\b(HOUSE\s+OF\s+DELEGATES|STATE\s+(?:HOUSE|REP(?:RESENTATIVE|RESENTATIVES)?S?)|ASSEMBLY)\b", combined):
            office_family = "State-REP"
        elif re.search(r"\b(HOUSE\s+SEAT|HOUSE|CONGRESS|CONGRESSIONAL\s+DISTRICT|REP(?:RESENTATIVE)?\b)\b", combined):
            office_family = "US-REP"
        elif re.search(r"\b(SENATE|U\.?S\.?\s*SEN|US[-\s]?SEN|SENATOR)\b", combined):
            office_family = "US-SEN"
        elif state_code:
            # Only emit Statewide when no district- or office-specific evidence exists.
            office_family = "Statewide"

    seat_id = None
    if state_code:
        if is_at_large:
            seat_id = f"{state_code}-AL"
        elif district_code:
            seat_id = f"{state_code}-{district_code}"
        elif office_family and office_family != "Statewide":
            seat_id = build_statewide_seat_id(state_code=state_code, office_family=office_family)

    normalized_contest_key = build_normalized_contest_key(
        office_family=office_family,
        state_code=state_code,
        district_code=district_code,
        is_at_large=is_at_large,
        cycle_year=cycle_year,
        party=party,
    )

    return KalshiElectionMetadata(
        state_code=state_code,
        district_code=None if district_code == "AL" else district_code,
        is_at_large=is_at_large,
        office_family=office_family,
        party=party,
        cycle_year=cycle_year,
        seat_id=seat_id,
        normalized_contest_key=normalized_contest_key,
        seat_hint_source=seat_hint_source,
        combined_text=combined,
    )
