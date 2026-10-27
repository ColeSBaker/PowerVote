#!/usr/bin/env python3
"""Build candidate-level 2026 attorney general rollups.

Inputs:
- apps/web/data/ballotpedia-attorney-general-{primary,runoff,general}-election-rollup.csv
- apps/web/data/kalshi-us-attorney-general-contest-index.json

Outputs:
- apps/web/data/attorney-general-candidate-rollup-2026.csv
- apps/web/data/attorney-general-candidate-rollup-2026.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_candidate_rollup as bcr  # noqa: E402

DATA_DIR = REPO_ROOT / "apps" / "web" / "data"

# Kalshi contest index file
_AG_CONTEST_INDEX = DATA_DIR / "kalshi-us-attorney-general-contest-index.json"


def _load_kalshi_contests(index_path: Path) -> list[dict[str, Any]]:
    """Load and normalize AG contest rows for the shared enrichment pipeline.

    The AG indexes use slightly different field names than the
    House/Senate indexes that ``build_kalshi_contest_indexes`` was written for.
    This function maps them so the existing enrichment code works unchanged.
    """
    if not index_path.exists():
        return []
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    raw_contests: list[dict[str, Any]] = payload.get("contests") or []
    normalized: list[dict[str, Any]] = []
    for c in raw_contests:
        nc = dict(c)
        nc.setdefault("seat", nc.get("seat_id"))
        nc.setdefault("party_lane", nc.get("party"))
        nc.setdefault("market_role", nc.get("market_type"))
        if "market_tickers" not in nc:
            nc["market_tickers"] = [
                str(m.get("marketTicker") or "")
                for m in nc.get("markets") or []
                if str(m.get("marketTicker") or "").strip()
            ]
        normalized.append(nc)
    return normalized


def _rollup_files() -> tuple[Path, Path, Path]:
    """Return (primary, runoff, general) CSV paths."""
    return (
        DATA_DIR / "ballotpedia-attorney-general-primary-election-rollup.csv",
        DATA_DIR / "ballotpedia-attorney-general-runoff-election-rollup.csv",
        DATA_DIR / "ballotpedia-attorney-general-general-election-rollup.csv",
    )


def build_for_office() -> list[dict]:
    """Build candidate rows for attorney general."""
    primary_path, runoff_path, general_path = _rollup_files()

    primary_rows = bcr.load_csv(primary_path)
    runoff_rows = bcr.load_csv(runoff_path)
    general_rows = bcr.load_csv(general_path)

    # No canonical candidates JSON -- derive everything from Ballotpedia rollup rows.
    augmented = bcr.augment_candidates_with_ballotpedia_sources(
        candidates=[],
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
        general_rows=general_rows,
    )

    # Deduplication only -- no FEC finance data.
    reconciled = bcr.reconcile_candidates(augmented, finance_rows=[])

    # Load Kalshi contest index for AG.
    kalshi_contests = _load_kalshi_contests(_AG_CONTEST_INDEX)

    rollup = bcr.build_rollup(
        candidates=reconciled,
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
        general_rows=general_rows,
        finance_rows=[],
        kalshi_contests=kalshi_contests,
    )
    return rollup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build candidate-level attorney general rollup files"
    )
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rollup = build_for_office()
    out_csv = args.out_dir / "attorney-general-candidate-rollup-2026.csv"
    out_json = args.out_dir / "attorney-general-candidate-rollup-2026.json"
    input_files = list(_rollup_files())
    bcr.write_csv(out_csv, rollup)
    bcr.write_json(out_json, rollup, input_files)
    print(f"attorney-general: {len(rollup)} candidate rows")
    print(f"  CSV:  {out_csv}")
    print(f"  JSON: {out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
