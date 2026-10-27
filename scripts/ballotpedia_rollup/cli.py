"""CLI entrypoint for Ballotpedia rollup extraction."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .config import (
    DEFAULT_OUTPUT_BALLOTPEDIA_KALSHI_UNMATCHED_CSV,
    DEFAULT_OUTPUT_HISTORICAL_VOTE_TOTAL_VIOLATIONS_CSV,
    DEFAULT_OUTPUT_PRIMARY_KALSHI_JOIN_ANOMALIES_CSV,
    DEFAULT_PARSE_CACHE_FILE,
    DEFAULT_OUTPUT_INCUMBENT_DEPARTURES_CSV,
    DEFAULT_OUTPUT_FEC_UNMATCHED_CSV,
    DEFAULT_OUTPUT_FEC_MATCH_AUDIT_CSV,
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_GENERAL_CSV,
    DEFAULT_OUTPUT_GENERAL_FILE,
    DEFAULT_OUTPUT_GENERAL_JSON,
    DEFAULT_OUTPUT_PRIMARY_CSV,
    DEFAULT_OUTPUT_PRIMARY_FILE,
    DEFAULT_OUTPUT_PRIMARY_JSON,
    DEFAULT_OUTPUT_RUNOFF_CSV,
    DEFAULT_OUTPUT_RUNOFF_FILE,
    DEFAULT_OUTPUT_RUNOFF_JSON,
    DEFAULT_OUTPUT_KALSHI_ROLLUP_JOIN_AUDIT_CSV,
)
from .io import write_csv, write_json, write_rows
from .fec_matching import load_fec_candidates, load_fec_rows
from .kalshi import build_kalshi_contest_indexes, load_kalshi_us_rep_contests
from .parser import build_rollup_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Ballotpedia 2026 House rollups from raw HTML snapshots")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--out-general-json", type=Path, default=DEFAULT_OUTPUT_GENERAL_JSON)
    parser.add_argument("--out-primary-json", type=Path, default=DEFAULT_OUTPUT_PRIMARY_JSON)
    parser.add_argument("--out-runoff-json", type=Path, default=DEFAULT_OUTPUT_RUNOFF_JSON)
    parser.add_argument("--out-general-csv", type=Path, default=DEFAULT_OUTPUT_GENERAL_CSV)
    parser.add_argument("--out-primary-csv", type=Path, default=DEFAULT_OUTPUT_PRIMARY_CSV)
    parser.add_argument("--out-runoff-csv", type=Path, default=DEFAULT_OUTPUT_RUNOFF_CSV)
    parser.add_argument("--out-general", type=Path, default=DEFAULT_OUTPUT_GENERAL_FILE)
    parser.add_argument("--out-primary", type=Path, default=DEFAULT_OUTPUT_PRIMARY_FILE)
    parser.add_argument("--out-runoff", type=Path, default=DEFAULT_OUTPUT_RUNOFF_FILE)
    parser.add_argument("--out-incumbent-departures-csv", type=Path, default=DEFAULT_OUTPUT_INCUMBENT_DEPARTURES_CSV)
    parser.add_argument("--out-fec-unmatched-csv", type=Path, default=DEFAULT_OUTPUT_FEC_UNMATCHED_CSV)
    parser.add_argument("--out-fec-match-audit-csv", type=Path, default=DEFAULT_OUTPUT_FEC_MATCH_AUDIT_CSV)
    parser.add_argument("--out-kalshi-rollup-join-audit-csv", type=Path, default=DEFAULT_OUTPUT_KALSHI_ROLLUP_JOIN_AUDIT_CSV)
    parser.add_argument("--out-ballotpedia-kalshi-unmatched-csv", type=Path, default=DEFAULT_OUTPUT_BALLOTPEDIA_KALSHI_UNMATCHED_CSV)
    parser.add_argument("--out-historical-vote-total-violations-csv", type=Path, default=DEFAULT_OUTPUT_HISTORICAL_VOTE_TOTAL_VIOLATIONS_CSV)
    parser.add_argument("--out-primary-kalshi-join-anomalies-csv", type=Path, default=DEFAULT_OUTPUT_PRIMARY_KALSHI_JOIN_ANOMALIES_CSV)
    parser.add_argument("--cache-file", type=Path, default=DEFAULT_PARSE_CACHE_FILE)
    parser.add_argument("--incremental", action="store_true", help="Reuse parse cache for unchanged source pages")
    parser.add_argument("--profile", action="store_true", help="Print per-stage timing diagnostics")
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    return parser


def _output_paths_from_args(args: argparse.Namespace) -> list[Path]:
    return [
        args.out_general_json,
        args.out_primary_json,
        args.out_runoff_json,
        args.out_general_csv,
        args.out_primary_csv,
        args.out_runoff_csv,
        args.out_general,
        args.out_primary,
        args.out_runoff,
        args.out_incumbent_departures_csv,
        args.out_fec_unmatched_csv,
        args.out_fec_match_audit_csv,
        args.out_kalshi_rollup_join_audit_csv,
        args.out_ballotpedia_kalshi_unmatched_csv,
        args.out_historical_vote_total_violations_csv,
        args.out_primary_kalshi_join_anomalies_csv,
    ]


def _preflight_output_paths_writable(paths: list[Path]) -> None:
    errors: list[str] = []
    for path in paths:
        parent = path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(f"{path}: cannot create parent directory ({exc})")
            continue
        if path.exists():
            try:
                with path.open("r+b"):
                    pass
            except OSError as exc:
                errors.append(f"{path}: not writable or locked ({exc})")
        else:
            if not os.access(parent, os.W_OK):
                errors.append(f"{path}: parent directory is not writable")
    if errors:
        details = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(f"Output preflight failed. Resolve file locks/permissions first:\n{details}")


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _preflight_output_paths_writable(_output_paths_from_args(args))

    stage_timings: dict[str, float] = {}
    t_total_start = time.perf_counter()

    t = time.perf_counter()
    fec_rows = load_fec_rows()
    fec_candidates = load_fec_candidates(rows=fec_rows)
    stage_timings["load_fec_resources_seconds"] = round(time.perf_counter() - t, 4)

    t = time.perf_counter()
    kalshi_contests = load_kalshi_us_rep_contests()
    kalshi_indexes = build_kalshi_contest_indexes(kalshi_contests)
    stage_timings["load_kalshi_resources_seconds"] = round(time.perf_counter() - t, 4)

    context = build_rollup_context(
        args.input_dir,
        fec_rows=fec_rows,
        fec_candidates=fec_candidates,
        kalshi_indexes=kalshi_indexes,
        incremental=bool(args.incremental),
        cache_path=args.cache_file,
        profile=bool(args.profile),
    )

    t = time.perf_counter()
    write_json(args.out_general_json, context.general_rows)
    write_json(args.out_primary_json, context.primary_rows)
    write_json(args.out_runoff_json, context.runoff_rows)
    write_csv(args.out_general_csv, context.general_rows)
    write_csv(args.out_primary_csv, context.primary_rows)
    write_csv(args.out_runoff_csv, context.runoff_rows)

    write_rows(args.out_general, context.general_rows, args.format)
    write_rows(args.out_primary, context.primary_rows, args.format)
    write_rows(args.out_runoff, context.runoff_rows, args.format)
    write_csv(args.out_incumbent_departures_csv, context.incumbent_departures)
    write_csv(args.out_fec_unmatched_csv, context.fec_unmatched)
    write_csv(args.out_fec_match_audit_csv, context.fec_match_audit)
    write_csv(args.out_kalshi_rollup_join_audit_csv, context.kalshi_join_audit)
    write_csv(args.out_ballotpedia_kalshi_unmatched_csv, context.ballotpedia_kalshi_unmatched)
    write_csv(args.out_historical_vote_total_violations_csv, context.historical_vote_total_violations)
    write_csv(args.out_primary_kalshi_join_anomalies_csv, context.primary_kalshi_join_anomalies)
    stage_timings["write_outputs_seconds"] = round(time.perf_counter() - t, 4)
    stage_timings["total_seconds"] = round(time.perf_counter() - t_total_start, 4)

    print(f"Input files discovered: {sum(context.archetype_counts.values())}")
    print(f"Archetype counts: {context.archetype_counts}")
    print(f"General rows emitted: {len(context.general_rows)}")
    print(f"Primary rows emitted: {len(context.primary_rows)}")
    print(f"Runoff rows emitted: {len(context.runoff_rows)}")
    print(f"Incumbent departures emitted: {len(context.incumbent_departures)}")
    print(f"Ballotpedia/FEC unmatched emitted: {len(context.fec_unmatched)}")
    print(f"Ballotpedia/FEC match audit rows emitted: {len(context.fec_match_audit)}")
    print(f"Kalshi join audit rows emitted: {len(context.kalshi_join_audit)}")
    print(f"Ballotpedia/Kalshi unmatched emitted: {len(context.ballotpedia_kalshi_unmatched)}")
    print(f"Historical vote-total violations emitted: {len(context.historical_vote_total_violations)}")
    print(f"Primary Kalshi join anomalies emitted: {len(context.primary_kalshi_join_anomalies)}")
    if args.profile:
        print("Timing profile (seconds):")
        merged = dict(stage_timings)
        merged.update(context.parse_profile or {})
        for key in sorted(merged.keys()):
            print(f"- {key}: {merged[key]:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
