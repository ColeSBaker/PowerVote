"""Kalshi US-REP contest indexing and rollup join helpers."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kalshi_candidate_mapping import build_candidate_market_rows, build_candidate_match_report
from kalshi_metadata_parsing import build_kalshi_event_url, parse_kalshi_election_metadata, parse_kalshi_ticker_hierarchy, parse_primary_election_event
from .config import display_path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent

DEFAULT_MARKET_DIRS = (
    WORKSPACE_ROOT / "kalshi" / "data" / "markets",
    REPO_ROOT / "test_data" / "kalshi" / "market",
    REPO_ROOT / "test_data" / "kalshi_json_data" / "market",
)
DEFAULT_SERIES_DIRS = (
    WORKSPACE_ROOT / "kalshi" / "data" / "series",
    REPO_ROOT / "test_data" / "kalshi" / "series",
    REPO_ROOT / "test_data" / "kalshi_json_data" / "series",
)

DEFAULT_OUTPUT_INDEX_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-rep-contest-index.json"
DEFAULT_OUTPUT_INDEX_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-rep-contest-index.csv"
DEFAULT_OUTPUT_VIOLATIONS_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-contest-integrity-violations.csv"
DEFAULT_OUTPUT_VIOLATIONS_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-contest-integrity-violations.json"
DEFAULT_OUTPUT_ROLLUP_JOIN_AUDIT_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-rollup-join-audit.csv"
DEFAULT_OUTPUT_BALLOTPEDIA_UNMATCHED_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-kalshi-unmatched-candidates.csv"
DEFAULT_OUTPUT_HOUSE_CANDIDATE_WINNER_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-house-candidate-winner.json"
DEFAULT_OUTPUT_HOUSE_CANDIDATE_WINNER_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-house-candidate-winner.csv"
DEFAULT_OUTPUT_HOUSE_CANDIDATE_NOMINEE_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-house-candidate-nominee.json"
DEFAULT_OUTPUT_HOUSE_CANDIDATE_NOMINEE_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-house-candidate-nominee.csv"
DEFAULT_OUTPUT_HOUSE_CANDIDATE_MATCH_REPORT_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-house-candidate-match-report.json"
DEFAULT_OUTPUT_HOUSE_CANDIDATE_MATCH_REPORT_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-house-candidate-match-report.csv"
DEFAULT_BALLOTPEDIA_HOUSE_PRIMARY_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.csv"
DEFAULT_BALLOTPEDIA_HOUSE_RUNOFF_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-runoff-election-rollup.csv"
DEFAULT_BALLOTPEDIA_HOUSE_GENERAL_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-general-election-rollup.csv"


PARTY_LABELS = {
    "D": {"D", "DEM", "DEMOCRAT", "DEMOCRATIC", "DEMOCRATIC PARTY"},
    "R": {"R", "REP", "REPUBLICAN", "REPUBLICAN PARTY", "GOP"},
}

RUNOFF_TEXT_RE = re.compile(r"\b(runoff|second round|2nd round)\b", flags=re.IGNORECASE)
NON_OUTCOME_TEXT_RE = re.compile(
    r"\b(percent|margin|number of seats|turnout|electoral vote|2nd place|third place)\b",
    flags=re.IGNORECASE,
)
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    flags=re.IGNORECASE,
)
HOUSE_HINT_RE = re.compile(
    r"\b(HOUSE\s+RACE|CONGRESSIONAL\s+DISTRICT|U\.?S\.?\s+HOUSE|US-REP|SWORN\s+IN)\b",
    flags=re.IGNORECASE,
)
TICKER_PARTY_PATTERNS = (
    re.compile(r"-(\d{1,2})([DR])(\d{2})(?:-|$)", flags=re.IGNORECASE),
    re.compile(r"(?:^|[-_])[A-Z]{2}(?:AL|\d{1,2})([DR])-(\d{2})(?:-|$)", flags=re.IGNORECASE),
    re.compile(r"-(\d{2})-([DR])(?:-|$)", flags=re.IGNORECASE),
    re.compile(r"(?:^|[-_])([DR])-(\d{2})(?:-|$)", flags=re.IGNORECASE),
    re.compile(r"(?:-|^)[A-Z0-9]+([DR])-(\d{2})(?:-|$)", flags=re.IGNORECASE),
    re.compile(r"\bNOM([DR])\b", flags=re.IGNORECASE),
)

# Advance-count detection — mirrors kalshi_gov_shared.py (avoid circular import)
_TOP_FOUR_RE = re.compile(r"top.four|top-4\b|four\s+candidates?\s+advance", flags=re.IGNORECASE)
_TOP_TWO_RE  = re.compile(r"top.two|top-2\b|top\s+2\s+primary|two\s+candidates?\s+advance", flags=re.IGNORECASE)
_ADVANCE_RE  = re.compile(r"\badvances?\b", flags=re.IGNORECASE)


def _extract_advance_count(rules: str, title: str = "") -> int:
    """Return how many candidates advance: 4 (top-four), 2 (top-two / generic advance), or 1 (binary)."""
    combined = f"{rules} {title}"
    if _TOP_FOUR_RE.search(combined):
        return 4
    if _TOP_TWO_RE.search(combined):
        return 2
    if _ADVANCE_RE.search(combined):
        return 2
    return 1


def normalize_name(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_seat_id(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    match = re.match(r"^([A-Z]{2})-(AL|\d{1,2})$", text)
    if not match:
        return text
    state, district = match.groups()
    if district == "AL":
        return f"{state}-AL"
    return f"{state}-{int(district):02d}"


def normalize_party(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text in PARTY_LABELS["D"]:
        return "D"
    if text in PARTY_LABELS["R"]:
        return "R"
    return None


def parse_odds_percent(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value) * 100, 2)
    except (TypeError, ValueError):
        return None


def build_entity_odds_map(markets: list[dict[str, Any]] | None) -> dict[str, float]:
    """Build deterministic entity->odds map.

    Preference:
    1) active market over non-active
    2) higher odds value
    """
    selected: dict[str, tuple[bool, float]] = {}
    for market in markets or []:
        entity = str(market.get("entityName") or "").strip()
        if not entity:
            continue
        odds_value = None
        try:
            odds_value = float(market.get("oddsPercent"))
        except (TypeError, ValueError):
            odds_value = parse_odds_percent(market.get("lastPriceDollars"))
        if odds_value is None:
            continue
        is_active = str(market.get("status") or "").strip().lower() == "active"
        existing = selected.get(entity)
        if existing is None:
            selected[entity] = (is_active, float(odds_value))
            continue
        existing_active, existing_odds = existing
        if is_active and not existing_active:
            selected[entity] = (is_active, float(odds_value))
            continue
        if is_active == existing_active and float(odds_value) > existing_odds:
            selected[entity] = (is_active, float(odds_value))

    return {
        entity: round(odds, 2)
        for entity, (_active, odds) in sorted(selected.items(), key=lambda item: item[0])
    }


def odds_map_sum_status(
    odds_map: dict[str, Any] | None,
    *,
    min_sum: float = 90.0,
    max_sum: float = 110.0,
) -> tuple[float, str]:
    numeric_values: list[float] = []
    for value in (odds_map or {}).values():
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            continue
    if len(numeric_values) < 2:
        return round(sum(numeric_values), 2), "insufficient_entries"
    total = round(sum(numeric_values), 2)
    if min_sum <= total <= max_sum:
        return total, "ok"
    return total, "out_of_band"


def _is_uuid_like(value: str | None) -> bool:
    return bool(UUID_RE.match(str(value or "").strip()))


def _is_active_status(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"active", "open"}


def _parse_timestamp(value: Any) -> datetime:
    if value in (None, ""):
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    if text.isdigit():
        number = int(text)
        # handle epoch millis
        if number > 1_000_000_000_000:
            number = number // 1000
        try:
            return datetime.fromtimestamp(number, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _relative_path(path: Path) -> str:
    return display_path(path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_settlement_source_names(series_payload: dict[str, Any] | None) -> list[str]:
    names: list[str] = []
    for source in (series_payload or {}).get("settlement_sources") or []:
        if not isinstance(source, dict):
            continue
        name = str(source.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _load_series_lookup(series_dirs: tuple[Path, ...] = DEFAULT_SERIES_DIRS) -> dict[str, dict[str, Any]]:
    selected: dict[str, tuple[dict[str, Any], datetime, int, str]] = {}
    for source_priority, directory in enumerate(series_dirs):
        if not directory.exists():
            continue
        for file_path in sorted(directory.glob("*.json")):
            payload = _load_json(file_path)
            ticker = str(payload.get("ticker") or "").strip()
            if not ticker:
                continue
            updated_ts = _parse_timestamp(payload.get("last_updated_ts") or payload.get("updated_time"))
            candidate = (payload, updated_ts, source_priority, _relative_path(file_path))
            existing = selected.get(ticker)
            if existing is None:
                selected[ticker] = candidate
                continue
            if (candidate[1], -candidate[2], candidate[3]) > (existing[1], -existing[2], existing[3]):
                selected[ticker] = candidate
    return {ticker: payload for ticker, (payload, _updated, _priority, _path) in selected.items()}


def _iter_market_payloads(
    market_dirs: tuple[Path, ...] = DEFAULT_MARKET_DIRS,
) -> tuple[list[tuple[Path, dict[str, Any], str, int]], dict[str, Any]]:
    candidates: dict[str, list[tuple[Path, dict[str, Any], str, int]]] = defaultdict(list)
    scanned_market_files = 0
    discovered_markets = 0

    for source_priority, directory in enumerate(market_dirs):
        if not directory.exists():
            continue
        for file_path in sorted(directory.glob("market_*.json")):
            scanned_market_files += 1
            payload = _load_json(file_path)
            ticker = str(payload.get("ticker") or "").strip()
            if not ticker:
                continue
            discovered_markets += 1
            candidates[ticker].append((file_path, payload, _relative_path(directory), source_priority))

    selected_rows: list[tuple[Path, dict[str, Any], str, int]] = []
    for ticker, options in candidates.items():
        selected_rows.append(
            max(
                options,
                key=lambda item: (
                    _parse_timestamp(item[1].get("updated_time")),
                    1 if _is_active_status(item[1].get("status")) else 0,
                    -item[3],
                    _relative_path(item[0]),
                    ticker,
                ),
            )
        )
    selected_rows.sort(key=lambda item: str(item[1].get("ticker") or "").strip())
    stats = {
        "scanned_market_files": scanned_market_files,
        "discovered_markets": discovered_markets,
        "selected_market_count": len(selected_rows),
    }
    return selected_rows, stats


def _infer_entity_name(payload: dict[str, Any]) -> str | None:
    custom_strike = payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        for key in ("Candidate", "candidate", "Nominee", "Person", "politician", "Politician", "Individual", "Party", "political_party"):
            value = str(custom_strike.get(key) or "").strip()
            if value and not _is_uuid_like(value):
                return value
    for key in ("yes_sub_title", "title"):
        value = str(payload.get(key) or "").strip()
        if value and not _is_uuid_like(value):
            return value
    return None


def _derive_entity_name(payload: dict[str, Any]) -> tuple[str | None, str]:
    custom_strike = payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        for key in ("Candidate", "candidate", "Nominee", "Person", "politician", "Politician", "Individual"):
            value = str(custom_strike.get(key) or "").strip()
            if value and not _is_uuid_like(value):
                return value, f"custom_strike.{key}"
        for key in ("Party", "political_party"):
            value = str(custom_strike.get(key) or "").strip()
            if value and not _is_uuid_like(value):
                return value, f"custom_strike.{key}"
    for key in ("yes_sub_title", "title"):
        value = str(payload.get(key) or "").strip()
        if value and not _is_uuid_like(value):
            return value, key
    return None, "none"


def _infer_party_from_tickers(*ticker_values: str) -> str | None:
    for raw in ticker_values:
        text = str(raw or "").strip().upper()
        if not text:
            continue
        for pattern in TICKER_PARTY_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            for value in match.groups():
                if value and value.upper() in {"D", "R"}:
                    return value.upper()
    return None


def _infer_party_from_fields(payload: dict[str, Any], title: str, series_title: str) -> str | None:
    custom_strike = payload.get("custom_strike")
    if isinstance(custom_strike, dict):
        party = normalize_party(custom_strike.get("Party"))
        if party:
            return party
        party = normalize_party(custom_strike.get("political_party"))
        if party:
            return party
    combined = f"{title} {series_title}".upper()
    if "DEMOCRAT" in combined or "DEMOCRATIC" in combined:
        return "D"
    if "REPUBLICAN" in combined or "GOP" in combined:
        return "R"
    return None


def _derive_party_lane(payload: dict[str, Any], *, title: str, series_title: str, event_ticker: str, ticker: str, series_ticker: str, metadata_party: str | None) -> tuple[str | None, str]:
    ticker_party = _infer_party_from_tickers(event_ticker, ticker, series_ticker)
    if ticker_party:
        return ticker_party, "ticker"
    if metadata_party:
        return metadata_party, "metadata"
    field_party = _infer_party_from_fields(payload, title, series_title)
    if field_party:
        return field_party, "fields"
    return None, "none"


def _infer_round(primary_detected: bool, title: str, rules_primary: str) -> str:
    if primary_detected:
        return "primary"
    if RUNOFF_TEXT_RE.search(f"{title} {rules_primary}"):
        return "runoff"
    return "general"


def _infer_market_role(
    primary_detected: bool,
    round_name: str,
    entity_name: str | None,
    title: str,
    rules_primary: str,
    *,
    party_lane: str | None,
) -> str:
    combined = f"{title} {rules_primary}".upper()
    entity_party = normalize_party(entity_name)
    if primary_detected:
        if _extract_advance_count(rules_primary, title) > 1:
            return "candidate_advance"
        return "candidate_nominee"
    if party_lane is not None or entity_party is not None:
        return "party_winner"
    if "NOMINEE" in combined or "NOMINATION" in combined:
        return "candidate_nominee"
    if round_name == "general":
        return "candidate_winner"
    return "candidate_winner"


def _extract_key_party(normalized_contest_key: str | None) -> str | None:
    text = str(normalized_contest_key or "").strip().upper()
    if not text:
        return None
    match = re.search(r":([DR])$", text)
    if match:
        return match.group(1)
    return None


def _repair_primary_contest_key(key: str | None, *, seat: str, cycle_year: int | None, party: str | None) -> str:
    if key:
        if party and _extract_key_party(key):
            return re.sub(r":[DR]$", f":{party}", key)
        if party and not _extract_key_party(key):
            return f"{key}:{party}"
        return key
    cycle = cycle_year or 2026
    lane = party or "OTH"
    return f"US-REP:{seat}:{cycle}:{lane}"


def _contest_row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("seat") or "",
        row.get("round") or "",
        row.get("party_lane") or "",
        row.get("market_role") or "",
        row.get("normalized_contest_key") or "",
    )


def _apply_general_election_aggregation(contest_rows: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, Any, str], list[dict[str, Any]]] = defaultdict(list)
    for contest in contest_rows:
        round_name = str(contest.get("round") or "").strip().lower()
        role = str(contest.get("market_role") or "").strip().lower()
        seat = normalize_seat_id(contest.get("seat"))
        if round_name != "general" or role not in {"party_winner", "candidate_winner"} or not seat:
            continue
        grouped[(seat, contest.get("cycle_year"), "general")].append(contest)

    for contests in grouped.values():
        market_by_ticker: dict[str, dict[str, Any]] = {}
        for contest in contests:
            for market in contest.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                ticker = str(market.get("marketTicker") or "").strip()
                if not ticker:
                    continue
                market_by_ticker[ticker] = market
        aggregate_markets = sorted(market_by_ticker.values(), key=lambda item: str(item.get("marketTicker") or ""))
        aggregate_map = build_entity_odds_map(aggregate_markets)
        aggregate_sum, aggregate_status = odds_map_sum_status(aggregate_map)
        aggregate_tickers = [str(item.get("marketTicker") or "").strip() for item in aggregate_markets if str(item.get("marketTicker") or "").strip()]
        for contest in contests:
            contest["general_election_odds_map"] = aggregate_map
            contest["general_election_odds_sum"] = aggregate_sum
            contest["general_election_odds_sum_status"] = aggregate_status
            contest["general_election_market_tickers"] = aggregate_tickers
            contest["general_election_market_count"] = len(aggregate_tickers)
            contest["odds_map_sum"] = aggregate_sum
            contest["odds_map_sum_status"] = aggregate_status


def _serialize_for_csv(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        for key, value in list(out.items()):
            if isinstance(value, (dict, list)):
                out[key] = json.dumps(value, sort_keys=True)
        serialized.append(out)
    return serialized


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    serialized = _serialize_for_csv(rows)
    fieldnames = sorted({key for row in serialized for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in serialized:
            writer.writerow(row)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_row_payload_json(path: Path, *, rows: list[dict[str, Any]], summary: dict[str, Any], report: dict[str, Any]) -> None:
    _write_json(
        path,
        {
            "generatedAt": summary.get("generated_at"),
            "summary": {
                "row_count": len(rows),
                "matched_count": report.get("matched_count"),
                "unmatched_count": report.get("unmatched_count"),
                "ambiguous_count": report.get("ambiguous_count"),
                "positive_odds_unmatched_count": report.get("positive_odds_unmatched_count"),
                "positive_odds_ambiguous_count": report.get("positive_odds_ambiguous_count"),
            },
            "rows": rows,
        },
    )


def _is_house_outcome_market(*, market_role: str, office_family: str | None, round_name: str, title: str, rules_primary: str) -> bool:
    if office_family != "US-REP":
        return False
    if NON_OUTCOME_TEXT_RE.search(f"{title} {rules_primary}"):
        return False
    if market_role in {"candidate_nominee", "candidate_winner", "candidate_advance"}:
        return True
    if market_role == "party_winner" and round_name == "general":
        return True
    return False


def _summarize_market_for_contest(market: dict[str, Any]) -> dict[str, Any]:
    return {
        "marketTicker": market.get("market_ticker"),
        "eventTicker": market.get("event_ticker"),
        "seriesTicker": market.get("series_ticker"),
        "kalshiUrl": build_kalshi_event_url(
            market.get("series_ticker"),
            market.get("series_title"),
            market.get("event_ticker"),
        ),
        "entityName": market.get("entity_name"),
        "partyLane": market.get("party_lane"),
        "status": market.get("status"),
        "oddsPercent": market.get("odds_percent"),
        "closeTime": market.get("close_time"),
        "sourceFile": market.get("source_file"),
        "sourceDir": market.get("source_dir"),
        "sourcePriority": market.get("source_priority"),
        "entityDerivation": market.get("entity_derivation"),
        "partyDerivation": market.get("party_derivation"),
    }


def build_kalshi_us_rep_contest_rows(
    market_dirs: tuple[Path, ...] = DEFAULT_MARKET_DIRS,
    series_dirs: tuple[Path, ...] = DEFAULT_SERIES_DIRS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    series_lookup = _load_series_lookup(series_dirs)
    market_payloads, source_stats = _iter_market_payloads(market_dirs)

    markets: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    for file_path, payload, source_dir, source_priority in market_payloads:
        ticker = str(payload.get("ticker") or "").strip()
        event_ticker_raw = str(payload.get("event_ticker") or "").strip()
        title = str(payload.get("title") or "").strip()
        rules_primary = str(payload.get("rules_primary") or "").strip()

        ticker_context = parse_kalshi_ticker_hierarchy(event_ticker=event_ticker_raw, market_ticker=ticker)
        series_ticker = ticker_context.parent_series_ticker or ""
        event_ticker = ticker_context.child_event_ticker or event_ticker_raw
        series_payload = series_lookup.get(series_ticker) or {}
        series_title = str(series_payload.get("title") or "").strip()
        settlement_source_names = _collect_settlement_source_names(series_payload)

        parsed = parse_kalshi_election_metadata(
            event_ticker=event_ticker,
            market_ticker=ticker,
            series_ticker=series_ticker,
            title=title,
            rules_primary=rules_primary,
            series_title=series_title,
            settlement_source_names=settlement_source_names,
        )
        seat = normalize_seat_id(parsed.seat_id)
        inferred_house_hint = bool(HOUSE_HINT_RE.search(f"{title} {rules_primary} {ticker} {event_ticker} {series_ticker}".upper()))
        if not seat:
            if inferred_house_hint or str(parsed.office_family or "").upper() == "US-REP":
                violations.append(
                    {
                        "type": "missing_seat_id",
                        "market_ticker": ticker,
                        "event_ticker": event_ticker,
                        "series_ticker": series_ticker,
                        "title": title,
                        "source_file": _relative_path(file_path),
                    }
                )
            continue
        office_family = parsed.office_family
        primary_event = parse_primary_election_event(
            event_ticker=event_ticker or series_ticker,
            parent_series_ticker=series_ticker,
            parent_series_title=series_title,
            settlement_source_names=settlement_source_names,
        )

        metadata_party = normalize_party(parsed.party)
        party_lane, party_derivation = _derive_party_lane(
            payload,
            title=title,
            series_title=series_title,
            event_ticker=event_ticker,
            ticker=ticker,
            series_ticker=series_ticker,
            metadata_party=metadata_party,
        )
        round_name = _infer_round(primary_event is not None, title, rules_primary)
        entity_name, entity_derivation = _derive_entity_name(payload)
        market_role = _infer_market_role(
            primary_event is not None,
            round_name,
            entity_name,
            title,
            rules_primary,
            party_lane=party_lane,
        )
        if not _is_house_outcome_market(
            market_role=market_role,
            office_family=office_family,
            round_name=round_name,
            title=title,
            rules_primary=rules_primary,
        ):
            continue

        normalized_contest_key = primary_event.normalized_contest_key if primary_event else parsed.normalized_contest_key
        key_party = _extract_key_party(normalized_contest_key)
        if round_name == "primary":
            repaired = _repair_primary_contest_key(
                normalized_contest_key,
                seat=seat,
                cycle_year=parsed.cycle_year,
                party=party_lane,
            )
            repaired_key_party = _extract_key_party(repaired)
            if repaired_key_party and party_lane and repaired_key_party != party_lane:
                violations.append(
                    {
                        "type": "primary_party_key_mismatch",
                        "seat": seat,
                        "market_ticker": ticker,
                        "event_ticker": event_ticker,
                        "series_ticker": series_ticker,
                        "party_from_key": key_party,
                        "party_from_precedence": party_lane,
                        "normalized_contest_key_original": normalized_contest_key or "",
                        "normalized_contest_key_repaired": repaired,
                        "source_file": _relative_path(file_path),
                    }
                )
            normalized_contest_key = repaired

        odds_percent = parse_odds_percent(payload.get("last_price_dollars"))
        if not odds_percent:
            yes_ask = parse_odds_percent(payload.get("yes_ask_dollars"))
            yes_bid = parse_odds_percent(payload.get("yes_bid_dollars"))
            if yes_ask is not None and yes_bid is not None:
                odds_percent = round((yes_ask + yes_bid) / 2, 2)
        status = str(payload.get("status") or "").strip().lower() or None
        close_time = payload.get("close_time")
        source_file = _relative_path(file_path)
        advance_count = _extract_advance_count(rules_primary, title) if round_name == "primary" else 1
        markets.append(
            {
                "market_ticker": ticker,
                "event_ticker": event_ticker or None,
                "series_ticker": series_ticker or None,
                "series_title": series_title or None,
                "seat": seat,
                "state": seat.split("-", 1)[0] if "-" in seat else None,
                "cycle_year": parsed.cycle_year,
                "round": round_name,
                "party_lane": party_lane,
                "market_role": market_role,
                "advance_count": advance_count,
                "normalized_contest_key": normalized_contest_key,
                "entity_name": entity_name,
                "status": status,
                "odds_percent": odds_percent,
                "close_time": close_time,
                "source_file": source_file,
                "source_dir": source_dir,
                "source_priority": source_priority,
                "title": title,
                "entity_derivation": entity_derivation,
                "party_derivation": party_derivation,
            }
        )

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for market in markets:
        key = (
            market.get("seat"),
            market.get("cycle_year"),
            market.get("round"),
            market.get("party_lane"),
            market.get("market_role"),
            market.get("normalized_contest_key"),
        )
        grouped[key].append(market)

    contest_rows: list[dict[str, Any]] = []
    for key, grouped_markets in grouped.items():
        seat, cycle_year, round_name, party_lane, market_role, normalized_contest_key = key
        sorted_markets = sorted(
            grouped_markets,
            key=lambda item: (
                item.get("status") != "active",
                -(item.get("odds_percent") or 0.0),
                item.get("market_ticker") or "",
            ),
        )
        market_tickers = [item.get("market_ticker") for item in sorted_markets if item.get("market_ticker")]
        series_tickers = sorted({item.get("series_ticker") for item in sorted_markets if item.get("series_ticker")})
        entity_names = sorted({item.get("entity_name") for item in sorted_markets if item.get("entity_name")})
        contest_id = normalized_contest_key or f"US-REP:{seat}:{cycle_year or 'unknown'}:{round_name}:{party_lane or 'OTH'}:{market_role}"
        contest_advance_count = max((m.get("advance_count") or 1) for m in sorted_markets)
        contest_rows.append(
            {
                "contest_id": contest_id,
                "seat": seat,
                "state": seat.split("-", 1)[0] if "-" in seat else "",
                "cycle_year": cycle_year,
                "round": round_name,
                "party_lane": party_lane,
                "market_role": market_role,
                "advance_count": contest_advance_count,
                "normalized_contest_key": normalized_contest_key,
                "market_count": len(market_tickers),
                "market_tickers": market_tickers,
                "series_tickers": series_tickers,
                "entity_names": entity_names,
                "has_active_market": any((item.get("status") or "").lower() == "active" for item in sorted_markets),
                "markets": [_summarize_market_for_contest(item) for item in sorted_markets],
                "source_files": sorted({item.get("source_file") for item in sorted_markets if item.get("source_file")}),
                "source_dirs": sorted({item.get("source_dir") for item in sorted_markets if item.get("source_dir")}),
                "source_priorities": sorted({item.get("source_priority") for item in sorted_markets if item.get("source_priority") is not None}),
            }
        )

    for contest in contest_rows:
        odds_map = build_entity_odds_map(contest.get("markets"))
        odds_sum, sum_status = odds_map_sum_status(odds_map)
        contest["entity_odds_map"] = odds_map
        contest["odds_map_sum"] = odds_sum
        contest["odds_map_sum_status"] = sum_status

    _apply_general_election_aggregation(contest_rows)

    contest_rows.sort(key=_contest_row_sort_key)

    # Advance sum check: for multi-winner primaries, group markets by event_ticker
    # across all contests and verify sum of yes_prices ≈ advance_count × 100 ± 20%.
    by_event_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for market in markets:
        if (market.get("advance_count") or 1) > 1:
            ev = market.get("event_ticker") or market.get("market_ticker") or ""
            by_event_ticker[ev].append(market)
    for event_ticker_key, event_markets in by_event_ticker.items():
        event_advance_count = max(m.get("advance_count") or 1 for m in event_markets)
        odds_map = {
            str(m["entity_name"]): float(m["odds_percent"])
            for m in event_markets
            if m.get("entity_name") and m.get("odds_percent") is not None
        }
        expected = event_advance_count * 100.0
        tolerance = event_advance_count * 20.0
        _, sum_status = odds_map_sum_status(odds_map, min_sum=expected - tolerance, max_sum=expected + tolerance)
        if sum_status == "out_of_band":
            violations.append(
                {
                    "type": "advance_sum_out_of_band",
                    "event_ticker": event_ticker_key,
                    "advance_count": event_advance_count,
                    "observed_sum": round(sum(odds_map.values()), 1),
                    "expected_range": [event_advance_count * 80, event_advance_count * 120],
                }
            )

    validation_violations = validate_kalshi_us_rep_contests(contest_rows, violations)
    violations = validation_violations
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned_markets": source_stats.get("scanned_market_files", 0),
        "discovered_markets": source_stats.get("discovered_markets", 0),
        "selected_markets": source_stats.get("selected_market_count", 0),
        "included_markets": len(markets),
        "contest_count": len(contest_rows),
        "violation_count": len(violations),
    }
    return contest_rows, violations, summary


def validate_kalshi_us_rep_contests(
    contests: list[dict[str, Any]],
    existing_violations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = [dict(v) for v in (existing_violations or []) if isinstance(v, dict)]
    seen: set[tuple[Any, ...]] = {
        (
            v.get("type"),
            v.get("market_ticker"),
            v.get("contest_id"),
            v.get("seat"),
            v.get("source_file"),
        )
        for v in combined
    }

    def add_violation(row: dict[str, Any]) -> None:
        signature = (
            row.get("type"),
            row.get("market_ticker"),
            row.get("contest_id"),
            row.get("seat"),
            row.get("source_file"),
        )
        if signature in seen:
            return
        seen.add(signature)
        combined.append(row)

    for contest in contests:
        seat = normalize_seat_id(contest.get("seat"))
        contest_id = str(contest.get("contest_id") or "")
        round_name = str(contest.get("round") or "").lower()
        role = str(contest.get("market_role") or "").lower()
        normalized_key = str(contest.get("normalized_contest_key") or "")
        party_lane = str(contest.get("party_lane") or "").upper()

        if not seat:
            add_violation(
                {
                    "type": "missing_seat_id",
                    "contest_id": contest_id,
                    "seat": contest.get("seat"),
                }
            )

        if round_name == "primary" and party_lane in {"D", "R"} and normalized_key and not normalized_key.upper().endswith(f":{party_lane}"):
            add_violation(
                {
                    "type": "primary_party_key_mismatch",
                    "contest_id": contest_id,
                    "seat": seat,
                    "normalized_contest_key": normalized_key,
                    "party_lane": party_lane,
                }
            )

        # candidate_advance markets are NOT mutually exclusive (multiple can resolve YES);
        # their integrity is checked separately via advance_sum_out_of_band.
        mutually_exclusive = role in {"candidate_nominee", "candidate_winner", "party_winner"}
        sum_status = str(contest.get("odds_map_sum_status") or "")
        sum_value = contest.get("odds_map_sum")
        if round_name == "general" and role in {"candidate_winner", "party_winner"}:
            sum_status = str(contest.get("general_election_odds_sum_status") or sum_status)
            sum_value = contest.get("general_election_odds_sum", sum_value)
        if mutually_exclusive and sum_status == "out_of_band":
            add_violation(
                {
                    "type": "odds_map_out_of_band",
                    "contest_id": contest_id,
                    "seat": seat,
                    "round": round_name,
                    "market_role": role,
                    "odds_map_sum": sum_value,
                    "odds_map_sum_status": sum_status,
                }
            )

        for market in contest.get("markets") or []:
            if not isinstance(market, dict):
                continue
            entity = str(market.get("entityName") or "").strip()
            if entity and _is_uuid_like(entity):
                add_violation(
                    {
                        "type": "uuid_entity_name",
                        "contest_id": contest_id,
                        "seat": seat,
                        "market_ticker": market.get("marketTicker"),
                        "entity_name": entity,
                        "source_file": market.get("sourceFile"),
                    }
                )

    combined.sort(key=lambda row: (str(row.get("type") or ""), str(row.get("seat") or ""), str(row.get("contest_id") or ""), str(row.get("market_ticker") or "")))
    return combined


def build_kalshi_us_rep_contest_index(
    output_json: Path = DEFAULT_OUTPUT_INDEX_JSON,
    output_csv: Path = DEFAULT_OUTPUT_INDEX_CSV,
    output_violations_csv: Path = DEFAULT_OUTPUT_VIOLATIONS_CSV,
    output_violations_json: Path = DEFAULT_OUTPUT_VIOLATIONS_JSON,
    output_candidate_winner_json: Path = DEFAULT_OUTPUT_HOUSE_CANDIDATE_WINNER_JSON,
    output_candidate_winner_csv: Path = DEFAULT_OUTPUT_HOUSE_CANDIDATE_WINNER_CSV,
    output_candidate_nominee_json: Path = DEFAULT_OUTPUT_HOUSE_CANDIDATE_NOMINEE_JSON,
    output_candidate_nominee_csv: Path = DEFAULT_OUTPUT_HOUSE_CANDIDATE_NOMINEE_CSV,
    output_candidate_match_report_json: Path = DEFAULT_OUTPUT_HOUSE_CANDIDATE_MATCH_REPORT_JSON,
    output_candidate_match_report_csv: Path = DEFAULT_OUTPUT_HOUSE_CANDIDATE_MATCH_REPORT_CSV,
    ballotpedia_primary_csv: Path = DEFAULT_BALLOTPEDIA_HOUSE_PRIMARY_CSV,
    ballotpedia_runoff_csv: Path = DEFAULT_BALLOTPEDIA_HOUSE_RUNOFF_CSV,
    ballotpedia_general_csv: Path = DEFAULT_BALLOTPEDIA_HOUSE_GENERAL_CSV,
    market_dirs: tuple[Path, ...] = DEFAULT_MARKET_DIRS,
    series_dirs: tuple[Path, ...] = DEFAULT_SERIES_DIRS,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    contests, violations, summary = build_kalshi_us_rep_contest_rows(market_dirs=market_dirs, series_dirs=series_dirs)
    payload = {
        "generatedAt": summary["generated_at"],
        "summary": summary,
        "marketDirs": [_relative_path(path) for path in market_dirs],
        "seriesDirs": [_relative_path(path) for path in series_dirs],
        "contests": contests,
    }

    candidate_winner_rows = build_candidate_market_rows(
        contests=contests,
        office="us_house",
        market_type_field="market_role",
        market_type_value="candidate_winner",
        seat_field="seat",
        party_field="party_lane",
        ballotpedia_primary_csv=ballotpedia_primary_csv,
        ballotpedia_runoff_csv=ballotpedia_runoff_csv,
        ballotpedia_general_csv=ballotpedia_general_csv,
    )
    candidate_nominee_rows = build_candidate_market_rows(
        contests=contests,
        office="us_house",
        market_type_field="market_role",
        market_type_value="candidate_nominee",
        seat_field="seat",
        party_field="party_lane",
        ballotpedia_primary_csv=ballotpedia_primary_csv,
        ballotpedia_runoff_csv=ballotpedia_runoff_csv,
        ballotpedia_general_csv=ballotpedia_general_csv,
    )
    candidate_winner_report = build_candidate_match_report(candidate_winner_rows, office="us_house", market_type="candidate_winner")
    candidate_nominee_report = build_candidate_match_report(candidate_nominee_rows, office="us_house", market_type="candidate_nominee")
    def _odds_value(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    combined_unresolved = list(candidate_winner_report.get("unresolved_examples") or []) + list(
        candidate_nominee_report.get("unresolved_examples") or []
    )
    combined_unresolved.sort(
        key=lambda row: (
            -_odds_value(row.get("oddsPercent")),
            str(row.get("seat") or ""),
            str(row.get("kalshi_candidate_name") or ""),
        )
    )
    blocking_count = int(candidate_winner_report.get("blocking_issue_count") or 0) + int(
        candidate_nominee_report.get("blocking_issue_count") or 0
    )
    ambiguous_auto_match_count = int(candidate_winner_report.get("ambiguous_auto_match_issue_count") or 0) + int(
        candidate_nominee_report.get("ambiguous_auto_match_issue_count") or 0
    )
    candidate_match_report = {
        "generatedAt": summary["generated_at"],
        "office": "us_house",
        "unresolved_odds_threshold": 2.0,
        "blocking_issue_count": blocking_count,
        "ambiguous_auto_match_issue_count": ambiguous_auto_match_count,
        "top_unresolved_examples": combined_unresolved[:200],
        "candidate_winner": candidate_winner_report,
        "candidate_nominee": candidate_nominee_report,
    }

    _write_row_payload_json(output_candidate_winner_json, rows=candidate_winner_rows, summary=summary, report=candidate_winner_report)
    _write_row_payload_json(output_candidate_nominee_json, rows=candidate_nominee_rows, summary=summary, report=candidate_nominee_report)
    _write_csv(output_candidate_winner_csv, candidate_winner_rows)
    _write_csv(output_candidate_nominee_csv, candidate_nominee_rows)
    _write_json(output_candidate_match_report_json, candidate_match_report)
    _write_csv(output_candidate_match_report_csv, [candidate_winner_report, candidate_nominee_report])

    payload["artifacts"] = {
        "candidate_winner_json": _relative_path(output_candidate_winner_json),
        "candidate_winner_csv": _relative_path(output_candidate_winner_csv),
        "candidate_nominee_json": _relative_path(output_candidate_nominee_json),
        "candidate_nominee_csv": _relative_path(output_candidate_nominee_csv),
        "candidate_match_report_json": _relative_path(output_candidate_match_report_json),
        "candidate_match_report_csv": _relative_path(output_candidate_match_report_csv),
    }
    if blocking_count > 0:
        violations.append(
            {
                "type": "candidate_match_blocking_unresolved",
                "office": "us_house",
                "threshold": 2.0,
                "count": blocking_count,
            }
        )
    if ambiguous_auto_match_count > 0:
        violations.append(
            {
                "type": "candidate_match_ambiguous_auto_match",
                "office": "us_house",
                "count": ambiguous_auto_match_count,
            }
        )

    _write_json(output_json, payload)
    _write_csv(output_csv, contests)
    _write_csv(output_violations_csv, violations)
    _write_json(output_violations_json, {"generatedAt": summary["generated_at"], "count": len(violations), "violations": violations})
    if strict and violations:
        raise RuntimeError(f"Kalshi US-REP contest integrity validation failed with {len(violations)} violation(s)")
    return payload


def load_kalshi_us_rep_contests(index_json: Path = DEFAULT_OUTPUT_INDEX_JSON, *, use_cached: bool = False) -> list[dict[str, Any]]:
    if use_cached and index_json.exists():
        payload = _load_json(index_json)
        contests = payload.get("contests")
        if isinstance(contests, list):
            return [dict(row) for row in contests if isinstance(row, dict)]
    contests, _violations, _summary = build_kalshi_us_rep_contest_rows()
    return contests


def build_kalshi_contest_indexes(contests: list[dict[str, Any]]) -> dict[str, Any]:
    by_ticker: dict[str, dict[str, Any]] = {}
    by_seat_round_party: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    by_seat_round: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    normalized_entity_by_ticker: dict[str, str] = {}

    for contest in contests:
        seat = normalize_seat_id(contest.get("seat"))
        round_name = str(contest.get("round") or "").strip().lower()
        party_lane = str(contest.get("party_lane") or "").strip().upper()
        if not seat or not round_name:
            continue
        by_seat_round[(seat, round_name)].append(contest)
        if party_lane:
            by_seat_round_party[(seat, round_name, party_lane)].append(contest)
        normalized_entity_candidates = {
            str(market.get("marketTicker") or "").strip(): normalize_name(market.get("entityName"))
            for market in contest.get("markets") or []
            if isinstance(market, dict) and str(market.get("marketTicker") or "").strip()
        }
        for ticker in contest.get("market_tickers") or []:
            ticker_text = str(ticker)
            by_ticker[ticker_text] = contest
            normalized = normalized_entity_candidates.get(ticker_text)
            if normalized:
                normalized_entity_by_ticker[ticker_text] = normalized

    for values in by_seat_round.values():
        values.sort(
            key=lambda row: (
                (not bool(row.get("has_active_market"))),
                -(int(row.get("cycle_year") or 0)),
                -(row.get("market_count") or 0),
                row.get("contest_id") or "",
            )
        )
    for values in by_seat_round_party.values():
        values.sort(
            key=lambda row: (
                (not bool(row.get("has_active_market"))),
                -(int(row.get("cycle_year") or 0)),
                -(row.get("market_count") or 0),
                row.get("contest_id") or "",
            )
        )

    return {
        "by_ticker": by_ticker,
        "by_seat_round_party": by_seat_round_party,
        "by_seat_round": by_seat_round,
        "normalized_entity_by_ticker": normalized_entity_by_ticker,
    }


def select_contest_for_row(
    indexes: dict[str, Any],
    *,
    seat: str,
    round_name: str,
    party_lane: str | None,
) -> tuple[dict[str, Any] | None, str]:
    seat_norm = normalize_seat_id(seat)
    round_norm = str(round_name or "").strip().lower()
    party_norm = normalize_party(party_lane) or str(party_lane or "").strip().upper()
    if seat_norm and round_norm and party_norm:
        options = indexes["by_seat_round_party"].get((seat_norm, round_norm, party_norm)) or []
        if options:
            return options[0], "seat_round_party"
    if seat_norm and round_norm:
        options = indexes["by_seat_round"].get((seat_norm, round_norm)) or []
        if options:
            return options[0], "seat_round"
    return None, "none"


def _candidate_market_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        (item.get("status") or "") != "active",
        -(item.get("oddsPercent") or 0.0),
        item.get("marketTicker") or "",
    )


def match_candidate_to_contest_markets(
    contest: dict[str, Any] | None,
    candidate_name: str,
    *,
    normalized_entity_by_ticker: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str, float]:
    if contest is None:
        return [], "no_contest", 0.0
    candidate_norm = normalize_name(candidate_name)
    if not candidate_norm:
        return [], "blank_name", 0.0
    exact: list[dict[str, Any]] = []
    fuzzy: list[tuple[float, dict[str, Any]]] = []
    for market in contest.get("markets") or []:
        ticker = str(market.get("marketTicker") or "").strip()
        entity = ""
        if normalized_entity_by_ticker is not None and ticker:
            entity = normalized_entity_by_ticker.get(ticker) or ""
        if not entity:
            entity = normalize_name(market.get("entityName"))
        if not entity:
            continue
        if entity == candidate_norm:
            exact.append(market)
            continue
        candidate_tokens = set(candidate_norm.split())
        entity_tokens = set(entity.split())
        if not candidate_tokens or not entity_tokens:
            continue
        overlap = len(candidate_tokens & entity_tokens)
        union = len(candidate_tokens | entity_tokens)
        score = overlap / union if union else 0.0
        if score >= 0.8:
            fuzzy.append((score, market))
    if exact:
        sorted_exact = sorted(exact, key=_candidate_market_sort_key)
        return sorted_exact, "exact_entity_name", 1.0
    if fuzzy:
        fuzzy.sort(key=lambda item: (-item[0],) + _candidate_market_sort_key(item[1]))
        return [item[1] for item in fuzzy], "fuzzy_entity_name", round(float(fuzzy[0][0]), 4)
    return [], "no_entity_match", 0.0


def summarize_contest(contest: dict[str, Any] | None) -> dict[str, Any]:
    if not contest:
        return {}
    return {
        "contestId": contest.get("contest_id"),
        "round": contest.get("round"),
        "partyLane": contest.get("party_lane"),
        "marketRole": contest.get("market_role"),
        "advanceCount": int(contest.get("advance_count") or 1),
        "normalizedContestKey": contest.get("normalized_contest_key"),
        "seriesTickers": contest.get("series_tickers") or [],
        "marketTickers": contest.get("market_tickers") or [],
        "marketCount": contest.get("market_count") or 0,
        "hasActiveMarket": bool(contest.get("has_active_market")),
    }
