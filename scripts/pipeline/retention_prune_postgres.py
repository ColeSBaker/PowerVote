#!/usr/bin/env python3
"""Prune old non-active ingest batches while preserving active snapshot history."""
from __future__ import annotations

import argparse
import os
from datetime import date, timedelta


def cutoff_date(days_to_keep: int) -> date:
    return date.today() - timedelta(days=days_to_keep)


def build_prune_sql() -> str:
    return """
    DELETE FROM pv.ingest_batches b
    WHERE b.snapshot_date < %s
      AND b.id <> (SELECT batch_id FROM pv.active_batch WHERE singleton_id = 1)
      AND b.status <> 'active'
    """


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune old staged/archived ingest batches")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--days-to-keep", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required (or pass --database-url).")

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for retention pruning. Install with `pip install psycopg[binary]`.") from exc

    cutoff = cutoff_date(args.days_to_keep)
    with psycopg.connect(args.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(build_prune_sql(), (cutoff,))
            deleted = cur.rowcount
        conn.commit()

    print(f"Pruned {deleted} batches older than {cutoff.isoformat()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
