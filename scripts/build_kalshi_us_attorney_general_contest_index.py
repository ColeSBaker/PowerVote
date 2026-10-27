#!/usr/bin/env python3
"""Build canonical Kalshi US-AG contest index artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path

from kalshi.kalshi_attorney_general_mapping import (
    DEFAULT_OUTPUT_INDEX_CSV,
    DEFAULT_OUTPUT_INDEX_JSON,
    DEFAULT_OUTPUT_VIOLATIONS_CSV,
    DEFAULT_OUTPUT_VIOLATIONS_JSON,
    DEFAULT_OUTPUT_CANDIDATE_WINNER_JSON,
    DEFAULT_OUTPUT_CANDIDATE_WINNER_CSV,
    DEFAULT_OUTPUT_PARTY_WINNER_JSON,
    DEFAULT_OUTPUT_PARTY_WINNER_CSV,
    DEFAULT_OUTPUT_CANDIDATE_NOMINEE_JSON,
    DEFAULT_OUTPUT_CANDIDATE_NOMINEE_CSV,
    DEFAULT_OUTPUT_EXCLUDED_CSV,
    DEFAULT_OUTPUT_UNMAPPED_CSV,
    DEFAULT_OUTPUT_AMBIGUOUS_CSV,
    DEFAULT_OUTPUT_COVERAGE_JSON,
    DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_JSON,
    DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_CSV,
    build_kalshi_us_ag_contest_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build canonical Kalshi US-AG contest index")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUTPUT_INDEX_JSON)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUTPUT_INDEX_CSV)
    parser.add_argument("--out-violations-csv", type=Path, default=DEFAULT_OUTPUT_VIOLATIONS_CSV)
    parser.add_argument("--out-violations-json", type=Path, default=DEFAULT_OUTPUT_VIOLATIONS_JSON)
    parser.add_argument("--out-candidate-winner-json", type=Path, default=DEFAULT_OUTPUT_CANDIDATE_WINNER_JSON)
    parser.add_argument("--out-candidate-winner-csv", type=Path, default=DEFAULT_OUTPUT_CANDIDATE_WINNER_CSV)
    parser.add_argument("--out-party-winner-json", type=Path, default=DEFAULT_OUTPUT_PARTY_WINNER_JSON)
    parser.add_argument("--out-party-winner-csv", type=Path, default=DEFAULT_OUTPUT_PARTY_WINNER_CSV)
    parser.add_argument("--out-candidate-nominee-json", type=Path, default=DEFAULT_OUTPUT_CANDIDATE_NOMINEE_JSON)
    parser.add_argument("--out-candidate-nominee-csv", type=Path, default=DEFAULT_OUTPUT_CANDIDATE_NOMINEE_CSV)
    parser.add_argument("--out-excluded-csv", type=Path, default=DEFAULT_OUTPUT_EXCLUDED_CSV)
    parser.add_argument("--out-unmapped-csv", type=Path, default=DEFAULT_OUTPUT_UNMAPPED_CSV)
    parser.add_argument("--out-ambiguous-csv", type=Path, default=DEFAULT_OUTPUT_AMBIGUOUS_CSV)
    parser.add_argument("--out-coverage-json", type=Path, default=DEFAULT_OUTPUT_COVERAGE_JSON)
    parser.add_argument("--out-candidate-match-report-json", type=Path, default=DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_JSON)
    parser.add_argument("--out-candidate-match-report-csv", type=Path, default=DEFAULT_OUTPUT_CANDIDATE_MATCH_REPORT_CSV)
    parser.add_argument("--no-strict", action="store_true", help="Allow integrity violations without failing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_kalshi_us_ag_contest_index(
        output_json=args.out_json,
        output_csv=args.out_csv,
        output_violations_csv=args.out_violations_csv,
        output_violations_json=args.out_violations_json,
        output_candidate_winner_json=args.out_candidate_winner_json,
        output_candidate_winner_csv=args.out_candidate_winner_csv,
        output_party_winner_json=args.out_party_winner_json,
        output_party_winner_csv=args.out_party_winner_csv,
        output_candidate_nominee_json=args.out_candidate_nominee_json,
        output_candidate_nominee_csv=args.out_candidate_nominee_csv,
        output_excluded_csv=args.out_excluded_csv,
        output_unmapped_csv=args.out_unmapped_csv,
        output_ambiguous_csv=args.out_ambiguous_csv,
        output_coverage_json=args.out_coverage_json,
        output_candidate_match_report_json=args.out_candidate_match_report_json,
        output_candidate_match_report_csv=args.out_candidate_match_report_csv,
        strict=not args.no_strict,
    )
    summary = payload.get("summary") or {}
    by_type = summary.get("by_market_type") or {}
    print(
        "Built Kalshi US-AG contest index:"
        f" contests={summary.get('contest_count', 0)}"
        f" included_markets={summary.get('included_markets', 0)}"
        f" party_winner={by_type.get('party_winner', 0)}"
        f" candidate_nominee={by_type.get('candidate_nominee', 0)}"
        f" candidate_winner={by_type.get('candidate_winner', 0)}"
        f" violations={summary.get('violation_count', 0)}"
    )
    print(f"JSON:       {args.out_json}")
    print(f"CSV:        {args.out_csv}")
    print(f"Violations: {args.out_violations_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
