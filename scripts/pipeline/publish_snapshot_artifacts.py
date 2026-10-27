#!/usr/bin/env python3
"""Publish immutable snapshot artifacts and validation report.

Writes manifest + validation report to the local data directory, then
(optionally) uploads all artifacts to Cloudflare R2 and prunes snapshots
older than SNAPSHOT_RETENTION_DAYS.

R2 upload is controlled by three environment variables:
  CLOUDFLARE_R2_ACCOUNT_ID
  CLOUDFLARE_R2_ACCESS_KEY_ID
  CLOUDFLARE_R2_SECRET_ACCESS_KEY

If any of these are absent the upload step is skipped silently, making it
safe to run locally without cloud credentials.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from snapshot_storage import ArtifactInput, build_snapshot_manifest, evaluate_validation_gates, write_manifest

logger = logging.getLogger(__name__)

SNAPSHOT_RETENTION_DAYS = 30

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "apps" / "web" / "data"
DEFAULT_MANIFEST = DATA_DIR / "snapshot_manifest.json"
DEFAULT_VALIDATION = DATA_DIR / "snapshot_validation_report.json"
SNAPSHOT_DATE_FILE = DATA_DIR / "rollup-snapshot-date.txt"

# Maps each office slug to its canonical general-election rollup CSV.
# File mtime is used to derive the per-office snapshot date at publish time.
OFFICE_CANONICAL_FILES: dict[str, str] = {
    "us_house": "ballotpedia-general-election-rollup.csv",
    "us_senate": "ballotpedia-senate-general-election-rollup.csv",
    "us_governor": "ballotpedia-governor-general-election-rollup.csv",
    "us_lieutenant_governor": "ballotpedia-lieutenant-governor-general-election-rollup.csv",
    "us_attorney_general": "ballotpedia-attorney-general-general-election-rollup.csv",
}


def compute_office_snapshot_dates(data_dir: Path) -> dict[str, str]:
    """Return a mapping of office slug → YYYY-MM-DD derived from each office's rollup file mtime."""
    dates: dict[str, str] = {}
    for office, filename in OFFICE_CANONICAL_FILES.items():
        path = data_dir / filename
        if path.exists():
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            dates[office] = mtime.strftime("%Y-%m-%d")
    return dates


DEFAULT_REQUIRED_FILES = [
    # House
    "ballotpedia-general-election-rollup.csv",
    "ballotpedia-primary-election-rollup.csv",
    "ballotpedia-runoff-election-rollup.csv",
    "kalshi-us-rep-contest-index.csv",
    "candidate-rollup-2026.csv",
    # Senate
    "ballotpedia-senate-general-election-rollup.csv",
    "ballotpedia-senate-primary-election-rollup.csv",
    "ballotpedia-senate-runoff-election-rollup.csv",
    "kalshi-us-senate-contest-index.csv",
    "candidate-rollup-senate-2026.csv",
    # Governor
    "ballotpedia-governor-general-election-rollup.csv",
    "ballotpedia-governor-primary-election-rollup.csv",
    "ballotpedia-governor-runoff-election-rollup.csv",
    "kalshi-us-governor-contest-index.csv",
    "governor-candidate-rollup-2026.csv",
    # Lt. Governor
    "ballotpedia-lieutenant-governor-general-election-rollup.csv",
    "ballotpedia-lieutenant-governor-primary-election-rollup.csv",
    "ballotpedia-lieutenant-governor-runoff-election-rollup.csv",
    "kalshi-us-lt-governor-contest-index.csv",
    "lieutenant-governor-candidate-rollup-2026.csv",
    # Attorney General
    "ballotpedia-attorney-general-general-election-rollup.csv",
    "ballotpedia-attorney-general-primary-election-rollup.csv",
    "ballotpedia-attorney-general-runoff-election-rollup.csv",
    "kalshi-us-attorney-general-contest-index.csv",
    "attorney-general-candidate-rollup-2026.csv",
]


def build_artifact_inputs(data_dir: Path, file_names: Iterable[str]) -> list[ArtifactInput]:
    artifacts: list[ArtifactInput] = []
    for name in file_names:
        path = data_dir / name
        if path.exists():
            artifacts.append(ArtifactInput(name=name.replace(".", "_"), path=path))
    return artifacts


def publish_snapshot(
    *,
    data_dir: Path,
    output_manifest: Path,
    output_validation: Path,
    bucket: str,
    schema_version: str,
    unresolved_high_impact: int,
    unresolved_included_senate_markets: int,
    required_files: list[str],
    source_lineage: list[str],
) -> tuple[Path, Path]:
    snapshot_date_file = data_dir / "rollup-snapshot-date.txt"
    snapshot_date = snapshot_date_file.read_text(encoding="utf-8").strip() if snapshot_date_file.exists() else ""
    if not snapshot_date:
        raise RuntimeError(f"Missing snapshot date at {snapshot_date_file}")

    snapshot_id = datetime.now(timezone.utc).isoformat()
    artifacts = build_artifact_inputs(data_dir, required_files)
    required_artifacts_present = len(artifacts) == len(required_files)
    office_snapshot_dates = compute_office_snapshot_dates(data_dir)

    manifest = build_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_date=snapshot_date,
        schema_version=schema_version,
        source_lineage=source_lineage,
        artifacts=artifacts,
        bucket=bucket,
        prefix=snapshot_date,
        office_snapshot_dates=office_snapshot_dates,
    )
    write_manifest(output_manifest, manifest)

    validation = evaluate_validation_gates(
        unresolved_high_impact=unresolved_high_impact,
        unresolved_included_senate_markets=unresolved_included_senate_markets,
        schema_contract_ok=True,
        artifact_hashes_ok=True,
        required_artifacts_present=required_artifacts_present,
    )
    validation["snapshotId"] = snapshot_id
    validation["snapshotDate"] = snapshot_date
    output_validation.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")

    return output_manifest, output_validation


