#!/usr/bin/env python3
"""Daily canonical refresh orchestration for PowerVote."""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[2]

# Ensure repo root is on sys.path so `scripts.*` imports resolve when the
# script is invoked directly (e.g. `python scripts/pipeline/run_daily_refresh.py`).
import sys as _sys
if str(REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(REPO_ROOT))

from scripts.logging_config import configure_logging

logger = configure_logging(name="powervote.pipeline")
RELEASE_METADATA_PATH = REPO_ROOT / "apps" / "web" / "data" / "release-metadata.json"
SNAPSHOT_DATE_PATH = REPO_ROOT / "apps" / "web" / "data" / "rollup-snapshot-date.txt"


@dataclass
class StepResult:
    name: str
    command: list[str]
    started_at: str
    finished_at: str
    exit_code: int
    stderr: str = ""


def run_step(name: str, command: Sequence[str], cwd: Path = REPO_ROOT) -> StepResult:
    logger.info("Starting step: %s", name)
    started = datetime.now(timezone.utc).isoformat()
    # stdout streams live to the terminal; stderr is captured so failures include
    # the error output in the exception message and in release-metadata.json.
    process = subprocess.run(command, cwd=cwd, text=True, stderr=subprocess.PIPE)
    finished = datetime.now(timezone.utc).isoformat()
    stderr = (process.stderr or "").strip()
    result = StepResult(
        name=name,
        command=list(command),
        started_at=started,
        finished_at=finished,
        exit_code=process.returncode,
        stderr=stderr,
    )
    if process.returncode != 0:
        detail = f"\n{stderr}" if stderr else ""
        logger.error("Step failed: %s%s", name, f" — {stderr}" if stderr else "")
        raise RuntimeError(f"Step failed ({name}): {' '.join(command)}{detail}")
    logger.info("Completed step: %s", name)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PowerVote daily refresh pipeline")
    parser.add_argument("--skip-db-load", action="store_true", help="Skip PostgreSQL staging/promote load step")
    parser.add_argument("--skip-frontend-tests", action="store_true", help="Skip Next.js test run")
    parser.add_argument("--run-retention-prune", action="store_true", help="Prune non-active historical staged batches after DB promote")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for DB load step")
    parser.add_argument(
        "--deploy-hook-url",
        default="",
        help="Optional deployment hook URL to trigger cache/materialized-view refresh after successful promote",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force re-scrape all Ballotpedia pages, ignoring cached data/raw/ files",
    )
    parser.add_argument(
        "--skip-kalshi-fetch",
        action="store_true",
        help="Skip live Kalshi market fetch (use existing ../kalshi/data/ files)",
    )
    return parser.parse_args()


