#!/usr/bin/env python3
"""Build a congressional-district Kalshi market index joined to canonical U.S. House seat IDs."""
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

from ballotpedia_rollup.kalshi import (
    DEFAULT_MARKET_DIRS,
    DEFAULT_SERIES_DIRS,
    build_kalshi_us_rep_contest_rows,
    validate_kalshi_us_rep_contests,
)
from kalshi_metadata_parsing import parse_kalshi_election_metadata, parse_kalshi_ticker_hierarchy, parse_primary_election_event
from ballotpedia_rollup.config import display_path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKET_INPUT_DIRS = DEFAULT_MARKET_DIRS
SERIES_INPUT_DIRS = DEFAULT_SERIES_DIRS
MARKET_INPUT_DIR = MARKET_INPUT_DIRS[0]
SERIES_INPUT_DIR = SERIES_INPUT_DIRS[0]
SEAT_INDEX_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-seats.json"
OUTPUT_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-market-index.json"
OUTPUT_VIOLATIONS_FILE = REPO_ROOT / "apps" / "web" / "data" / "us-house-market-index-violations.json"


class HouseMarketIndexError(RuntimeError):
    pass


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_series_lookup(series_dir: Path = SERIES_INPUT_DIR) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for path in sorted(series_dir.glob("*.json")):
        payload = load_json(path)
        ticker = str(payload.get("ticker") or "").strip()
        if ticker:
            lookup[ticker] = payload
    return lookup


def load_seat_lookup(seat_index_file: Path = SEAT_INDEX_FILE) -> dict[str, dict]:
    payload = load_json(seat_index_file)
    return {seat["seatId"]: seat for seat in payload.get("seats", [])}


def parse_odds_percent(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value) * 100, 2)
    except (TypeError, ValueError):
        return None


def infer_entity_name(market_payload: dict) -> str | None:
    custom_strike = market_payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        for key in ("Candidate", "candidate", "Party", "political_party", "Nominee", "Person"):
            value = custom_strike.get(key)
            if isinstance(value, str) and value.strip() and not value.startswith("9244"):
                return value.strip()

    for key in ("yes_sub_title", "title"):
        value = market_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def infer_market_type(title: str, entity_name: str | None) -> str:
    upper = title.upper()
    normalized_entity = (entity_name or "").strip().lower()
    if "NOMINEE" in upper or "PRIMARY" in upper:
        return "candidate_nominee"
    if normalized_entity in {"democratic", "democratic party", "democrat", "republican", "republican party"}:
        return "party_winner"
    if "PARTY" in upper or re.search(r"\b(DEMOCRAT|DEMOCRATIC|REPUBLICAN|GOP)\b", upper):
        return "party_winner"
    return "district_winner"


def infer_party(market_payload: dict, title: str, series_title: str) -> str | None:
    custom_strike = market_payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        party_value = custom_strike.get("Party")
        if isinstance(party_value, str) and party_value.strip():
            party = party_value.strip().lower()
            if party.startswith("dem"):
                return "D"
            if party.startswith("rep"):
                return "R"

    combined = f"{title} {series_title}".upper()
    if "DEMOCRATIC" in combined or "DEMOCRAT" in combined:
        return "D"
    if "REPUBLICAN" in combined or "GOP" in combined:
        return "R"
    return None


def infer_cycle_year(*texts: str) -> int | None:
    parsed = parse_kalshi_election_metadata(
        event_ticker=texts[0] if texts else "",
        market_ticker=texts[1] if len(texts) > 1 else "",
        series_ticker=texts[2] if len(texts) > 2 else "",
    )
    return parsed.cycle_year


def infer_election_type(market_payload: dict, title: str, series_title: str, entity_name: str | None) -> str:
    primary = parse_primary_election_event(
        event_ticker=str(market_payload.get("event_ticker") or ""),
        parent_series_ticker=str(market_payload.get("series_ticker") or ""),
        parent_series_title=series_title,
    )
    if primary is not None:
        return primary.election_kind
    combined = " ".join(
        str(value or "")
        for value in (
            title,
            series_title,
            market_payload.get("rules_primary"),
            market_payload.get("rules_secondary"),
            entity_name,
        )
    ).upper()
    if "PRIMARY" in combined or "NOMINEE" in combined or "NOMINATION" in combined:
        return "primary"
    return "general"


def infer_seat_id(series_ticker: str, market_ticker: str, title: str, rules_primary: str = "") -> str | None:
    parsed = parse_kalshi_election_metadata(
        event_ticker=series_ticker,
        market_ticker=market_ticker,
        series_ticker=series_ticker,
        title=title,
        rules_primary=rules_primary,
    )
    return parsed.seat_id