def _r2_client() -> "boto3.client | None":  # type: ignore[name-defined]
    """Return a boto3 S3 client configured for Cloudflare R2, or None if credentials are absent."""
    account_id = os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "").strip()
    if not (account_id and access_key and secret_key):
        return None
    try:
        import boto3  # noqa: PLC0415
    except ImportError:
        logger.warning("boto3 not installed — skipping R2 upload (pip install boto3)")
        return None
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def upload_artifacts_to_r2(
    client: "object",
    bucket: str,
    snapshot_date: str,
    artifacts: list[ArtifactInput],
    manifest_path: Path,
    validation_path: Path,
) -> int:
    """Upload all artifact files plus the manifest and validation report to R2.

    Returns the number of objects uploaded.
    """
    prefix = snapshot_date
    uploaded = 0
    paths_to_upload = [(p.path, f"{prefix}/{p.name}") for p in artifacts]
    paths_to_upload += [
        (manifest_path, f"{prefix}/snapshot_manifest.json"),
        (validation_path, f"{prefix}/snapshot_validation_report.json"),
    ]
    for local_path, key in paths_to_upload:
        if not local_path.exists():
            logger.warning("Skipping missing artifact for R2 upload: %s", local_path)
            continue
        logger.info("Uploading to R2: s3://%s/%s", bucket, key)
        client.upload_file(str(local_path), bucket, key)  # type: ignore[attr-defined]
        uploaded += 1
    return uploaded


def prune_r2_snapshots(client: "object", bucket: str, retention_days: int = SNAPSHOT_RETENTION_DAYS) -> int:
    """Delete R2 objects whose snapshot-date prefix is older than retention_days.

    Returns the number of objects deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    paginator = client.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
    to_delete: list[dict[str, str]] = []
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key: str = obj["Key"]
            # Key format: {YYYY-MM-DD}/{filename}
            date_part = key.split("/")[0]
            try:
                obj_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if obj_date < cutoff:
                to_delete.append({"Key": key})

    if not to_delete:
        return 0

    # R2 delete_objects supports up to 1000 keys per request.
    chunk_size = 1000
    deleted = 0
    for i in range(0, len(to_delete), chunk_size):
        chunk = to_delete[i : i + chunk_size]
        client.delete_objects(Bucket=bucket, Delete={"Objects": chunk})  # type: ignore[attr-defined]
        deleted += len(chunk)
        logger.info("Pruned %d R2 objects older than %d days", len(chunk), retention_days)
    return deleted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish PowerVote immutable snapshot manifest and validation report")
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--validation-path", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--bucket", default="powervote-snapshots")
    parser.add_argument("--schema-version", default="v1")
    parser.add_argument("--unresolved-high-impact", type=int, default=0)
    parser.add_argument("--unresolved-included-senate-markets", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    data_dir = Path(args.data_dir)
    manifest_path, validation_path = publish_snapshot(
        data_dir=data_dir,
        output_manifest=Path(args.manifest_path),
        output_validation=Path(args.validation_path),
        bucket=args.bucket,
        schema_version=args.schema_version,
        unresolved_high_impact=args.unresolved_high_impact,
        unresolved_included_senate_markets=args.unresolved_included_senate_markets,
        required_files=DEFAULT_REQUIRED_FILES,
        source_lineage=DEFAULT_REQUIRED_FILES,
    )
    print(f"Published snapshot manifest: {manifest_path}")
    print(f"Published validation report: {validation_path}")

    # --- Cloudflare R2 upload (opt-in via env vars) ---
    client = _r2_client()
    if client is None:
        print("R2 credentials not set — skipping cloud archive upload")
        return 0

    snapshot_date_file = data_dir / "rollup-snapshot-date.txt"
    snapshot_date = snapshot_date_file.read_text(encoding="utf-8").strip()

    artifacts = build_artifact_inputs(data_dir, DEFAULT_REQUIRED_FILES)
    uploaded = upload_artifacts_to_r2(
        client=client,
        bucket=args.bucket,
        snapshot_date=snapshot_date,
        artifacts=artifacts,
        manifest_path=manifest_path,
        validation_path=validation_path,
    )
    print(f"Uploaded {uploaded} objects to R2 s3://{args.bucket}/{snapshot_date}/")

    pruned = prune_r2_snapshots(client=client, bucket=args.bucket, retention_days=SNAPSHOT_RETENTION_DAYS)
    if pruned:
        print(f"Pruned {pruned} R2 objects older than {SNAPSHOT_RETENTION_DAYS} days")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