def write_release_metadata(results: list[StepResult]) -> None:
    snapshot_date = SNAPSHOT_DATE_PATH.read_text(encoding="utf-8").strip() if SNAPSHOT_DATE_PATH.exists() else None
    payload = {
        "pipeline": "daily_refresh",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "snapshotDate": snapshot_date,
        "status": "success",
        "steps": [result.__dict__ for result in results],
    }
    RELEASE_METADATA_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    results: list[StepResult] = []

    # Stamp today's UTC date as the canonical snapshot date for this run.
    SNAPSHOT_DATE_PATH.write_text(
        datetime.now(timezone.utc).strftime("%Y-%m-%d") + "\n", encoding="utf-8"
    )
    logger.info("Snapshot date set to %s", SNAPSHOT_DATE_PATH.read_text(encoding="utf-8").strip())

    scrape_extra = ["--force-refresh"] if args.force_refresh else []

    # Fetch fresh Kalshi market + series data before building contest indices
    if not args.skip_kalshi_fetch:
        results.append(run_step("fetch_kalshi_markets", ["python", "scripts/fetch_kalshi_markets.py"]))

    # Canonical source rebuild — House
    results.append(run_step("scrape_ballotpedia_house", ["python", "scripts/scrape_ballotpedia_house_raw.py", "--outdir", "data/raw/ballotpedia_house_raw", *scrape_extra]))
    results.append(run_step("parse_ballotpedia_rollups", ["python", "scripts/parse_ballotpedia_house_raw.py"]))
    results.append(run_step("build_kalshi_us_rep_contest_index", ["python", "scripts/build_kalshi_us_rep_contest_index.py", "--no-strict"]))
    results.append(run_step("build_candidate_rollup", ["python", "scripts/build_candidate_rollup.py"]))

    # Canonical source rebuild — Senate
    results.append(run_step("scrape_ballotpedia_senate", ["python", "scripts/scrape_ballotpedia_senate_raw.py", "--outdir", "data/raw/ballotpedia_senate_raw", *scrape_extra]))
    results.append(run_step("parse_ballotpedia_senate_rollups", ["python", "scripts/parse_ballotpedia_senate_raw.py"]))
    results.append(run_step("build_kalshi_us_senate_contest_index", ["python", "scripts/build_kalshi_us_senate_contest_index.py", "--no-strict"]))
    results.append(run_step("build_senate_fec_linkage", ["python", "scripts/build_senate_fec_linkage.py"]))
    results.append(run_step("build_candidate_rollup_senate", ["python", "scripts/build_candidate_rollup_senate.py"]))

    # Canonical source rebuild — Governor + Lt. Governor
    results.append(run_step("scrape_ballotpedia_governor", ["python", "scripts/scrape_ballotpedia_governor_raw.py", "--outdir", "data/raw/ballotpedia_governor_raw", *scrape_extra]))
    results.append(run_step("parse_ballotpedia_governor_rollups", ["python", "scripts/parse_ballotpedia_governor_raw.py"]))
    results.append(run_step("build_kalshi_us_governor_contest_index", ["python", "scripts/build_kalshi_us_governor_contest_index.py", "--no-strict"]))
    results.append(run_step("build_kalshi_us_ltgov_contest_index", ["python", "scripts/build_kalshi_us_ltgov_contest_index.py", "--no-strict"]))
    results.append(run_step("build_governor_candidate_rollup", ["python", "scripts/build_governor_candidate_rollup.py"]))

    # Canonical source rebuild — Attorney General
    results.append(run_step("scrape_ballotpedia_attorney_general", ["python", "scripts/scrape_ballotpedia_attorney_general_raw.py", *scrape_extra]))
    results.append(run_step("parse_ballotpedia_attorney_general_rollups", ["python", "scripts/parse_ballotpedia_attorney_general_raw.py"]))
    results.append(run_step("build_kalshi_us_attorney_general_contest_index", ["python", "scripts/build_kalshi_us_attorney_general_contest_index.py", "--no-strict"]))
    results.append(run_step("build_attorney_general_candidate_rollup", ["python", "scripts/build_attorney_general_candidate_rollup.py"]))

    results.append(
        run_step(
            "publish_snapshot_artifacts",
            ["python", "scripts/pipeline/publish_snapshot_artifacts.py"],
        )
    )

    # Data quality and integrity suite
    results.append(
        run_step(
            "rollup_quality_tests",
            [
                "python",
                "-m",
                "pytest",
                "-q",
                "tests/test_ballotpedia_rollup_parser.py",
                "tests/test_ballotpedia_general_primary_status_buckets.py",
                "tests/test_ballotpedia_kalshi_rollup_integrity.py",
                "tests/test_candidate_rollup_data_quality.py",
                "tests/test_ballotpedia_senate_rollup_parser.py",
                "tests/test_kalshi_senate_contest_index.py",
                "tests/test_senate_fec_linkage.py",
                "tests/test_build_candidate_rollup_senate.py",
                "tests/test_ballotpedia_governor_rollup_parser.py",
                "tests/test_ballotpedia_attorney_general_rollup_parser.py",
                "tests/test_kalshi_governor_contest_index.py",
                "tests/test_kalshi_ltgov_contest_index.py",
                "tests/test_kalshi_attorney_general_contest_index.py",
                "tests/test_governor_ag_candidate_rollup_kalshi_integrity.py",
            ],
        )
    )

    if not args.skip_frontend_tests:
        web_dir = REPO_ROOT / "apps" / "web-next"
        results.append(run_step("web_next_install", ["npm", "install"], cwd=web_dir))
        results.append(run_step("web_next_tests", ["npm", "test"], cwd=web_dir))

    if not args.skip_db_load:
        command = [
            "python",
            "scripts/pipeline/load_rollups_to_postgres.py",
            "--apply-migration",
            "--promote",
        ]
        if args.database_url:
            command.extend(["--database-url", args.database_url])
        results.append(run_step("db_stage_and_promote", command))
        if args.run_retention_prune:
            retention_cmd = ["python", "scripts/pipeline/retention_prune_postgres.py"]
            if args.database_url:
                retention_cmd.extend(["--database-url", args.database_url])
            results.append(run_step("db_retention_prune", retention_cmd))

    deploy_hook_url = args.deploy_hook_url.strip()
    if deploy_hook_url:
        started = datetime.now(timezone.utc).isoformat()
        req = urllib_request.Request(
            deploy_hook_url,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"pipeline": "daily_refresh"}).encode("utf-8"),
        )
        with urllib_request.urlopen(req, timeout=30):
            pass
        finished = datetime.now(timezone.utc).isoformat()
        results.append(
            StepResult(
                name="deployment_hook_refresh",
                command=["POST", deploy_hook_url],
                started_at=started,
                finished_at=finished,
                exit_code=0,
            )
        )

    write_release_metadata(results)
    logger.info("Daily refresh pipeline completed successfully. %d steps ran.", len(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
