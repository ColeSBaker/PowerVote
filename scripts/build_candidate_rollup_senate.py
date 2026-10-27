#!/usr/bin/env python3
"""Build candidate-level 2026 U.S. Senate rollup with House-compatible columns."""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from ballotpedia_rollup.config import display_path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIMARY_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-senate-primary-election-rollup.csv"
DEFAULT_RUNOFF_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-senate-runoff-election-rollup.csv"
DEFAULT_GENERAL_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-senate-general-election-rollup.csv"
DEFAULT_HOUSE_TEMPLATE_FILE = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-2026.csv"
DEFAULT_OUT_CSV = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-senate-2026.csv"
DEFAULT_OUT_JSON = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-senate-2026.json"


def _load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_json_list(raw: str | None) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    return []


def _parse_json_map(raw: str | None) -> dict[str, object]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return {str(key): value for key, value in payload.items()}
    return {}


def _normalize_name(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _odds_map_sum_status(odds_map: dict[str, float]) -> str:
    values = [float(v) for v in odds_map.values() if isinstance(v, (int, float))]
    if len(values) < 2:
        return "insufficient_entries"
    total = round(sum(values), 2)
    return "ok" if 90.0 <= total <= 110.0 else "out_of_band"


def _parse_odds_map(raw: str | None) -> dict[str, float]:
    parsed = _parse_json_map(raw)
    output: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            output[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return output


def _lookup_candidate_odds(name: str, odds_map: dict[str, float]) -> tuple[float | None, str | None]:
    if not odds_map:
        return None, None
    target = _normalize_name(name)
    if not target:
        return None, None
    for odds_name, odds in odds_map.items():
        if _normalize_name(odds_name) == target:
            return odds, odds_name
    return None, None


def _headers_from_template(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"House candidate template missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or [])


def _new_row(headers: list[str]) -> dict[str, object]:
    return {header: "" for header in headers}


def _normalize_party(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"D", "DEM", "DEMOCRATIC"}:
        return "DEM"
    if text in {"R", "REP", "REPUBLICAN"}:
        return "REP"
    if text in {"L", "LIB", "LIBERTARIAN"}:
        return "LIB"
    if text in {"G", "GRE", "GREEN"}:
        return "GRE"
    return text or "OTH"


def _parse_iso_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _primary_concluded(primary_row: dict[str, str], snapshot_date: date) -> bool:
    """Return True if a primary election has concluded (date passed and results or complete status)."""
    primary_date = _parse_iso_date(primary_row.get("primary_date"))
    if not primary_date or primary_date > snapshot_date:
        return False
    primary_status = str(primary_row.get("status") or "").strip().lower()
    if primary_status in {"complete", "runoff"}:
        return True
    vote_count_map = _parse_json_map(primary_row.get("primary_vote_count"))
    for v in vote_count_map.values():
        try:
            if float(str(v)) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _build_candidate_rows(
    *,
    headers: list[str],
    general_rows: list[dict[str, str]],
    primary_rows: list[dict[str, str]],
    runoff_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    general_by_seat = {str(row.get("seat") or ""): row for row in general_rows}
    primary_by_seat_party: dict[tuple[str, str], dict[str, str]] = {
        (str(r.get("seat") or ""), str(r.get("party") or "")): r
        for r in primary_rows
    }

    def upsert(
        *,
        seat: str,
        name: str,
        party: str,
        status: str,
        primary_id: str = "",
        runoff_id: str = "",
        primary_votes: object = "",
        primary_share: object = "",
        kalshi_primary_odds: float | None = None,
        kalshi_primary_odds_map: dict[str, float] | None = None,
        kalshi_name: str | None = None,
    ) -> None:
        key = (seat, party, name)
        row = by_key.get(key)
        if row is None:
            row = _new_row(headers)
            row["BallotpediaName"] = name
            row["2026 Seat"] = seat
            row["Party"] = _normalize_party(party)
            row["aliases"] = json.dumps([name], sort_keys=True)
            row["sourceAliases"] = json.dumps({"ballotpedia": [name]}, sort_keys=True)
            row["candidateIds"] = json.dumps([], sort_keys=True)
            row["sourceFlags"] = json.dumps({"hasPrimaryResults": False, "hasRunoffResults": False, "hasFinance": False}, sort_keys=True)
            row["KalshiSeries"] = json.dumps([], sort_keys=True)
            row["KalshiMarkets"] = json.dumps([], sort_keys=True)
            row["KalshiPrimaryMarkets"] = json.dumps([], sort_keys=True)
            row["KalshiRunoffMarkets"] = json.dumps([], sort_keys=True)
            row["KalshiGeneralMarkets"] = json.dumps([], sort_keys=True)
            row["KalshiPrimaryOddsMap"] = json.dumps({}, sort_keys=True)
            row["KalshiPrimaryOddsMapOutOfBand"] = False
            row["KalshiGeneralOddsMap"] = json.dumps({}, sort_keys=True)
            row["KalshiGeneralOddsMapOutOfBand"] = False
            row["FilingName"] = json.dumps([name], sort_keys=True)
            row["KalshiName"] = json.dumps([], sort_keys=True)
            row["CanonicalIsIncumbent"] = False
            row["BallotpediaIsIncumbent"] = False
            row["IsIncumbent"] = False
            by_key[key] = row

        row["Status"] = status
        if primary_id:
            row["Primary ID"] = primary_id
        if runoff_id:
            row["RunoffID"] = runoff_id
        if primary_votes != "":
            row["Votes in Primary"] = primary_votes
        if primary_share != "":
            row["Share of Primary"] = primary_share
        if kalshi_primary_odds is not None:
            current = row.get("KalshiBestPrimaryOdds")
            try:
                current_value = float(str(current or ""))
            except ValueError:
                current_value = None
            if current_value is None or kalshi_primary_odds > current_value:
                row["KalshiBestPrimaryOdds"] = round(kalshi_primary_odds, 2)
        if kalshi_primary_odds_map:
            row["KalshiPrimaryOddsMap"] = json.dumps(kalshi_primary_odds_map, sort_keys=True)
            row["KalshiPrimaryOddsMapOutOfBand"] = _odds_map_sum_status(kalshi_primary_odds_map) == "out_of_band"
        if kalshi_name:
            existing_names = _parse_json_list(str(row.get("KalshiName") or "[]"))
            if kalshi_name not in existing_names:
                existing_names.append(kalshi_name)
            row["KalshiName"] = json.dumps(existing_names, sort_keys=True)

        seat_general = general_by_seat.get(seat) or {}
        row["primaryDate"] = seat_general.get("primary_date") or row.get("primaryDate") or ""
        row["runoffDate"] = seat_general.get("runoff_date") or row.get("runoffDate") or ""
        row["generalDate"] = seat_general.get("general_date") or row.get("generalDate") or ""
        row["statusReason"] = "appears_in_primary_results" if status in {"primary", "runoff"} else "appears_in_general_candidates"
        incumbent_name = str(seat_general.get("incumbent_name") or "").strip().lower()
        incumbent_party = str(seat_general.get("incumbent_party") or "").strip().upper()
        is_incumbent = bool(incumbent_name and incumbent_name == name.strip().lower() and (not incumbent_party or incumbent_party == party.strip().upper()))
        row["CanonicalIsIncumbent"] = bool(is_incumbent)
        row["BallotpediaIsIncumbent"] = bool(is_incumbent)
        row["IsIncumbent"] = bool(is_incumbent)

    for primary in primary_rows:
        seat = str(primary.get("seat") or "")
        party = str(primary.get("party") or "")
        primary_id = str(primary.get("primary_id") or "")
        runoff_id = str(primary.get("runoff_id") or "")
        candidate_names = _parse_json_list(primary.get("candidates"))
        vote_counts = _parse_json_map(primary.get("primary_vote_count"))
        vote_shares = _parse_json_map(primary.get("primary_vote_share"))
        primary_odds_map = _parse_odds_map(primary.get("kalshi_primary_odds_map"))
        runoff_odds_map = _parse_odds_map(primary.get("kalshi_runoff_odds_map"))
        merged_odds_map = dict(primary_odds_map)
        for odds_name, odds_value in runoff_odds_map.items():
            existing = merged_odds_map.get(odds_name)
            if existing is None or odds_value > existing:
                merged_odds_map[odds_name] = odds_value
        for name in candidate_names:
            odds_value, kalshi_name = _lookup_candidate_odds(name, merged_odds_map)
            upsert(
                seat=seat,
                name=name,
                party=party,
                status="primary",
                primary_id=primary_id,
                runoff_id=runoff_id,
                primary_votes=vote_counts.get(name, ""),
                primary_share=vote_shares.get(name, ""),
                kalshi_primary_odds=odds_value,
                kalshi_primary_odds_map=merged_odds_map,
                kalshi_name=kalshi_name,
            )

    for runoff in runoff_rows:
        seat = str(runoff.get("seat") or "")
        party = str(runoff.get("party") or "")
        runoff_id = str(runoff.get("primary_id") or "")
        runoff_odds_map = _parse_odds_map(runoff.get("kalshi_runoff_odds_map"))
        for name in _parse_json_list(runoff.get("candidates")):
            odds_value, kalshi_name = _lookup_candidate_odds(name, runoff_odds_map)
            upsert(
                seat=seat,
                name=name,
                party=party,
                status="runoff",
                primary_id=str(runoff.get("parent_primary_id") or ""),
                runoff_id=runoff_id,
                kalshi_primary_odds=odds_value,
                kalshi_primary_odds_map=runoff_odds_map,
                kalshi_name=kalshi_name,
            )

    for general in general_rows:
        seat = str(general.get("seat") or "")
        for party, field, primary_field in (
            ("D", "nominee_d", "primary_id_d"),
            ("R", "nominee_r", "primary_id_r"),
            ("G", "nominee_green", ""),
            ("L", "nominee_libertarian", ""),
        ):
            name = str(general.get(field) or "").strip()
            if not name:
                continue
            upsert(
                seat=seat,
                name=name,
                party=party,
                status="general (nominated)",
                primary_id=str(general.get(primary_field) or ""),
            )

        for name in _parse_json_list(general.get("other_general_candidates")):
            upsert(
                seat=seat,
                name=name,
                party="OTH",
                status="general (other)",
            )

    # Mark candidates eliminated if they appeared in a concluded primary but did not advance.
    snapshot_date = date.today()
    for key, row in by_key.items():
        if row.get("Status") != "primary":
            continue
        seat, party, _ = key
        primary_row = primary_by_seat_party.get((seat, party))
        if primary_row and _primary_concluded(primary_row, snapshot_date):
            row["Status"] = "eliminated"
            row["statusReason"] = "in_completed_primary_not_in_runoff_or_general"

    rows = list(by_key.values())
    rows.sort(key=lambda row: (str(row.get("2026 Seat") or ""), str(row.get("Party") or ""), str(row.get("BallotpediaName") or "")))
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, rows: list[dict[str, object]], sources: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "electionCycle": 2026,
        "rowCount": len(rows),
        "sources": sources,
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Senate candidate rollup")
    parser.add_argument("--primary-file", type=Path, default=DEFAULT_PRIMARY_FILE)
    parser.add_argument("--runoff-file", type=Path, default=DEFAULT_RUNOFF_FILE)
    parser.add_argument("--general-file", type=Path, default=DEFAULT_GENERAL_FILE)
    parser.add_argument("--template-file", type=Path, default=DEFAULT_HOUSE_TEMPLATE_FILE)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    args = parser.parse_args(argv)

    headers = _headers_from_template(args.template_file)
    # Ensure OutOfBand flag columns are present (they may be absent in older templates).
    for map_col, flag_col in (
        ("KalshiPrimaryOddsMap", "KalshiPrimaryOddsMapOutOfBand"),
        ("KalshiGeneralOddsMap", "KalshiGeneralOddsMapOutOfBand"),
    ):
        if flag_col not in headers and map_col in headers:
            headers.insert(headers.index(map_col) + 1, flag_col)
    general_rows = _load_rows(args.general_file)
    primary_rows = _load_rows(args.primary_file)
    runoff_rows = _load_rows(args.runoff_file)
    rows = _build_candidate_rows(
        headers=headers,
        general_rows=general_rows,
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
    )

    _write_csv(args.out_csv, rows, headers)
    _write_json(
        args.out_json,
        rows,
        [
            display_path(args.primary_file),
            display_path(args.runoff_file),
            display_path(args.general_file),
        ],
    )
    print(f"Rows emitted: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
