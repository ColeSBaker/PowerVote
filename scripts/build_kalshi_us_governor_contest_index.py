#!/usr/bin/env python3
"""Build canonical Kalshi US-GOV contest index artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path

from kalshi.kalshi_governor_mapping import (
    DEFAULT_OUTPUT_INDEX_CSV,
    DEFAULT_OUTPUT_INDEX_JSON,
    DEFAULT_OUTPUT_VIOLATIONS_CSV,
    DEFAULT_OUTPUT_VIOLATIONS_JSON,
    build_kalshi_us_governor_contest_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build canonical Kalshi US-GOV contest index")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUTPUT_INDEX_JSON)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUTPUT_INDEX_CSV)
    parser.add_argument("--out-violations-csv", type=Path, default=DEFAULT_OUTPUT_VIOLATIONS_CSV)
    parser.add_argument("--out-violations-json", type=Path, default=DEFAULT_OUTPUT_VIOLATIONS_JSON)
    parser.add_argument("--no-strict", action="store_true", help="Allow integrity violations without failing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_kalshi_us_governor_contest_index(
        output_json=args.out_json,
        output_csv=args.out_csv,
        output_violations_csv=args.out_violations_csv,
        output_violations_json=args.out_violations_json,
        strict=not args.no_strict,
    )
    summary = payload.get("summary") or {}
    by_type = summary.get("by_market_type") or {}
    print(
        "Built Kalshi US-GOV contest index:"
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