def build_market_record(market_payload: dict, series_payload: dict | None, seat_lookup: dict[str, dict]) -> tuple[str, dict] | None:
    market_ticker = str(market_payload.get("ticker") or "").strip()
    ticker_context = parse_kalshi_ticker_hierarchy(
        parent_series_ticker=str(series_payload.get("ticker") if series_payload else ""),
        event_ticker=str(market_payload.get("event_ticker") or ""),
        market_ticker=market_ticker,
    )
    series_ticker = ticker_context.parent_series_ticker or ""
    event_ticker = ticker_context.child_event_ticker or str(market_payload.get("event_ticker") or "").strip()
    title = str(market_payload.get("title") or "").strip()
    rules_primary = str(market_payload.get("rules_primary") or "")
    settlement_source_names = [str(source.get("name", "")) for source in (series_payload or {}).get("settlement_sources", []) if source.get("name")]
    parsed_house = parse_kalshi_election_metadata(
        event_ticker=event_ticker,
        market_ticker=market_ticker,
        series_ticker=series_ticker,
        title=title,
        rules_primary=rules_primary,
        series_title=str(series_payload.get("title") if series_payload else ""),
        settlement_source_names=settlement_source_names,
    )
    primary_election = parse_primary_election_event(
        event_ticker=str(market_payload.get("event_ticker") or series_ticker),
        parent_series_ticker=series_ticker,
        parent_series_title=str(series_payload.get("title") if series_payload else ""),
        settlement_source_names=settlement_source_names,
    )
    seat_id = parsed_house.seat_id
    if not seat_id or seat_id not in seat_lookup:
        return None

    series_title = str(series_payload.get("title") if series_payload else "").strip()
    entity_name = infer_entity_name(market_payload)
    record = {
        "seatId": seat_id,
        "stateCode": seat_lookup[seat_id]["stateCode"],
        "districtNumber": seat_lookup[seat_id]["districtNumber"],
        "districtCode": seat_lookup[seat_id]["districtCode"],
        "marketTicker": market_ticker,
        "eventTicker": event_ticker or None,
        "eventKey": ticker_context.event_key,
        "seriesTicker": series_ticker,
        "seriesTitle": series_title,
        "eventTicker": market_payload.get("event_ticker") or None,
        "parentSeries": {
            "ticker": series_ticker or None,
            "title": series_title or None,
            "category": series_payload.get("category") if series_payload else None,
            "settlementSources": [
                {
                    "name": source.get("name"),
                    "url": source.get("url"),
                }
                for source in (series_payload or {}).get("settlement_sources", [])
                if isinstance(source, dict)
            ],
        },
        "childElection": {
            "ticker": event_ticker or None,
            "key": ticker_context.event_key,
        },
        "title": title,
        "subtitle": market_payload.get("subtitle") or None,
        "yesSubtitle": market_payload.get("yes_sub_title") or None,
        "marketType": infer_market_type(title, entity_name),
        "entityName": entity_name,
        "party": parsed_house.party or infer_party(market_payload, title, series_title),
        "electionType": primary_election.election_kind if primary_election else infer_election_type(market_payload, title, series_title, entity_name),
        "electionLabel": primary_election.election_label if primary_election else None,
        "normalizedContestKey": primary_election.normalized_contest_key if primary_election else parsed_house.normalized_contest_key,
        "status": market_payload.get("status") or None,
        "closeTime": market_payload.get("close_time") or None,
        "lastPriceDollars": market_payload.get("last_price_dollars") or None,
        "oddsPercent": parse_odds_percent(market_payload.get("last_price_dollars")),
        "liquidityDollars": market_payload.get("liquidity_dollars") or None,
        "openInterest": market_payload.get("open_interest") or market_payload.get("open_interest_fp") or None,
        "volume": market_payload.get("volume") or None,
        "result": market_payload.get("result") or None,
        "rulesPrimary": market_payload.get("rules_primary") or None,
        "electionCycle": parsed_house.cycle_year or infer_cycle_year(market_ticker, series_ticker),
        "sourceFile": str(market_payload.get("_source_file") or ""),
    }
    return seat_id, record


