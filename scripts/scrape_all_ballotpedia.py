#!/usr/bin/env python3
"""Scrape all Ballotpedia pages for all five offices with force-refresh.

Usage:
    python scripts/scrape_all_ballotpedia.py
    python scripts/scrape_all_ballotpedia.py --request-delay 1.5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ballotpedia_rollup.scrape_house import default_house_config, run_house_scrape
from ballotpedia_rollup.scrape_senate import default_senate_config, run_senate_scrape
from ballotpedia_rollup.scrape_governor import default_governor_config, run_governor_scrape
from ballotpedia_rollup.scrape_attorney_general import default_ag_config, run_ag_scrape
from ballotpedia_rollup.scrape_shared import RetryPolicy, ScrapeError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--request-delay", type=float, default=0.8, help="Seconds between requests (default: 0.8)")
    parser.add_argument("--max-attempts", type=int, default=5, help="Max retry attempts per page (default: 5)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds (default: 30.0)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    retry = RetryPolicy(
        initial_delay_seconds=args.request_delay,
        max_attempts=args.max_attempts,
        backoff_multiplier=2.0,
        reset_delay_seconds=4.0,
    )

    offices = [
        (
            "House",
            lambda: run_house_scrape(default_house_config(force_refresh=True, timeout_seconds=args.timeout, retry_policy=retry)),
        ),
        (
            "Senate",
            lambda: run_senate_scrape(default_senate_config(force_refresh=True, timeout_seconds=args.timeout, retry_policy=retry)),
        ),
        (
            "Governor",
            lambda: run_governor_scrape(default_governor_config(force_refresh=True, timeout_seconds=args.timeout, retry_policy=retry)),
        ),
        (
            "Attorney General",
            lambda: run_ag_scrape(default_ag_config(force_refresh=True, timeout_seconds=args.timeout, retry_policy=retry)),
        ),
    ]

    failed: list[str] = []
    for name, scrape_fn in offices:
        print(f"\n--- Scraping {name} ---")
        try:
            summary = scrape_fn()
            print(
                f"Done. states={summary.state_pages} seats={summary.seat_pages} "
                f"cached={summary.files_cached} written={summary.files_written} "
                f"outdir={summary.outdir}"
            )
        except ScrapeError as exc:
            print(f"[error] {name} scrape failed: {exc}")
            failed.append(name)

    if failed:
        print(f"\n[fatal] {len(failed)} office(s) failed: {', '.join(failed)}")
        return 1

    print("\nAll offices scraped successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
