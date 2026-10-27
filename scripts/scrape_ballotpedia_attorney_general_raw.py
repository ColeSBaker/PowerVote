#!/usr/bin/env python3
"""CLI wrapper for Ballotpedia attorney general raw page scraping."""
from __future__ import annotations

import argparse
from pathlib import Path

from ballotpedia_rollup.scrape_attorney_general import default_ag_config, run_ag_scrape
from ballotpedia_rollup.scrape_shared import RetryPolicy, ScrapeError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-attempts", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = default_ag_config(
        timeout_seconds=args.timeout,
        force_refresh=args.force_refresh,
        retry_policy=RetryPolicy(
            initial_delay_seconds=args.request_delay,
            max_attempts=args.max_attempts,
            backoff_multiplier=2.0,
        ),
    )
    try:
        summary = run_ag_scrape(config)
    except ScrapeError as exc:
        print(f"[fatal] {exc}")
        return 1

    print(
        "Done. "
        f"states={summary.state_pages} seats={summary.seat_pages} "
        f"cached={summary.files_cached} written={summary.files_written} "
        f"outdir={summary.outdir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
