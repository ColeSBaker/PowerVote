#!/usr/bin/env python3
"""Build a state-scoped winner-market index from Kalshi JSON snapshots."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kalshi_metadata_parsing import (
    KalshiElectionMetadata,
    infer_statewide_office_code,
    parse_kalshi_election_metadata,
    parse_primary_election_event,
    parse_kalshi_ticker_hierarchy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = REPO_ROOT / "test_data" / "kalshi_json_data"
MARKET_INPUT_DIR = INPUT_DIR / "market"
SERIES_INPUT_DIR = INPUT_DIR / "series"
OUTPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "state-election-markets.json"

EXCLUDE_PATTERNS = [
    r"%", r"percent", r"margin", r"2nd place", r"third place", r"number of seats", r"closest", r"endorse",
    r"billionaire tax", r"round", r"electoral vote", r"turnout",
]

INCLUDE_PATTERNS = [
    r"winner", r"will win", r"nominee", r"nomination", r"primary winners", r"party",
]


def build_parsed_market_context(market_payload: dict, series_payload: dict | None = None) -> KalshiElectionMetadata:
    series_payload = series_payload or {}
    ticker_context = parse_kalshi_ticker_hierarchy(
        parent_series_ticker=str(series_payload.get("ticker") or ""),
        event_ticker=str(market_payload.get("event_ticker") or ""),
        market_ticker=str(market_payload.get("ticker") or ""),
    )
    settlement_source_names = [
        str(source.get("name", ""))
        for source in series_payload.get("settlement_sources", [])
        if source.get("name")
    ]
    return parse_kalshi_election_metadata(
        event_ticker=str(ticker_context.child_event_ticker or ""),
        market_ticker=str(ticker_context.contract_ticker or market_payload.get("ticker") or ""),
        series_ticker=str(ticker_context.parent_series_ticker or series_payload.get("ticker") or ""),
        title=str(market_payload.get("title") or series_payload.get("title") or ""),
        rules_primary=str(market_payload.get("rules_primary") or ""),
        series_title=str(series_payload.get("title") or ""),
        settlement_source_names=settlement_source_names,
    )


def build_primary_election_context(market_payload: dict, series_payload: dict | None = None):
    series_payload = series_payload or {}
    settlement_source_names = [
        str(source.get("name", ""))
        for source in series_payload.get("settlement_sources", [])
        if source.get("name")
    ]
    return parse_primary_election_event(
        event_ticker=str(market_payload.get("event_ticker") or series_payload.get("ticker") or ""),
        parent_series_ticker=str(series_payload.get("ticker") or ""),
        parent_series_title=str(series_payload.get("title") or ""),
        settlement_source_names=settlement_source_names,
    )


def infer_state(series_ticker: str, market_ticker: str, title: str, series: dict | None = None) -> str | None:
    context = parse_kalshi_election_metadata(
        event_ticker=str(series_ticker or ""),
        market_ticker=str(market_ticker or ""),
        series_ticker=str(series_ticker or ""),
        title=str(title or ""),
        rules_primary=str((series or {}).get("rules_primary") or ""),
        series_title=str((series or {}).get("title") or ""),
        settlement_source_names=[
            str(source.get("name", ""))
            for source in (series or {}).get("settlement_sources", [])
            if source.get("name")
        ],
    )
    return context.state_code


def infer_seat_type(*args) -> str:
    context = args[0] if len(args) == 1 and isinstance(args[0], KalshiElectionMetadata) else parse_kalshi_election_metadata(
        event_ticker=str(args[1] if len(args) > 1 else ""),
        market_ticker=str(args[2] if len(args) > 2 else ""),
        series_ticker=str(args[1] if len(args) > 1 else ""),
        title=str(args[3] if len(args) > 3 else ""),
    )
    office_family = context.office_family or "Statewide"
    if office_family in {"US-REP", "US-SEN", "State-SEN", "State-REP", "Statewide"}:
        return office_family
    return "Statewide"

def infer_primary_party(series_ticker: str, market_ticker: str, title: str, series: dict | None = None) -> str | None:
    primary = build_primary_election_context({"ticker": market_ticker, "event_ticker": market_ticker, "title": title}, {**(series or {}), "ticker": series_ticker})
    if primary is not None:
        return primary.party
    context = build_parsed_market_context({"ticker": market_ticker, "title": title}, {**(series or {}), "ticker": series_ticker})
    return context.party


def infer_election_type(*args) -> str:
    if len(args) == 1 and isinstance(args[0], KalshiElectionMetadata):
        context = args[0]
        primary = None
    else:
        market_payload = {
            "ticker": args[1] if len(args) > 1 else "",
            "event_ticker": args[1] if len(args) > 1 else "",
            "title": args[2] if len(args) > 2 else "",
        }
        series_payload = {**(args[3] if len(args) > 3 and isinstance(args[3], dict) else {}), "ticker": args[0] if args else ""}
        primary = build_primary_election_context(market_payload, series_payload)
        context = build_parsed_market_context(market_payload, series_payload)
    cycle_year = context.cycle_year or (primary.cycle_year if primary else None) or "Unknown"
    if primary is not None:
        return f"{cycle_year} Primary ({primary.party or 'other'})"
    if re.search(r"\b(PRIMARY|NOM|NOMINEE)\b", context.combined_text):
        if context.party:
            return f"{cycle_year} Primary ({context.party})"
        return f"{cycle_year} Primary (other)"
    return f"{cycle_year} General"


def extract_district_number(state: str, market_ticker: str, title: str) -> int | None:
    district_patterns = [
        rf"\b{state}[-\s]?(\d{{1,2}})\b",
        r"-(\d{1,2})[DR]\d{2}$",
    ]
    for text in (market_ticker.upper(), title.upper()):
        for pattern in district_patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
    return None


def infer_at_large_seat_id(state: str, market_ticker: str, title: str, seat_type: str) -> str | None:
    if seat_type != "US-REP":
        return None

    combined = f"{market_ticker} {title}".upper()
    if re.search(rf"(?:-|^){state}AL(?:-|$)", combined):
        return f"{state}-AL"

    if "AT-LARGE" in combined or "AT LARGE" in combined:
        return f"{state}-AL"

    return None


def infer_seat_id(*args) -> str:
    if len(args) == 2 and isinstance(args[0], KalshiElectionMetadata):
        context, seat_type = args
    else:
        context = parse_kalshi_election_metadata(
            event_ticker=str(args[1] if len(args) > 1 else ""),
            market_ticker=str(args[2] if len(args) > 2 else ""),
            series_ticker=str(args[1] if len(args) > 1 else ""),
            title=str(args[3] if len(args) > 3 else ""),
        )
        seat_type = args[4] if len(args) > 4 else infer_seat_type(context)
    state = context.state_code or "UNKNOWN"
    if seat_type == "US-REP":
        if context.is_at_large:
            return f"{state}-AL"
        if context.district_code:
            return f"{state}-{context.district_code}"

    seat_suffix_map = {
        "US-SEN": "SEN",
        "US-REP": "REP",
        "Statewide": context.office_family if context.office_family and context.office_family != "Statewide" else "STATE",
        "State-SEN": "STATE-SEN",
        "State-REP": "STATE-REP",
    }
    suffix = seat_suffix_map.get(seat_type, seat_type.replace(" ", "-").upper())
    return f"{state}-{suffix}"


def build_market_title(election_type: str, seat_type: str, seat_id: str) -> str:
    return f"{election_type} - {seat_type} - {seat_id}"


def build_market_context_title(series: dict | None, market_payload: dict) -> str:
    title_parts = []
    for value in (
        (series or {}).get("title"),
        market_payload.get("title"),
        market_payload.get("yes_sub_title"),
        market_payload.get("rules_primary"),
    ):
        if value:
            title_parts.append(str(value))
    return " | ".join(title_parts)


def infer_entity_name(market_payload: dict, market_ticker: str) -> str:
    custom_strike = market_payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        for key in ("Candidate", "candidate", "politician", "Politician", "Party", "political_party", "Nominee", "Person", "Individual"):
            value = custom_strike.get(key)
            if value:
                return str(value).strip()

        for value in custom_strike.values():
            if value:
                return str(value).strip()

    for key in ("yes_sub_title", "no_sub_title", "title"):
        value = market_payload.get(key)
        if value:
            return str(value).strip()

    ticker_segments = market_ticker.split("-")
    return ticker_segments[-1] if ticker_segments else market_ticker


def parse_odds_percent(market_payload: dict) -> float | None:
    last_price = market_payload.get("last_price_dollars")
    if last_price in (None, ""):
        return None

    try:
        return round(float(last_price) * 100, 2)
    except (TypeError, ValueError):
        return None


def is_winner_market(title: str, series_ticker: str = "", market_ticker: str = "") -> bool:
    lower_title = title.lower()
    if any(re.search(pattern, lower_title) for pattern in EXCLUDE_PATTERNS):
        return False
    if any(re.search(pattern, lower_title) for pattern in INCLUDE_PATTERNS):
        return True

    combined = f"{series_ticker} {market_ticker} {title}".upper()
    has_election_context = bool(re.search(r"\b(RACE|ELECTION|PRIMARY|GENERAL|NOM|NOMINEE)\b", combined))
    if not has_election_context:
        has_election_context = bool(re.search(r"-(\d{2})(?:-|$)", market_ticker.upper()))
    has_office_context = bool(
        infer_statewide_office_code(series_ticker, market_ticker, title)
        or "SENATE" in combined
        or "HOUSE" in combined
        or "DELEGATE" in combined
    )
    return has_election_context and has_office_context


def load_series_lookup() -> dict[str, dict]:
    series_lookup: dict[str, dict] = {}
    for series_file in SERIES_INPUT_DIR.glob("series_*.json"):
        payload = json.loads(series_file.read_text())
        ticker = payload.get("ticker")
        if ticker:
            series_lookup[ticker] = payload
    return series_lookup


def iter_market_payloads() -> tuple[int, list[tuple[Path, dict, str, str]]]:
    scanned = 0
    seen_tickers: set[str] = set()
    market_rows: list[tuple[Path, dict, str, str]] = []

    market_input_dirs = [REPO_ROOT / "test_data" / "kalshi" / "market", MARKET_INPUT_DIR]
    for market_dir in market_input_dirs:
        if not market_dir.exists():
            continue

        for file_path in sorted(market_dir.glob("market_*.json")):
            scanned += 1
            market_payload = json.loads(file_path.read_text())
            stem = file_path.stem
            parts = stem.split("_")
            if len(parts) < 3:
                continue

            market_ticker = str(market_payload.get("ticker") or parts[2])
            ticker_context = parse_kalshi_ticker_hierarchy(
                parent_series_ticker=parts[1],
                event_ticker=str(market_payload.get("event_ticker") or ""),
                market_ticker=market_ticker,
            )
            series_ticker = ticker_context.parent_series_ticker or parts[1]
            if market_ticker in seen_tickers:
                continue

            seen_tickers.add(market_ticker)
            market_rows.append((file_path, market_payload, series_ticker, market_ticker))

    return scanned, market_rows


def main() -> None:
    series_lookup = load_series_lookup()
    by_state: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    scanned, market_rows = iter_market_payloads()

    for file_path, market_payload, series_ticker, market_ticker in market_rows:
        series = series_lookup.get(series_ticker, {})
        ticker_context = parse_kalshi_ticker_hierarchy(
            parent_series_ticker=series_ticker,
            event_ticker=str(market_payload.get("event_ticker") or ""),
            market_ticker=market_ticker,
        )
        title = build_market_context_title(series, market_payload) or series_ticker
        series_payload = {**series, "ticker": series_ticker}
        enriched_market_payload = {**market_payload, "ticker": market_ticker, "title": market_payload.get("title") or title}
        classifier_context = build_parsed_market_context(enriched_market_payload, series_payload)
        primary_election = build_primary_election_context(enriched_market_payload, series_payload)

        if not is_winner_market(title, series_ticker, market_ticker):
            continue

        state = classifier_context.state_code
        if not state:
            continue

        seat_type = infer_seat_type(classifier_context)
        election_type = infer_election_type(classifier_context) if primary_election is None else f"{primary_election.cycle_year or classifier_context.cycle_year or 'Unknown'} Primary ({primary_election.party or 'other'})"
        seat_id = infer_seat_id(classifier_context, seat_type)
        entity_name = infer_entity_name(market_payload, market_ticker)
        odds_percent = parse_odds_percent(market_payload)
        normalized_contest_key = primary_election.normalized_contest_key if primary_election else classifier_context.normalized_contest_key
        by_state[state][normalized_contest_key or market_ticker].append(
            {
                "marketTicker": market_ticker,
                "eventTicker": ticker_context.child_event_ticker,
                "eventKey": ticker_context.event_key,
                "seriesTicker": series_ticker,
                "parentSeries": {
                    "ticker": series_ticker or None,
                    "title": series.get("title"),
                    "category": series.get("category"),
                    "settlementSources": [
                        {
                            "name": source.get("name"),
                            "url": source.get("url"),
                        }
                        for source in series.get("settlement_sources", [])
                        if isinstance(source, dict)
                    ],
                },
                "childElection": {
                    "ticker": ticker_context.child_event_ticker,
                    "key": ticker_context.event_key,
                },
                "title": build_market_title(election_type, seat_type, seat_id),
                "eventTicker": market_payload.get("event_ticker") or None,
                "parentSeriesTitle": primary_election.parent_series_title if primary_election else (series.get("title") or None),
                "electionLabel": primary_election.election_label if primary_election else None,
                "normalizedContestKey": normalized_contest_key,
                "seatType": seat_type,
                "electionType": election_type,
                "seatId": seat_id,
                "entityName": entity_name,
                "oddsPercent": odds_percent,
                "sourceFile": file_path.name,
            }
        )

    flattened_by_state: dict[str, list[dict]] = {}
    for code, grouped_records in by_state.items():
        records = [record for contest_records in grouped_records.values() for record in contest_records]
        records.sort(key=lambda item: ((item.get("normalizedContestKey") or ""), item["marketTicker"]))
        flattened_by_state[code] = records

    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputDirectory": str(INPUT_DIR.relative_to(REPO_ROOT)),
        "scannedFiles": scanned,
        "includedMarkets": sum(len(v) for v in flattened_by_state.values()),
        "stateMarkets": dict(sorted(flattened_by_state.items())),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2) + "\n")

    print(f"Wrote {output['includedMarkets']} markets across {len(flattened_by_state)} states to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
