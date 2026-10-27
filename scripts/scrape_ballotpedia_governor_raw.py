#!/usr/bin/env python3
"""CLI wrapper for Ballotpedia governor and lieutenant governor raw page scraping."""
from __future__ import annotations

import argparse
from pathlib import Path

from ballotpedia_rollup.scrape_governor import default_governor_config, run_governor_scrape
from ballotpedia_rollup.scrape_shared import RetryPolicy, ScrapeError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default="ballotpedia_governor_raw")
    parser.add_argument("--max-attempts", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--office", default="state_governor")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.office not in {
        "state_governor",
        "state_lieutenant_governor",
        "governor",
        "lt_governor",
        "ltgov",
    }:
        print(f"[fatal] unsupported office for this wrapper: {args.office}")
        return 1

    config = default_governor_config(
        outdir=Path(args.outdir),
        timeout_seconds=args.timeout,
        force_refresh=args.force_refresh,
        retry_policy=RetryPolicy(
            initial_delay_seconds=args.request_delay,
            max_attempts=args.max_attempts,
            backoff_multiplier=2.0,
        ),
    )
    try:
        summary = run_governor_scrape(config)
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