def build_us_house_market_index(
    market_input_dir: Path | tuple[Path, ...] = MARKET_INPUT_DIRS,
    series_input_dir: Path | tuple[Path, ...] = SERIES_INPUT_DIRS,
    seat_index_file: Path = SEAT_INDEX_FILE,
    output_file: Path = OUTPUT_FILE,
    *,
    strict: bool = False,
    output_violations_file: Path = OUTPUT_VIOLATIONS_FILE,
) -> dict:
    if isinstance(market_input_dir, Path):
        market_dirs = (market_input_dir,)
    else:
        market_dirs = tuple(market_input_dir)
    if isinstance(series_input_dir, Path):
        series_dirs = (series_input_dir,)
    else:
        series_dirs = tuple(series_input_dir)

    seat_lookup = load_seat_lookup(seat_index_file)
    contests, violations, summary = build_kalshi_us_rep_contest_rows(
        market_dirs=market_dirs,
        series_dirs=series_dirs,
    )
    violations = validate_kalshi_us_rep_contests(contests, violations)

    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    matched_markets = 0
    for contest in contests:
        seat_id = str(contest.get("seat") or "").strip()
        if not seat_id or seat_id not in seat_lookup:
            continue
        for market in contest.get("markets") or []:
            if not isinstance(market, dict):
                continue
            record = {
                "seatId": seat_id,
                "stateCode": seat_lookup[seat_id]["stateCode"],
                "districtNumber": seat_lookup[seat_id]["districtNumber"],
                "districtCode": seat_lookup[seat_id]["districtCode"],
                "marketTicker": market.get("marketTicker"),
                "eventTicker": market.get("eventTicker"),
                "seriesTicker": market.get("seriesTicker"),
                "seriesTitle": None,
                "title": None,
                "yesSubtitle": None,
                "marketType": contest.get("market_role"),
                "marketRole": contest.get("market_role"),
                "entityName": market.get("entityName"),
                "party": contest.get("party_lane"),
                "electionType": contest.get("round"),
                "electionLabel": f"{seat_id} {str(contest.get('round') or '').title()}",
                "normalizedContestKey": contest.get("normalized_contest_key"),
                "status": market.get("status"),
                "closeTime": market.get("closeTime"),
                "lastPriceDollars": None,
                "oddsPercent": market.get("oddsPercent"),
                "liquidityDollars": None,
                "openInterest": None,
                "volume": None,
                "result": None,
                "rulesPrimary": None,
                "electionCycle": contest.get("cycle_year"),
                "sourceFile": market.get("sourceFile"),
                "sourceDir": market.get("sourceDir"),
                "sourcePriority": market.get("sourcePriority"),
                "entityDerivation": market.get("entityDerivation"),
                "partyDerivation": market.get("partyDerivation"),
            }
            primary_group_key = record.get("normalizedContestKey") or seat_id
            grouped[seat_id][primary_group_key].append(record)
            matched_markets += 1

    districts = []
    for seat_id, seat in sorted(seat_lookup.items(), key=lambda item: (item[1]["stateCode"], item[1]["districtNumber"])):
        seat_markets = sorted(
            [record for contest_records in grouped.get(seat_id, {}).values() for record in contest_records],
            key=lambda item: (
                item.get("electionCycle") or 0,
                item.get("marketRole") or "",
                item.get("party") or "",
                item.get("entityName") or "",
                item.get("marketTicker") or "",
            ),
            reverse=True,
        )
        districts.append({
            "seatId": seat_id,
            "displayName": seat.get("displayName"),
            "districtLabel": seat.get("districtLabel"),
            "stateCode": seat.get("stateCode"),
            "districtNumber": seat.get("districtNumber"),
            "districtCode": seat.get("districtCode"),
            "marketCount": len(seat_markets),
            "markets": seat_markets,
        })

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "marketInputDirectory": display_path(market_dirs[0]) if market_dirs else "",
        "seriesInputDirectory": display_path(series_dirs[0]) if series_dirs else "",
        "marketInputDirectories": [display_path(path) for path in market_dirs],
        "seriesInputDirectories": [display_path(path) for path in series_dirs],
        "seatIndexFile": display_path(seat_index_file),
        "scannedFiles": summary.get("scanned_markets", 0),
        "discoveredMarkets": summary.get("discovered_markets", 0),
        "selectedMarkets": summary.get("selected_markets", 0),
        "matchedMarkets": matched_markets,
        "districtCount": len(districts),
        "violationCount": len(violations),
        "districts": districts,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_violations_file.parent.mkdir(parents=True, exist_ok=True)
    output_violations_file.write_text(
        json.dumps({"generatedAt": payload["generatedAt"], "count": len(violations), "violations": violations}, indent=2) + "\n",
        encoding="utf-8",
    )
    if strict and violations:
        raise HouseMarketIndexError(f"US-House market index integrity validation failed with {len(violations)} violation(s)")
    return payload


def main() -> None:
    payload = build_us_house_market_index(strict=True)
    print(f"Wrote {payload['matchedMarkets']} US-REP markets across {payload['districtCount']} districts to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
