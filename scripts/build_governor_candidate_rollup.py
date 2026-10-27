#!/usr/bin/env python3
"""Build candidate-level 2026 governor and lieutenant governor rollups.

Inputs:
- apps/web/data/ballotpedia-governor-{primary,runoff,general}-election-rollup.csv
- apps/web/data/ballotpedia-lieutenant-governor-{primary,runoff,general}-election-rollup.csv
- apps/web/data/kalshi-us-governor-contest-index.json
- apps/web/data/kalshi-us-lt-governor-contest-index.json

Outputs:
- apps/web/data/governor-candidate-rollup-2026.csv
- apps/web/data/governor-candidate-rollup-2026.json
- apps/web/data/lieutenant-governor-candidate-rollup-2026.csv
- apps/web/data/lieutenant-governor-candidate-rollup-2026.json
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

# Kalshi contest index files
_GOV_CONTEST_INDEX = DATA_DIR / "kalshi-us-governor-contest-index.json"
_LTGOV_CONTEST_INDEX = DATA_DIR / "kalshi-us-lt-governor-contest-index.json"

# Map from rollup prefix → contest index path
_KALSHI_INDEX_BY_PREFIX: dict[str, Path] = {
    "ballotpedia-governor": _GOV_CONTEST_INDEX,
    "ballotpedia-lieutenant-governor": _LTGOV_CONTEST_INDEX,
}


def _load_kalshi_contests(index_path: Path) -> list[dict[str, Any]]:
    """Load and normalize governor/lt-gov contest rows for the shared enrichment pipeline.

    The governor/lt-gov indexes use slightly different field names than the
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
        # build_kalshi_contest_indexes expects "seat", not "seat_id"
        nc.setdefault("seat", nc.get("seat_id"))
        # expects "party_lane", not "party"
        nc.setdefault("party_lane", nc.get("party"))
        # expects "market_role", not "market_type"
        nc.setdefault("market_role", nc.get("market_type"))
        # expects "market_tickers" list
        if "market_tickers" not in nc:
            nc["market_tickers"] = [
                str(m.get("marketTicker") or "")
                for m in nc.get("markets") or []
                if str(m.get("marketTicker") or "").strip()
            ]
        normalized.append(nc)
    return normalized


def _rollup_files(prefix: str) -> tuple[Path, Path, Path]:
    """Return (primary, runoff, general) CSV paths for the given prefix."""
    return (
        DATA_DIR / f"{prefix}-primary-election-rollup.csv",
        DATA_DIR / f"{prefix}-runoff-election-rollup.csv",
        DATA_DIR / f"{prefix}-general-election-rollup.csv",
    )


def build_for_office(prefix: str) -> list[dict]:
    """Build candidate rows for one office (governor or lt-governor)."""
    primary_path, runoff_path, general_path = _rollup_files(prefix)

    primary_rows = bcr.load_csv(primary_path)
    runoff_rows = bcr.load_csv(runoff_path)
    general_rows = bcr.load_csv(general_path)

    # No canonical candidates JSON — derive everything from Ballotpedia rollup rows.
    augmented = bcr.augment_candidates_with_ballotpedia_sources(
        candidates=[],
        primary_rows=primary_rows,
        runoff_rows=runoff_rows,
        general_rows=general_rows,
    )

    # Deduplication only — no FEC finance data.
    reconciled = bcr.reconcile_candidates(augmented, finance_rows=[])

    # Load Kalshi contest index for this office.
    kalshi_index_path = _KALSHI_INDEX_BY_PREFIX.get(prefix)
    kalshi_contests = _load_kalshi_contests(kalshi_index_path) if kalshi_index_path else []

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
        description="Build candidate-level governor and lt-governor rollup files"
    )
    parser.add_argument("--out-dir", type=Path, default=DATA_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for prefix, label in [
        ("ballotpedia-governor", "governor"),
        ("ballotpedia-lieutenant-governor", "lieutenant-governor"),
    ]:
        rollup = build_for_office(prefix)
        out_csv = args.out_dir / f"{label}-candidate-rollup-2026.csv"
        out_json = args.out_dir / f"{label}-candidate-rollup-2026.json"
        input_files = list(_rollup_files(prefix))
        bcr.write_csv(out_csv, rollup)
        bcr.write_json(out_json, rollup, input_files)
        print(f"{label}: {len(rollup)} candidate rows")
        print(f"  CSV:  {out_csv}")
        print(f"  JSON: {out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
