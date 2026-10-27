#!/usr/bin/env python3
"""Build Ballotpedia 2026 Senate rollups from raw HTML snapshots."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ballotpedia_rollup.kalshi import build_kalshi_contest_indexes
from ballotpedia_rollup.io import write_csv, write_json, write_rows
from ballotpedia_rollup.parser import build_rollup_context
from kalshi.kalshi_senate_mapping import DEFAULT_OUTPUT_INDEX_JSON as DEFAULT_SENATE_KALSHI_INDEX_JSON

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "raw" / "ballotpedia_senate_raw"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "apps" / "web" / "data"
DEFAULT_OUTPUT_GENERAL_CSV = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-general-election-rollup.csv"
DEFAULT_OUTPUT_PRIMARY_CSV = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-primary-election-rollup.csv"
DEFAULT_OUTPUT_RUNOFF_CSV = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-runoff-election-rollup.csv"
DEFAULT_OUTPUT_GENERAL_JSON = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-general-election-rollup.json"
DEFAULT_OUTPUT_PRIMARY_JSON = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-primary-election-rollup.json"
DEFAULT_OUTPUT_RUNOFF_JSON = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-runoff-election-rollup.json"
DEFAULT_OUTPUT_GENERAL_JSONL = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-general-election-rollup.jsonl"
DEFAULT_OUTPUT_PRIMARY_JSONL = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-primary-election-rollup.jsonl"
DEFAULT_OUTPUT_RUNOFF_JSONL = DEFAULT_OUTPUT_DIR / "ballotpedia-senate-runoff-election-rollup.jsonl"


def _build_senate_kalshi_indexes(index_json: Path) -> dict[str, object]:
    if not index_json.exists():
        return {}
    payload = json.loads(index_json.read_text(encoding="utf-8"))
    raw_contests = payload.get("contests")
    if not isinstance(raw_contests, list):
        return {}
    transformed: list[dict[str, object]] = []
    for contest in raw_contests:
        if not isinstance(contest, dict):
            continue
        seat = str(contest.get("seat_id") or "").strip()
        round_name = str(contest.get("round") or "").strip().lower()
        if not seat or not round_name:
            continue
        markets = []
        market_tickers = []
        for market in contest.get("markets") or []:
            if not isinstance(market, dict):
                continue
            ticker = str(market.get("marketTicker") or "").strip()
            if not ticker:
                continue
            market_tickers.append(ticker)
            markets.append(
                {
                    "marketTicker": ticker,
                    "eventTicker": market.get("eventTicker"),
                    "seriesTicker": market.get("seriesTicker"),
                    "entityName": market.get("entityName"),
                    "status": market.get("status"),
                    "oddsPercent": market.get("oddsPercent"),
                    "sourceFile": market.get("sourceFile"),
                }
            )
        transformed.append(
            {
                "contest_id": contest.get("contest_id"),
                "seat": seat,
                "cycle_year": contest.get("cycle_year"),
                "round": round_name,
                "party_lane": contest.get("party"),
                "market_role": contest.get("market_type"),
                "normalized_contest_key": contest.get("contest_id"),
                "market_count": contest.get("market_count"),
                "market_tickers": market_tickers,
                "has_active_market": contest.get("has_active_market"),
                "markets": markets,
            }
        )
    return build_kalshi_contest_indexes(transformed)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Ballotpedia 2026 Senate rollups from raw HTML snapshots")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--out-general-csv", type=Path, default=DEFAULT_OUTPUT_GENERAL_CSV)
    parser.add_argument("--out-primary-csv", type=Path, default=DEFAULT_OUTPUT_PRIMARY_CSV)
    parser.add_argument("--out-runoff-csv", type=Path, default=DEFAULT_OUTPUT_RUNOFF_CSV)
    parser.add_argument("--out-general-json", type=Path, default=DEFAULT_OUTPUT_GENERAL_JSON)
    parser.add_argument("--out-primary-json", type=Path, default=DEFAULT_OUTPUT_PRIMARY_JSON)
    parser.add_argument("--out-runoff-json", type=Path, default=DEFAULT_OUTPUT_RUNOFF_JSON)
    parser.add_argument("--out-general-jsonl", type=Path, default=DEFAULT_OUTPUT_GENERAL_JSONL)
    parser.add_argument("--out-primary-jsonl", type=Path, default=DEFAULT_OUTPUT_PRIMARY_JSONL)
    parser.add_argument("--out-runoff-jsonl", type=Path, default=DEFAULT_OUTPUT_RUNOFF_JSONL)
    parser.add_argument("--kalshi-index-json", type=Path, default=DEFAULT_SENATE_KALSHI_INDEX_JSON)
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kalshi_indexes = _build_senate_kalshi_indexes(args.kalshi_index_json)
    context = build_rollup_context(
        args.input_dir,
        office="us_senate",
        kalshi_indexes=kalshi_indexes,
    )

    write_json(args.out_general_json, context.general_rows)
    write_json(args.out_primary_json, context.primary_rows)
    write_json(args.out_runoff_json, context.runoff_rows)
    write_csv(args.out_general_csv, context.general_rows)
    write_csv(args.out_primary_csv, context.primary_rows)
    write_csv(args.out_runoff_csv, context.runoff_rows)

    write_rows(args.out_general_jsonl, context.general_rows, args.format)
    write_rows(args.out_primary_jsonl, context.primary_rows, args.format)
    write_rows(args.out_runoff_jsonl, context.runoff_rows, args.format)

    print(f"Input files discovered: {sum(context.archetype_counts.values())}")
    print(f"Archetype counts: {context.archetype_counts}")
    print(f"General rows emitted: {len(context.general_rows)}")
    print(f"Primary rows emitted: {len(context.primary_rows)}")
    print(f"Runoff rows emitted: {len(context.runoff_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
