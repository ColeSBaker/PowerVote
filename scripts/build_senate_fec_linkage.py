#!/usr/bin/env python3
"""Build Senate FEC linkage outputs for candidate rollup."""
from __future__ import annotations

import argparse
from pathlib import Path

from senate_fec_linkage import (
    DEFAULT_OUTPUT_AUDIT,
    DEFAULT_OUTPUT_CONFLICTS,
    DEFAULT_OUTPUT_ENRICHED,
    build_senate_fec_linkage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Senate FEC linkage artifacts")
    parser.add_argument("--out-enriched", type=Path, default=DEFAULT_OUTPUT_ENRICHED)
    parser.add_argument("--out-audit", type=Path, default=DEFAULT_OUTPUT_AUDIT)
    parser.add_argument("--out-conflicts", type=Path, default=DEFAULT_OUTPUT_CONFLICTS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_senate_fec_linkage(
        output_enriched=args.out_enriched,
        output_audit=args.out_audit,
        output_conflicts=args.out_conflicts,
    )
    print(
        "Built Senate FEC linkage:"
        f" senate_rows={summary.get('senate_rows', 0)}"
        f" matched_rows={summary.get('matched_rows', 0)}"
        f" conflicts={summary.get('conflicts', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
