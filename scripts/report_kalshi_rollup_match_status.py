#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "apps" / "web" / "data"

HOUSE_GENERAL = DATA_DIR / "ballotpedia-general-election-rollup.csv"
HOUSE_PRIMARY = DATA_DIR / "ballotpedia-primary-election-rollup.csv"
SENATE_GENERAL = DATA_DIR / "ballotpedia-senate-general-election-rollup.csv"
SENATE_PRIMARY = DATA_DIR / "ballotpedia-senate-primary-election-rollup.csv"

DEFAULT_OUT_JSON = DATA_DIR / "kalshi-rollup-match-report.json"
DEFAULT_OUT_CSV = DATA_DIR / "kalshi-rollup-match-report.csv"


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_json_value(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return default
    return parsed


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _classify_general(row: dict[str, str]) -> tuple[str, str]:
    audit = _parse_json_value(row.get("kalshi_join_audit"), {})
    market_count = _to_int(row.get("kalshi_market_count") or audit.get("market_count"))
    sum_status = str(audit.get("sum_status") or "").strip().lower()
    if market_count <= 0:
        return "unmatched", "no_market"
    if sum_status == "out_of_band":
        return "unmatched", "sum_issue"
    return "matched", "matched"


def _classify_primary(row: dict[str, str]) -> tuple[str, str]:
    audit = _parse_json_value(row.get("kalshi_join_audit"), {})
    market_count = _to_int(row.get("kalshi_market_count") or audit.get("market_count"))
    matched_candidate_count = _to_int(audit.get("matched_candidate_count"))
    sum_status = str(audit.get("sum_status") or "").strip().lower()
    if market_count <= 0:
        return "unmatched", "no_market"
    if matched_candidate_count <= 0:
        return "unmatched", "no_candidate_in_market"
    if sum_status == "out_of_band":
        return "unmatched", "sum_issue"
    return "matched", "matched"


def _summarize_bucket(rows: list[dict[str, str]], *, row_type: str) -> dict[str, Any]:
    totals = {
        "total_rows": len(rows),
        "matched_rows": 0,
        "unmatched_rows": 0,
        "cause_no_market": 0,
        "cause_no_candidate_in_market": 0,
        "cause_sum_issue": 0,
    }
    unmatched_examples: dict[str, list[dict[str, str]]] = {
        "no_market": [],
        "no_candidate_in_market": [],
        "sum_issue": [],
    }
    for row in rows:
        seat = str(row.get("seat") or "")
        primary_id = str(row.get("primary_id") or "")
        if row_type == "general":
            status, cause = _classify_general(row)
            row_id = seat
        else:
            status, cause = _classify_primary(row)
            row_id = primary_id or seat
        if status == "matched":
            totals["matched_rows"] += 1
            continue
        totals["unmatched_rows"] += 1
        if cause == "no_market":
            totals["cause_no_market"] += 1
        elif cause == "no_candidate_in_market":
            totals["cause_no_candidate_in_market"] += 1
        elif cause == "sum_issue":
            totals["cause_sum_issue"] += 1
        if cause in unmatched_examples and len(unmatched_examples[cause]) < 25:
            unmatched_examples[cause].append({
                "id": row_id,
                "seat": seat,
                "state": str(row.get("state") or ""),
                "party": str(row.get("party") or ""),
                "primary_id": primary_id,
                "kalshi_market_count": str(row.get("kalshi_market_count") or ""),
                "kalshi_join_strategy": str(row.get("kalshi_join_strategy") or ""),
            })
    totals["match_rate"] = round((totals["matched_rows"] / totals["total_rows"]), 4) if totals["total_rows"] else 0.0
    return {
        "counts": totals,
        "unmatched_examples": unmatched_examples,
    }


def build_report() -> dict[str, Any]:
    house_general_rows = _load_csv(HOUSE_GENERAL)
    house_primary_rows = _load_csv(HOUSE_PRIMARY)
    senate_general_rows = _load_csv(SENATE_GENERAL)
    senate_primary_rows = _load_csv(SENATE_PRIMARY)

    report = {
        "generatedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "house": {
            "general": _summarize_bucket(house_general_rows, row_type="general"),
            "primary": _summarize_bucket(house_primary_rows, row_type="primary"),
        },
        "senate": {
            "general": _summarize_bucket(senate_general_rows, row_type="general"),
            "primary": _summarize_bucket(senate_primary_rows, row_type="primary"),
        },
    }
    return report


def _write_csv_summary(path: Path, report: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    for office in ("house", "senate"):
        for row_type in ("general", "primary"):
            counts = ((report.get(office) or {}).get(row_type) or {}).get("counts") or {}
            rows.append(
                {
                    "office": office,
                    "row_type": row_type,
                    "total_rows": counts.get("total_rows", 0),
                    "matched_rows": counts.get("matched_rows", 0),
                    "unmatched_rows": counts.get("unmatched_rows", 0),
                    "match_rate": counts.get("match_rate", 0),
                    "cause_no_market": counts.get("cause_no_market", 0),
                    "cause_no_candidate_in_market": counts.get("cause_no_candidate_in_market", 0),
                    "cause_sum_issue": counts.get("cause_sum_issue", 0),
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Kalshi match coverage in Ballotpedia election rollups")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    args = parser.parse_args()

    report = build_report()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_csv_summary(args.out_csv, report)

    for office in ("house", "senate"):
        for row_type in ("general", "primary"):
            counts = report[office][row_type]["counts"]
            print(
                f"{office}.{row_type}: total={counts['total_rows']} matched={counts['matched_rows']} "
                f"unmatched={counts['unmatched_rows']} no_market={counts['cause_no_market']} "
                f"no_candidate_in_market={counts['cause_no_candidate_in_market']} sum_issue={counts['cause_sum_issue']}"
            )
    print(f"JSON: {args.out_json}")
    print(f"CSV: {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
