"""Strict Kalshi US Senate contest indexing and mapping helpers."""
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
from senate_seat_ids import infer_senate_seat_id, infer_senate_seat_id_from_ticker, normalize_senate_seat_id

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

DEFAULT_OVERRIDE_FILE = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-senate-mapping-overrides.json"
DEFAULT_OUTPUT_INDEX_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-senate-contest-index.json"
DEFAULT_OUTPUT_INDEX_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-senate-contest-index.csv"
DEFAULT_OUTPUT_VIOLATIONS_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-senate-contest-integrity-violations.csv"
DEFAULT_OUTPUT_VIOLATIONS_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-us-senate-contest-integrity-violations.json"
DEFAULT_OUTPUT_CANDIDATE_WINNER_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-candidate-winner.json"
DEFAULT_OUTPUT_CANDIDATE_WINNER_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-candidate-winner.csv"
DEFAULT_OUTPUT_PARTY_WINNER_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-party-winner.json"
DEFAULT_OUTPUT_PARTY_WINNER_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-party-winner.csv"
DEFAULT_OUTPUT_CANDIDATE_NOMINEE_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-candidate-nominee.json"
DEFAULT_OUTPUT_CANDIDATE_NOMINEE_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-candidate-nominee.csv"
DEFAULT_OUTPUT_EXCLUDED_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-excluded-markets.csv"
DEFAULT_OUTPUT_UNMAPPED_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-unmapped-markets.csv"
DEFAULT_OUTPUT_AMBIGUOUS_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-ambiguous-markets.csv"
DEFAULT_OUTPUT_COVERAGE_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-coverage-summary.json"
DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_JSON = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-candidate-match-report.json"
DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-senate-candidate-match-report.csv"
DEFAULT_BALLOTPEDIA_SENATE_PRIMARY_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-senate-primary-election-rollup.csv"
DEFAULT_BALLOTPEDIA_SENATE_RUNOFF_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-senate-runoff-election-rollup.csv"
DEFAULT_BALLOTPEDIA_SENATE_GENERAL_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-senate-general-election-rollup.csv"

SENATE_PATTERN = re.compile(r"SENATE", flags=re.IGNORECASE)
OUTCOME_HINT_RE = re.compile(r"\b(NOMINEE|NOMINATION|WILL\s+.+\s+WIN)\b", flags=re.IGNORECASE)
NON_OUTCOME_RE = re.compile(
    r"\b(MARGIN OF VICTORY|TURNOUT|LOSE RE-?ELECTION|LOSEPRIMARY|FINISH 2ND|FINISH 3RD|ABOVE|BELOW|SMALLEST|ENDORSE|SWEEP|COMBO|CONTROLS|LEAD)\b",
    flags=re.IGNORECASE,
)
ROUND_PRIMARY_RE = re.compile(r"\b(NOMINEE|NOMINATION|PRIMARY)\b", flags=re.IGNORECASE)
ROUND_RUNOFF_RE = re.compile(r"\b(RUNOFF|SECOND ROUND|2ND ROUND)\b", flags=re.IGNORECASE)
ROUND_GENERAL_RE = re.compile(r"\b(GENERAL|SENATE\s+RACE|SENATE\s+ELECTION|SWORN\s+IN)\b", flags=re.IGNORECASE)
STATE_PARTY_TICKER_RE = re.compile(r"SENATE(?P<state>[A-Z]{2})(?P<tag>S?[DR])(?:-|$)", flags=re.IGNORECASE)
STATE_ONLY_TICKER_RE = re.compile(r"SENATE(?P<state>[A-Z]{2})(?:-|$)", flags=re.IGNORECASE)
PREFIX_STATE_TICKER_RE = re.compile(r"(?:^|KX)(?P<state>[A-Z]{2})SENATE(?:-|$)", flags=re.IGNORECASE)
PARTY_SUFFIX_RE = re.compile(r"-(?P<party>[DR])(?:-|$)", flags=re.IGNORECASE)
CYCLE_RE = re.compile(r"-(\d{2})(?=[A-Z]|-|$)")
CLASS_ROMAN_RE = re.compile(r"CLASS\s+(I{1,3}|IV|V|VI)\b", flags=re.IGNORECASE)
CLASS_DIGIT_RE = re.compile(r"CLASS\s+([123])\b", flags=re.IGNORECASE)
PARTY_TEXT_RE = re.compile(r"\b(DEMOCRAT|DEMOCRATIC|REPUBLICAN|GOP|PARTY)\b", flags=re.IGNORECASE)
NON_SEAT_MARKET_RE = re.compile(r"\b(NUMBER OF SEATS|SEATS\b|CONTROL|CONTROLS|SWEEP|COMBO|PORTFOLIO|POWER)\b", flags=re.IGNORECASE)
REQUIRED_GENERAL_SAMPLE_TICKERS = {
    "KXAKSENATE-26NOV03-DSUL",
    "SENATEAK-26-R",
}


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


