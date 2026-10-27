"""Kalshi US Attorney General contest indexing and mapping helpers."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kalshi_candidate_mapping import (
    build_candidate_market_rows,
    build_candidate_match_report,
)
from house_seat_parsing import STATE_CODES, STATE_NAMES
from kalshi_metadata_parsing import build_kalshi_event_url
from ballotpedia_rollup.config import display_path
from .kalshi_ag_shared import (
    extract_cycle_year,
    extract_nom_party,
    extract_party_from_subtitle,
    extract_party_from_title,
    extract_party_suffix,
    extract_state_from_ticker,
    extract_state_from_title,
    infer_market_type,
    infer_round,
    is_ag_market,
    is_finish_position_market,
    is_non_seat_market,
    normalize_party,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent

DEFAULT_MARKET_DIRS: tuple[Path, ...] = (
    WORKSPACE_ROOT / "kalshi" / "data" / "markets",
    REPO_ROOT / "test_data" / "kalshi" / "market",
    REPO_ROOT / "test_data" / "kalshi_json_data" / "market",
)
DEFAULT_SERIES_DIRS: tuple[Path, ...] = (
    WORKSPACE_ROOT / "kalshi" / "data" / "series",
    REPO_ROOT / "test_data" / "kalshi" / "series",
    REPO_ROOT / "test_data" / "kalshi_json_data" / "series",
)

_WEB_DATA = REPO_ROOT / "apps" / "web" / "data"

DEFAULT_OVERRIDE_FILE = _WEB_DATA / "kalshi-us-attorney-general-mapping-overrides.json"
DEFAULT_OUTPUT_INDEX_JSON = _WEB_DATA / "kalshi-us-attorney-general-contest-index.json"
DEFAULT_OUTPUT_INDEX_CSV = _WEB_DATA / "kalshi-us-attorney-general-contest-index.csv"
DEFAULT_OUTPUT_VIOLATIONS_CSV = _WEB_DATA / "kalshi-us-attorney-general-contest-integrity-violations.csv"
DEFAULT_OUTPUT_VIOLATIONS_JSON = _WEB_DATA / "kalshi-us-attorney-general-contest-integrity-violations.json"
DEFAULT_OUTPUT_CANDIDATE_WINNER_JSON = _WEB_DATA / "kalshi-attorney-general-candidate-winner.json"
DEFAULT_OUTPUT_CANDIDATE_WINNER_CSV = _WEB_DATA / "kalshi-attorney-general-candidate-winner.csv"
DEFAULT_OUTPUT_PARTY_WINNER_JSON = _WEB_DATA / "kalshi-attorney-general-party-winner.json"
DEFAULT_OUTPUT_PARTY_WINNER_CSV = _WEB_DATA / "kalshi-attorney-general-party-winner.csv"
DEFAULT_OUTPUT_CANDIDATE_NOMINEE_JSON = _WEB_DATA / "kalshi-attorney-general-candidate-nominee.json"
DEFAULT_OUTPUT_CANDIDATE_NOMINEE_CSV = _WEB_DATA / "kalshi-attorney-general-candidate-nominee.csv"
DEFAULT_OUTPUT_EXCLUDED_CSV = _WEB_DATA / "kalshi-attorney-general-excluded-markets.csv"
DEFAULT_OUTPUT_UNMAPPED_CSV = _WEB_DATA / "kalshi-attorney-general-unmapped-markets.csv"
DEFAULT_OUTPUT_AMBIGUOUS_CSV = _WEB_DATA / "kalshi-attorney-general-ambiguous-markets.csv"
DEFAULT_OUTPUT_COVERAGE_JSON = _WEB_DATA / "kalshi-attorney-general-coverage-summary.json"
DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_JSON = _WEB_DATA / "kalshi-attorney-general-candidate-match-report.json"
DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_CSV = _WEB_DATA / "kalshi-attorney-general-candidate-match-report.csv"
DEFAULT_BALLOTPEDIA_AG_PRIMARY_CSV = _WEB_DATA / "ballotpedia-attorney-general-primary-election-rollup.csv"
DEFAULT_BALLOTPEDIA_AG_RUNOFF_CSV = _WEB_DATA / "ballotpedia-attorney-general-runoff-election-rollup.csv"
DEFAULT_BALLOTPEDIA_AG_GENERAL_CSV = _WEB_DATA / "ballotpedia-attorney-general-general-election-rollup.csv"


# ---------------------------------------------------------------------------
# I/O utilities
# ---------------------------------------------------------------------------

def _parse_timestamp(value: Any) -> datetime:
    if value in (None, ""):
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    serialized: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        for key, value in list(out.items()):
            if isinstance(value, (dict, list)):
                out[key] = json.dumps(value, sort_keys=True)
        serialized.append(out)
    fieldnames = sorted({key for row in serialized for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(serialized)


def _write_contest_payload_json(
    path: Path, *, contests: list[dict[str, Any]], summary: dict[str, Any]
) -> None:
    _write_json(
        path,
        {
            "generatedAt": summary.get("generated_at"),
            "summary": {
                "contest_count": len(contests),
                "included_markets": int(
                    sum(int(row.get("market_count") or 0) for row in contests)
                ),
            },
            "contests": contests,
        },
    )


def _write_row_payload_json(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    report: dict[str, Any],
) -> None:
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


def _read_series_lookup(series_dirs: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    selected: dict[str, tuple[dict[str, Any], datetime, int, str]] = {}
    for source_priority, directory in enumerate(series_dirs):
        if not directory.exists():
            continue
        for file_path in sorted(directory.glob("*.json")):
            payload = _load_json(file_path)
            ticker = str(payload.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            updated = _parse_timestamp(payload.get("last_updated_ts"))
            candidate = (payload, updated, source_priority, str(file_path))
            existing = selected.get(ticker)
            if existing is None or (
                candidate[1],
                -candidate[2],
                candidate[3],
            ) > (existing[1], -existing[2], existing[3]):
                selected[ticker] = candidate
    return {ticker: value[0] for ticker, value in selected.items()}


def _iter_markets(market_dirs: tuple[Path, ...]) -> list[tuple[Path, dict[str, Any], int]]:
    selected: dict[str, tuple[Path, dict[str, Any], int, datetime]] = {}
    for source_priority, directory in enumerate(market_dirs):
        if not directory.exists():
            continue
        for file_path in sorted(directory.glob("market_*.json")):
            payload = _load_json(file_path)
            ticker = str(payload.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            updated = _parse_timestamp(payload.get("updated_time"))
            existing = selected.get(ticker)
            candidate = (file_path, payload, source_priority, updated)
            if existing is None or (
                candidate[3],
                -candidate[2],
                str(candidate[0]),
            ) > (existing[3], -existing[2], str(existing[0])):
                selected[ticker] = candidate
    return [
        (file_path, payload, source_priority)
        for file_path, payload, source_priority, _updated in selected.values()
    ]


# ---------------------------------------------------------------------------
# Override registry
# ---------------------------------------------------------------------------

def load_override_registry(path: Path = DEFAULT_OVERRIDE_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"ticker_overrides": {}, "ticker_prefix_overrides": {}}
    payload = _load_json(path)
    return {
        "ticker_overrides": payload.get("ticker_overrides") or {},
        "ticker_prefix_overrides": payload.get("ticker_prefix_overrides") or {},
    }


def _apply_override(
    *,
    ticker: str,
    event_ticker: str,
    series_ticker: str,
    override_registry: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    direct = override_registry.get("ticker_overrides") or {}
    if ticker in direct and isinstance(direct[ticker], dict):
        return dict(direct[ticker]), f"ticker:{ticker}"
    prefixes = override_registry.get("ticker_prefix_overrides") or {}
    matches: list[tuple[str, dict[str, Any]]] = []
    for prefix, value in prefixes.items():
        if not isinstance(value, dict):
            continue
        if (
            ticker.startswith(prefix)
            or event_ticker.startswith(prefix)
            or series_ticker.startswith(prefix)
        ):
            matches.append((prefix, dict(value)))
    if not matches:
        return None, None
    if len(matches) > 1:
        return {"_ambiguous_override": [p for p, _ in matches]}, "ambiguous"
    prefix, resolved = matches[0]
    return resolved, f"prefix:{prefix}"


# ---------------------------------------------------------------------------
# Entity name extraction
# ---------------------------------------------------------------------------

def _entity_name(payload: dict[str, Any]) -> str:
    custom = payload.get("custom_strike")
    if isinstance(custom, dict):
        for key in ("Candidate", "candidate", "Nominee", "Person", "Option"):
            value = str(custom.get(key) or "").strip()
            if value:
                return value
    yes_sub_title = str(payload.get("yes_sub_title") or "").strip()
    if yes_sub_title:
        return yes_sub_title
    return str(payload.get("title") or "").strip()


def _is_party_entity(value: str | None) -> bool:
    upper = str(value or "").strip().upper()
    if not upper:
        return False
    if "PARTY" in upper:
        return True
    return upper in {
        "DEMOCRAT", "DEMOCRATS", "DEMOCRATIC", "DEMOCRATIC PARTY",
        "REPUBLICAN", "REPUBLICANS", "REPUBLICAN PARTY", "GOP",
    }


# ---------------------------------------------------------------------------
# Party extraction helpers
# ---------------------------------------------------------------------------

def _extract_party(
    ticker: str,
    market_type: str,
    subtitle: str,
    title: str,
    entity_name: str,
) -> str | None:
    if market_type == "party_winner":
        party = extract_party_suffix(ticker)
        if party:
            return party
        if _is_party_entity(entity_name):
            raw = str(entity_name).upper()
            if "DEMOCRAT" in raw:
                return "D"
            if "REPUBLICAN" in raw or "GOP" in raw:
                return "R"
        return extract_party_from_title(title)
    # candidate_nominee: party encoded in NOMR/NOMD or subtitle
    party = extract_nom_party(ticker)
    if party:
        return party
    party = extract_party_from_subtitle(subtitle)
    if party:
        return party
    # candidate_winner: party from subtitle
    return extract_party_from_subtitle(subtitle)


# ---------------------------------------------------------------------------
# Core row builder
# ---------------------------------------------------------------------------

def build_kalshi_us_ag_contest_rows(
    market_dirs: tuple[Path, ...] = DEFAULT_MARKET_DIRS,
    series_dirs: tuple[Path, ...] = DEFAULT_SERIES_DIRS,
    *,
    override_registry: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """
    Iterate all market JSON files and extract US Attorney General contest rows.

    Returns:
        (contests, violations, summary)
    """
    overrides = override_registry if override_registry is not None else load_override_registry()
    series_lookup = _read_series_lookup(series_dirs)
    selected_markets = _iter_markets(market_dirs)

    included_markets: list[dict[str, Any]] = []
    excluded_markets: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    overrides_used: list[dict[str, str]] = []

    for file_path, payload, source_priority in selected_markets:
        ticker = str(payload.get("ticker") or "").strip().upper()
        event_ticker = str(payload.get("event_ticker") or "").strip().upper()
        hierarchy_source = event_ticker or ticker
        series_ticker = hierarchy_source.split("-", 1)[0].strip().upper() if hierarchy_source else ""
        series_payload = series_lookup.get(series_ticker) or {}
        series_title = str(series_payload.get("title") or "")
        title = str(payload.get("title") or "")
        subtitle = str(payload.get("subtitle") or "")
        rules_primary = str(payload.get("rules_primary") or "")
        yes_sub_title = str(payload.get("yes_sub_title") or "")
        close_time = payload.get("close_time")

        # Gate 1: must be an attorney general market
        if not is_ag_market(ticker, title, rules_primary):
            continue

        # Gate 2: exclude non-seat meta markets
        if is_non_seat_market(ticker, title):
            excluded_markets.append(
                {
                    "market_ticker": ticker,
                    "event_ticker": event_ticker,
                    "series_ticker": series_ticker,
                    "title": title,
                    "raw_source_path": display_path(file_path),
                    "exclusion_reason": "non_seat_market",
                }
            )
            continue

        # Gate 3: exclude finish-position markets
        if is_finish_position_market(ticker, title):
            excluded_markets.append(
                {
                    "market_ticker": ticker,
                    "event_ticker": event_ticker,
                    "series_ticker": series_ticker,
                    "title": title,
                    "raw_source_path": display_path(file_path),
                    "exclusion_reason": "finish_position_market",
                }
            )
            continue

        # Apply ticker overrides
        override_data, override_key = _apply_override(
            ticker=ticker,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            override_registry=overrides,
        )
        if override_key == "ambiguous":
            violations.append(
                {
                    "type": "ambiguous_override",
                    "market_ticker": ticker,
                    "event_ticker": event_ticker,
                    "series_ticker": series_ticker,
                    "source_file": display_path(file_path),
                }
            )
            continue

        # Extract state
        state_code = extract_state_from_ticker(ticker)
        if not state_code:
            state_code = extract_state_from_title(title)
            if not state_code:
                state_code = extract_state_from_title(rules_primary)
        if not state_code or state_code not in STATE_CODES:
            excluded_markets.append(
                {
                    "market_ticker": ticker,
                    "event_ticker": event_ticker,
                    "series_ticker": series_ticker,
                    "title": title,
                    "raw_source_path": display_path(file_path),
                    "exclusion_reason": "state_unresolved",
                }
            )
            continue

        # Extract cycle year
        cycle_year = extract_cycle_year(ticker, event_ticker, series_ticker)

        # Infer round and market type
        round_name = infer_round(ticker, title, rules_primary)
        entity_name = _entity_name(payload)
        market_type = infer_market_type(ticker, title, round_name)

        # Party-winner series sometimes holds individual candidate markets.
        # Reclassify to candidate_winner when the entity is a person, not a party.
        if market_type == "party_winner" and not _is_party_entity(entity_name):
            market_type = "candidate_winner"

        # Apply overrides
        if override_data:
            state_code = str(override_data.get("state") or state_code or "").strip().upper() or state_code
            cycle_year_ov = override_data.get("cycle_year")
            if cycle_year_ov:
                cycle_year = int(cycle_year_ov)
            round_name = str(override_data.get("round") or round_name or "").strip() or round_name
            market_type_ov = str(override_data.get("market_type") or "").strip()
            if market_type_ov:
                market_type = market_type_ov
            if override_key:
                overrides_used.append({"market_ticker": ticker, "override": override_key})

        # Extract party
        party = _extract_party(ticker, market_type, subtitle, title, entity_name)

        seat_id = f"{state_code}-AG"

        if not round_name or cycle_year is None:
            violations.append(
                {
                    "type": "unresolved_mapping",
                    "market_ticker": ticker,
                    "event_ticker": event_ticker,
                    "series_ticker": series_ticker,
                    "state_code": state_code,
                    "cycle_year": cycle_year,
                    "seat_id": seat_id,
                    "round": round_name or "",
                    "party": party or "",
                    "source_file": display_path(file_path),
                }
            )
            continue

        if round_name == "primary" and party not in {"D", "R"}:
            violations.append(
                {
                    "type": "primary_missing_party_lane",
                    "market_ticker": ticker,
                    "event_ticker": event_ticker,
                    "series_ticker": series_ticker,
                    "seat_id": seat_id,
                    "source_file": display_path(file_path),
                }
            )
            continue

        odds_percent = None
        try:
            odds_percent = round(float(payload.get("last_price_dollars")) * 100, 2)
        except (TypeError, ValueError):
            odds_percent = None

        included_markets.append(
            {
                "market_ticker": ticker,
                "event_ticker": event_ticker or None,
                "series_ticker": series_ticker or None,
                "series_title": series_title or None,
                "title": title,
                "subtitle": subtitle or None,
                "rules_primary": rules_primary or None,
                "yes_sub_title": yes_sub_title or None,
                "close_time": close_time,
                "raw_source_path": display_path(file_path),
                "seat_id": seat_id,
                "state": state_code,
                "office": "AG",
                "cycle_year": cycle_year,
                "round": round_name,
                "party": party,
                "market_type": market_type,
                "entity_name": entity_name,
                "status": str(payload.get("status") or "").strip().lower() or None,
                "odds_percent": odds_percent,
                "source_file": display_path(file_path),
                "source_priority": source_priority,
                "override_applied": override_key or "",
                "mapping_confidence": "override" if override_key else "deterministic",
                "exclusion_reason": None,
            }
        )

    # Group into contests
    by_contest: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for market in included_markets:
        key = (
            market["seat_id"],
            market["cycle_year"],
            market["round"],
            market.get("party") or "",
            market["market_type"],
        )
        by_contest[key].append(market)

    contests: list[dict[str, Any]] = []
    for key, markets in by_contest.items():
        seat_id, cycle_year, round_name, party, market_type = key
        sorted_markets = sorted(
            markets,
            key=lambda item: (
                item.get("status") != "active",
                -(item.get("odds_percent") or 0.0),
                item.get("market_ticker") or "",
            ),
        )
        contest_id = f"US-AG:{seat_id}:{cycle_year}:{round_name}:{party or 'NA'}:{market_type}"
        contests.append(
            {
                "contest_id": contest_id,
                "seat_id": seat_id,
                "state": seat_id.split("-", 1)[0],
                "office": "AG",
                "cycle_year": cycle_year,
                "round": round_name,
                "party": party or None,
                "market_type": market_type,
                "market_count": len(sorted_markets),
                "has_active_market": any(
                    (item.get("status") or "").lower() == "active" for item in sorted_markets
                ),
                "markets": [
                    {
                        "marketTicker": item.get("market_ticker"),
                        "eventTicker": item.get("event_ticker"),
                        "seriesTicker": item.get("series_ticker"),
                        "kalshiUrl": build_kalshi_event_url(
                            item.get("series_ticker"),
                            item.get("series_title"),
                            item.get("event_ticker"),
                        ),
                        "entityName": item.get("entity_name"),
                        "status": item.get("status"),
                        "oddsPercent": item.get("odds_percent"),
                        "overrideApplied": item.get("override_applied"),
                        "sourceFile": item.get("source_file"),
                    }
                    for item in sorted_markets
                ],
                "source_files": sorted(
                    {item.get("source_file") for item in sorted_markets if item.get("source_file")}
                ),
            }
        )

    # Check for ambiguous multi-contest ticker mappings
    contest_by_ticker: dict[str, str] = {}
    for contest in contests:
        for market in contest.get("markets") or []:
            ticker = str(market.get("marketTicker") or "").strip()
            if not ticker:
                continue
            existing = contest_by_ticker.get(ticker)
            if existing and existing != contest["contest_id"]:
                violations.append(
                    {
                        "type": "ambiguous_market_mapping",
                        "market_ticker": ticker,
                        "contest_a": existing,
                        "contest_b": contest["contest_id"],
                    }
                )
            contest_by_ticker[ticker] = contest["contest_id"]

    contests.sort(
        key=lambda row: (
            row.get("seat_id") or "",
            row.get("round") or "",
            row.get("party") or "",
            row.get("market_type") or "",
        )
    )
    violations.sort(
        key=lambda row: (
            str(row.get("type") or ""),
            str(row.get("market_ticker") or ""),
            str(row.get("seat_id") or ""),
        )
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_markets": len(selected_markets),
        "included_markets": len(included_markets),
        "excluded_count": len(excluded_markets),
        "contest_count": len(contests),
        "violation_count": len(violations),
        "overrides_used_count": len(overrides_used),
        "by_round": dict(
            sorted(
                {
                    key: sum(1 for row in included_markets if row.get("round") == key)
                    for key in {"primary", "runoff", "general"}
                }.items()
            )
        ),
        "by_market_type": dict(
            sorted(
                {
                    key: sum(1 for row in included_markets if row.get("market_type") == key)
                    for key in {"candidate_nominee", "candidate_winner", "party_winner"}
                }.items()
            )
        ),
        "excluded_markets": excluded_markets,
    }
    return contests, violations, summary


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def build_kalshi_us_ag_contest_index(
    output_json: Path = DEFAULT_OUTPUT_INDEX_JSON,
    output_csv: Path = DEFAULT_OUTPUT_INDEX_CSV,
    output_violations_csv: Path = DEFAULT_OUTPUT_VIOLATIONS_CSV,
    output_violations_json: Path = DEFAULT_OUTPUT_VIOLATIONS_JSON,
    output_candidate_winner_json: Path = DEFAULT_OUTPUT_CANDIDATE_WINNER_JSON,
    output_candidate_winner_csv: Path = DEFAULT_OUTPUT_CANDIDATE_WINNER_CSV,
    output_party_winner_json: Path = DEFAULT_OUTPUT_PARTY_WINNER_JSON,
    output_party_winner_csv: Path = DEFAULT_OUTPUT_PARTY_WINNER_CSV,
    output_candidate_nominee_json: Path = DEFAULT_OUTPUT_CANDIDATE_NOMINEE_JSON,
    output_candidate_nominee_csv: Path = DEFAULT_OUTPUT_CANDIDATE_NOMINEE_CSV,
    output_excluded_csv: Path = DEFAULT_OUTPUT_EXCLUDED_CSV,
    output_unmapped_csv: Path = DEFAULT_OUTPUT_UNMAPPED_CSV,
    output_ambiguous_csv: Path = DEFAULT_OUTPUT_AMBIGUOUS_CSV,
    output_coverage_json: Path = DEFAULT_OUTPUT_COVERAGE_JSON,
    output_candidate_match_report_json: Path = DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_JSON,
    output_candidate_match_report_csv: Path = DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_CSV,
    ballotpedia_primary_csv: Path = DEFAULT_BALLOTPEDIA_AG_PRIMARY_CSV,
    ballotpedia_runoff_csv: Path = DEFAULT_BALLOTPEDIA_AG_RUNOFF_CSV,
    ballotpedia_general_csv: Path = DEFAULT_BALLOTPEDIA_AG_GENERAL_CSV,
    market_dirs: tuple[Path, ...] = DEFAULT_MARKET_DIRS,
    series_dirs: tuple[Path, ...] = DEFAULT_SERIES_DIRS,
    *,
    override_registry: dict[str, Any] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    contests, violations, summary = build_kalshi_us_ag_contest_rows(
        market_dirs=market_dirs,
        series_dirs=series_dirs,
        override_registry=override_registry,
    )

    payload: dict[str, Any] = {
        "generatedAt": summary["generated_at"],
        "summary": summary,
        "marketDirs": [display_path(p) for p in market_dirs],
        "seriesDirs": [display_path(p) for p in series_dirs],
        "contests": contests,
    }

    candidate_winner_contests = [r for r in contests if str(r.get("market_type") or "") == "candidate_winner"]
    party_winner_contests = [r for r in contests if str(r.get("market_type") or "") == "party_winner"]
    candidate_nominee_contests = [r for r in contests if str(r.get("market_type") or "") == "candidate_nominee"]
    unmapped_rows = [r for r in violations if str(r.get("type") or "") == "unresolved_mapping"]
    ambiguous_rows = [r for r in violations if "ambiguous" in str(r.get("type") or "")]
    excluded_rows = list(summary.get("excluded_markets") or [])

    coverage_payload: dict[str, Any] = {
        "generatedAt": summary["generated_at"],
        "counts": {
            "candidate_winner_contests": len(candidate_winner_contests),
            "party_winner_contests": len(party_winner_contests),
            "candidate_nominee_contests": len(candidate_nominee_contests),
            "general_contests": sum(1 for r in contests if str(r.get("round") or "") == "general"),
        },
        "byRound": summary.get("by_round") or {},
        "byMarketType": summary.get("by_market_type") or {},
    }

    candidate_winner_rows = build_candidate_market_rows(
        contests=contests,
        office="us_attorney_general",
        market_type_field="market_type",
        market_type_value="candidate_winner",
        seat_field="seat_id",
        party_field="party",
        ballotpedia_primary_csv=ballotpedia_primary_csv,
        ballotpedia_runoff_csv=ballotpedia_runoff_csv,
        ballotpedia_general_csv=ballotpedia_general_csv,
    )
    candidate_nominee_rows = build_candidate_market_rows(
        contests=contests,
        office="us_attorney_general",
        market_type_field="market_type",
        market_type_value="candidate_nominee",
        seat_field="seat_id",
        party_field="party",
        ballotpedia_primary_csv=ballotpedia_primary_csv,
        ballotpedia_runoff_csv=ballotpedia_runoff_csv,
        ballotpedia_general_csv=ballotpedia_general_csv,
    )

    candidate_winner_report = build_candidate_match_report(
        candidate_winner_rows, office="us_attorney_general", market_type="candidate_winner"
    )
    candidate_nominee_report = build_candidate_match_report(
        candidate_nominee_rows, office="us_attorney_general", market_type="candidate_nominee"
    )

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
    ambiguous_auto_match_count = int(
        candidate_winner_report.get("ambiguous_auto_match_issue_count") or 0
    ) + int(candidate_nominee_report.get("ambiguous_auto_match_issue_count") or 0)

    candidate_match_report: dict[str, Any] = {
        "generatedAt": summary["generated_at"],
        "office": "us_attorney_general",
        "unresolved_odds_threshold": 2.0,
        "blocking_issue_count": blocking_count,
        "ambiguous_auto_match_issue_count": ambiguous_auto_match_count,
        "top_unresolved_examples": combined_unresolved[:200],
        "candidate_winner": candidate_winner_report,
        "candidate_nominee": candidate_nominee_report,
    }

    _write_json(output_coverage_json, coverage_payload)
    _write_csv(output_unmapped_csv, unmapped_rows)
    _write_csv(output_ambiguous_csv, ambiguous_rows)
    _write_csv(output_excluded_csv, excluded_rows)
    _write_row_payload_json(
        output_candidate_winner_json,
        rows=candidate_winner_rows,
        summary=summary,
        report=candidate_winner_report,
    )
    _write_contest_payload_json(
        output_party_winner_json, contests=party_winner_contests, summary=summary
    )
    _write_row_payload_json(
        output_candidate_nominee_json,
        rows=candidate_nominee_rows,
        summary=summary,
        report=candidate_nominee_report,
    )
    _write_csv(output_candidate_winner_csv, candidate_winner_rows)
    _write_csv(output_party_winner_csv, party_winner_contests)
    _write_csv(output_candidate_nominee_csv, candidate_nominee_rows)
    _write_json(output_candidate_match_report_json, candidate_match_report)
    _write_csv(output_candidate_match_report_csv, [candidate_winner_report, candidate_nominee_report])

    if coverage_payload["counts"]["general_contests"] <= 0:
        violations.append(
            {
                "type": "general_market_coverage_missing",
                "message": "No general Attorney General contests were produced by Kalshi mapping.",
            }
        )
    if blocking_count > 0:
        violations.append(
            {
                "type": "candidate_match_blocking_unresolved",
                "office": "us_attorney_general",
                "threshold": 2.0,
                "count": blocking_count,
            }
        )
    if ambiguous_auto_match_count > 0:
        violations.append(
            {
                "type": "candidate_match_ambiguous_auto_match",
                "office": "us_attorney_general",
                "count": ambiguous_auto_match_count,
            }
        )

    payload["artifacts"] = {
        "candidate_winner_json": display_path(output_candidate_winner_json),
        "candidate_winner_csv": display_path(output_candidate_winner_csv),
        "party_winner_json": display_path(output_party_winner_json),
        "party_winner_csv": display_path(output_party_winner_csv),
        "candidate_nominee_json": display_path(output_candidate_nominee_json),
        "candidate_nominee_csv": display_path(output_candidate_nominee_csv),
        "excluded_csv": display_path(output_excluded_csv),
        "unmapped_csv": display_path(output_unmapped_csv),
        "ambiguous_csv": display_path(output_ambiguous_csv),
        "coverage_json": display_path(output_coverage_json),
        "candidate_match_report_json": display_path(output_candidate_match_report_json),
        "candidate_match_report_csv": display_path(output_candidate_match_report_csv),
    }
    payload["summary"]["violation_count"] = len(violations)
    _write_json(output_json, payload)
    _write_csv(output_csv, contests)
    _write_csv(output_violations_csv, violations)
    _write_json(
        output_violations_json,
        {
            "generatedAt": summary["generated_at"],
            "count": len(violations),
            "violations": violations,
        },
    )
    if strict and violations:
        raise RuntimeError(
            f"Kalshi US-AG contest integrity validation failed with {len(violations)} violation(s)"
        )
    return payload


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build Kalshi US Attorney General contest index")
    parser.add_argument("--strict", action="store_true", default=False, help="Fail on violations")
    args = parser.parse_args()

    try:
        payload = build_kalshi_us_ag_contest_index(strict=args.strict)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    summary = payload.get("summary") or {}
    print(f"Attorney General contest index built:")
    print(f"  Contests:  {summary.get('contest_count', 0)}")
    print(f"  Markets:   {summary.get('included_markets', 0)}")
    print(f"  Excluded:  {summary.get('excluded_count', 0)}")
    print(f"  Violations: {summary.get('violation_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