def _write_contest_payload_json(path: Path, *, contests: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    _write_json(
        path,
        {
            "generatedAt": summary.get("generated_at"),
            "summary": {
                "contest_count": len(contests),
                "included_markets": int(sum(int(row.get("market_count") or 0) for row in contests)),
            },
            "contests": contests,
        },
    )


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
        if ticker.startswith(prefix) or event_ticker.startswith(prefix) or series_ticker.startswith(prefix):
            matches.append((prefix, dict(value)))
    if not matches:
        return None, None
    if len(matches) > 1:
        return {"_ambiguous_override": [prefix for prefix, _value in matches]}, "ambiguous"
    prefix, resolved = matches[0]
    return resolved, f"prefix:{prefix}"


def _extract_state_party_special(*texts: str) -> tuple[str | None, str | None, bool]:
    for text in texts:
        upper = str(text or "").upper()
        match = STATE_PARTY_TICKER_RE.search(upper)
        if not match:
            state_match = STATE_ONLY_TICKER_RE.search(upper) or PREFIX_STATE_TICKER_RE.search(upper)
            if not state_match:
                continue
            party_match = PARTY_SUFFIX_RE.search(upper)
            party = party_match.group("party").upper() if party_match else None
            special = "SPECIAL" in upper or "SENATEOHS" in upper or "SENATEFLS" in upper
            return state_match.group("state").upper(), party, special
        tag = match.group("tag").upper()
        party = tag[-1] if tag[-1] in {"D", "R"} else None
        special = tag.startswith("S")
        return match.group("state").upper(), party, special
    return None, None, False


def _extract_state_from_text(*texts: str) -> str | None:
    for text in texts:
        upper = str(text or "").upper()
        for state_name, state_code in STATE_NAMES.items():
            if state_name.upper() in upper:
                return state_code
    return None


def _extract_cycle_year(*texts: str) -> int | None:
    for text in texts:
        upper = str(text or "").upper()
        match = CYCLE_RE.search(upper)
        if match:
            return 2000 + int(match.group(1))
    return None


def _extract_class_hint(*texts: str) -> int | None:
    roman_map = {"I": 1, "II": 2, "III": 3}
    for text in texts:
        upper = str(text or "").upper()
        digit_match = CLASS_DIGIT_RE.search(upper)
        if digit_match:
            return int(digit_match.group(1))
        roman_match = CLASS_ROMAN_RE.search(upper)
        if roman_match:
            return roman_map.get(roman_match.group(1))
    return None


def _infer_party(text: str, fallback: str | None) -> str | None:
    if fallback in {"D", "R"}:
        return fallback
    upper = text.upper()
    if "DEMOCRAT" in upper or "DEMOCRATIC" in upper:
        return "D"
    if "REPUBLICAN" in upper or "GOP" in upper:
        return "R"
    return None


def _infer_round(text: str) -> str | None:
    if ROUND_RUNOFF_RE.search(text):
        return "runoff"
    if ROUND_PRIMARY_RE.search(text):
        return "primary"
    if ROUND_GENERAL_RE.search(text):
        return "general"
    if "WIN" in text and "SENATE" in text:
        return "general"
    return None


def _is_outcome_market(text: str) -> bool:
    if NON_OUTCOME_RE.search(text):
        return False
    if OUTCOME_HINT_RE.search(text):
        return True
    return bool("WIN" in text and "SENATE" in text)


def _is_senate_market(*texts: str) -> bool:
    for text in texts:
        upper = str(text or "").upper()
        if not upper:
            continue
        party_state = STATE_PARTY_TICKER_RE.search(upper)
        if party_state and party_state.group("state").upper() in STATE_CODES:
            return True
        state_only = STATE_ONLY_TICKER_RE.search(upper) or PREFIX_STATE_TICKER_RE.search(upper)
        if state_only and state_only.group("state").upper() in STATE_CODES:
            return True
        if SENATE_PATTERN.search(upper) and NON_SEAT_MARKET_RE.search(upper):
            return True
        if ("U.S. SENATE" in upper or "US SENATE" in upper) and any(state_name.upper() in upper for state_name in STATE_NAMES):
            return True
    return False


def _is_non_seat_market(*texts: str) -> bool:
    combined = " ".join(str(text or "") for text in texts).upper()
    if not combined:
        return False
    if NON_SEAT_MARKET_RE.search(combined):
        if "SENATE RACE" in combined or "SENATE ELECTION" in combined or "SENATOR OF" in combined:
            return False
        return True
    return False


def _is_party_entity(value: str | None) -> bool:
    upper = str(value or "").strip().upper()
    if not upper:
        return False
    if "PARTY" in upper:
        return True
    return upper in {
        "DEMOCRAT",
        "DEMOCRATS",
        "DEMOCRATIC",
        "DEMOCRATIC PARTY",
        "REPUBLICAN",
        "REPUBLICANS",
        "REPUBLICAN PARTY",
        "GOP",
    }


def _infer_market_type(*, round_name: str, text: str, party_hint: str | None, entity_name: str) -> str:
    upper = text.upper()
    if round_name in {"primary", "runoff"}:
        return "candidate_nominee"
    if _is_party_entity(entity_name):
        return "party_winner"
    if "WHICH PARTY" in upper:
        return "party_winner"
    if not str(entity_name or "").strip() and party_hint in {"D", "R"} and PARTY_TEXT_RE.search(upper):
        return "party_winner"
    return "candidate_winner"


def _entity_name(payload: dict[str, Any]) -> str:
    custom = payload.get("custom_strike")
    if isinstance(custom, dict):
        for key in ("Candidate", "candidate", "Nominee", "Person"):
            value = str(custom.get(key) or "").strip()
            if value:
                return value
    yes_sub_title = str(payload.get("yes_sub_title") or "").strip()
    if yes_sub_title:
        return yes_sub_title
    return str(payload.get("title") or "").strip()


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
            if existing is None or (candidate[1], -candidate[2], candidate[3]) > (existing[1], -existing[2], existing[3]):
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
            if existing is None or (candidate[3], -candidate[2], str(candidate[0])) > (existing[3], -existing[2], str(existing[0])):
                selected[ticker] = candidate
    return [(file_path, payload, source_priority) for file_path, payload, source_priority, _updated in selected.values()]


def build_kalshi_us_senate_contest_rows(
    market_dirs: tuple[Path, ...] = DEFAULT_MARKET_DIRS,
    series_dirs: tuple[Path, ...] = DEFAULT_SERIES_DIRS,
    *,
    override_registry: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    overrides = override_registry or load_override_registry()
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
        rules_secondary = str(payload.get("rules_secondary") or "")
        yes_sub_title = str(payload.get("yes_sub_title") or "")
        outcomes = payload.get("outcomes")
        close_time = payload.get("close_time")
        combined_text_core = f"{ticker} {event_ticker} {series_ticker} {series_title} {title} {subtitle} {yes_sub_title} {rules_primary}".strip()
        combined_text = f"{combined_text_core} {rules_secondary}".strip()
        combined_upper = combined_text.upper()
        combined_upper_core = combined_text_core.upper()

        if not _is_senate_market(ticker, event_ticker, series_ticker, series_title, title, rules_primary, rules_secondary):
            continue
        if _is_non_seat_market(ticker, event_ticker, series_ticker, series_title, title, rules_primary):
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
        if not _is_outcome_market(combined_upper_core):
            continue

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

        state_code, party_hint, special_hint = _extract_state_party_special(ticker, event_ticker, series_ticker, title, rules_primary)
        if not state_code:
            state_code = _extract_state_from_text(title, rules_primary, rules_secondary, series_title, event_ticker, ticker)
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
        cycle_year = _extract_cycle_year(ticker, event_ticker, series_ticker, title, rules_primary)
        if cycle_year != 2026:
            continue
        class_hint = _extract_class_hint(title, rules_primary, rules_secondary, series_title)
        is_special = special_hint or ("SPECIAL ELECTION" in combined_upper)
        round_name = _infer_round(combined_upper_core)
        if not round_name:
            continue
        party = _infer_party(combined_upper_core, party_hint)

        seat_id = infer_senate_seat_id_from_ticker(
            ticker=combined_upper,
            state_code=state_code,
            cycle_year=cycle_year,
        )
        if seat_id is None:
            seat_id = infer_senate_seat_id(
                state_code=state_code,
                cycle_year=cycle_year,
                is_special=is_special,
                class_hint=class_hint,
            )

        if override_data:
            seat_id = str(override_data.get("seat_id") or seat_id or "").strip() or None
            round_name = str(override_data.get("round") or round_name or "").strip() or None
            party = str(override_data.get("party") or party or "").strip().upper() or None
            market_type = str(override_data.get("market_type") or "").strip()
            if market_type:
                inferred_market_type = market_type
            else:
                inferred_market_type = ""
            if override_key:
                overrides_used.append({"market_ticker": ticker, "override": override_key})
        else:
            inferred_market_type = ""

        entity_name = _entity_name(payload)
        market_type = inferred_market_type or _infer_market_type(
            round_name=round_name or "",
            text=f"{title} {subtitle} {yes_sub_title} {rules_primary}",
            party_hint=party,
            entity_name=entity_name,
        )
        if market_type == "party_winner":
            party = _infer_party(f"{entity_name} {combined_upper}", party)

        if seat_id:
            try:
                seat_id = normalize_senate_seat_id(seat_id)
            except ValueError:
                seat_id = None

        if not seat_id or not round_name or cycle_year is None:
            violations.append(
                {
                    "type": "unresolved_mapping",
                    "market_ticker": ticker,
                    "event_ticker": event_ticker,
                    "series_ticker": series_ticker,
                    "state_code": state_code or "",
                    "cycle_year": cycle_year,
                    "seat_id": seat_id or "",
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
                "outcomes": outcomes if isinstance(outcomes, list) else [],
                "raw_source_path": display_path(file_path),
                "seat_id": seat_id,
                "state": seat_id.split("-", 1)[0],
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
                "classification_reason": [
                    f"round:{round_name}",
                    f"market_type:{market_type}",
                ],
                "mapping_confidence": "override" if override_key else "deterministic",
                "exclusion_reason": None,
            }
        )

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
        contest_id = f"US-SEN:{seat_id}:{cycle_year}:{round_name}:{party or 'NA'}:{market_type}"
        contests.append(
            {
                "contest_id": contest_id,
                "seat_id": seat_id,
                "state": seat_id.split("-", 1)[0],
                "cycle_year": cycle_year,
                "round": round_name,
                "party": party or None,
                "market_type": market_type,
                "market_count": len(sorted_markets),
                "has_active_market": any((item.get("status") or "").lower() == "active" for item in sorted_markets),
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
                "source_files": sorted({item.get("source_file") for item in sorted_markets if item.get("source_file")}),
            }
        )

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

    contests.sort(key=lambda row: (row.get("seat_id") or "", row.get("round") or "", row.get("party") or "", row.get("market_type") or ""))
    violations.sort(key=lambda row: (str(row.get("type") or ""), str(row.get("market_ticker") or ""), str(row.get("seat_id") or "")))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_markets": len(selected_markets),
        "included_markets": len(included_markets),
        "excluded_count": len(excluded_markets),
        "contest_count": len(contests),
        "violation_count": len(violations),
        "overrides_used_count": len(overrides_used),
        "by_round": dict(sorted({key: sum(1 for row in included_markets if row.get("round") == key) for key in {"primary", "runoff", "general"}}.items())),
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


def build_kalshi_us_senate_contest_index(
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
    ballotpedia_primary_csv: Path = DEFAULT_BALLOTPEDIA_SENATE_PRIMARY_CSV,
    ballotpedia_runoff_csv: Path = DEFAULT_BALLOTPEDIA_SENATE_RUNOFF_CSV,
    ballotpedia_general_csv: Path = DEFAULT_BALLOTPEDIA_SENATE_GENERAL_CSV,
    market_dirs: tuple[Path, ...] = DEFAULT_MARKET_DIRS,
    series_dirs: tuple[Path, ...] = DEFAULT_SERIES_DIRS,
    *,
    override_registry: dict[str, Any] | None = None,
    strict: bool = True,
    enforce_required_sample_tickers: bool = True,
) -> dict[str, Any]:
    contests, violations, summary = build_kalshi_us_senate_contest_rows(
        market_dirs=market_dirs,
        series_dirs=series_dirs,
        override_registry=override_registry,
    )
    payload = {
        "generatedAt": summary["generated_at"],
        "summary": summary,
        "marketDirs": [display_path(path) for path in market_dirs],
        "seriesDirs": [display_path(path) for path in series_dirs],
        "contests": contests,
    }

    candidate_winner_contests = [row for row in contests if str(row.get("market_type") or "") == "candidate_winner"]
    party_winner_contests = [row for row in contests if str(row.get("market_type") or "") == "party_winner"]
    candidate_nominee_contests = [row for row in contests if str(row.get("market_type") or "") == "candidate_nominee"]
    unmapped_rows = [row for row in violations if str(row.get("type") or "") == "unresolved_mapping"]
    ambiguous_rows = [row for row in violations if "ambiguous" in str(row.get("type") or "")]
    excluded_rows = list(summary.get("excluded_markets") or [])

    coverage_payload = {
        "generatedAt": summary["generated_at"],
        "counts": {
            "candidate_winner_contests": len(candidate_winner_contests),
            "party_winner_contests": len(party_winner_contests),
            "candidate_nominee_contests": len(candidate_nominee_contests),
            "general_contests": sum(1 for row in contests if str(row.get("round") or "") == "general"),
        },
        "byRound": summary.get("by_round") or {},
        "byMarketType": summary.get("by_market_type") or {},
    }
    market_tickers = {
        str(market.get("marketTicker") or "").strip().upper()
        for contest in contests
        for market in (contest.get("markets") or [])
        if str(market.get("marketTicker") or "").strip()
    }
    required_sample_tickers = sorted(REQUIRED_GENERAL_SAMPLE_TICKERS) if enforce_required_sample_tickers else []
    missing_sample_tickers = sorted(ticker for ticker in required_sample_tickers if ticker not in market_tickers)
    coverage_payload["requiredGeneralSampleTickers"] = required_sample_tickers
    coverage_payload["missingRequiredGeneralSampleTickers"] = missing_sample_tickers
    candidate_winner_rows = build_candidate_market_rows(
        contests=contests,
        office="us_senate",
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
        office="us_senate",
        market_type_field="market_type",
        market_type_value="candidate_nominee",
        seat_field="seat_id",
        party_field="party",
        ballotpedia_primary_csv=ballotpedia_primary_csv,
        ballotpedia_runoff_csv=ballotpedia_runoff_csv,
        ballotpedia_general_csv=ballotpedia_general_csv,
    )
    candidate_winner_report = build_candidate_match_report(candidate_winner_rows, office="us_senate", market_type="candidate_winner")
    candidate_nominee_report = build_candidate_match_report(candidate_nominee_rows, office="us_senate", market_type="candidate_nominee")
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
        "office": "us_senate",
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
    _write_row_payload_json(output_candidate_winner_json, rows=candidate_winner_rows, summary=summary, report=candidate_winner_report)
    _write_contest_payload_json(output_party_winner_json, contests=party_winner_contests, summary=summary)
    _write_row_payload_json(output_candidate_nominee_json, rows=candidate_nominee_rows, summary=summary, report=candidate_nominee_report)
    _write_csv(output_candidate_winner_csv, candidate_winner_rows)
    _write_csv(output_party_winner_csv, party_winner_contests)
    _write_csv(output_candidate_nominee_csv, candidate_nominee_rows)
    _write_json(output_candidate_match_report_json, candidate_match_report)
    _write_csv(output_candidate_match_report_csv, [candidate_winner_report, candidate_nominee_report])

    if coverage_payload["counts"]["general_contests"] <= 0:
        violations.append(
            {
                "type": "general_market_coverage_missing",
                "message": "No general Senate contests were produced by Kalshi mapping.",
            }
        )
    if enforce_required_sample_tickers and missing_sample_tickers:
        violations.append(
            {
                "type": "required_general_sample_missing",
                "missing_tickers": missing_sample_tickers,
            }
        )
    if blocking_count > 0:
        violations.append(
            {
                "type": "candidate_match_blocking_unresolved",
                "office": "us_senate",
                "threshold": 2.0,
                "count": blocking_count,
            }
        )
    if ambiguous_auto_match_count > 0:
        violations.append(
            {
                "type": "candidate_match_ambiguous_auto_match",
                "office": "us_senate",
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
        raise RuntimeError(f"Kalshi US-SEN contest integrity validation failed with {len(violations)} violation(s)")
    return payload
