#!/usr/bin/env python3
"""Snapshot storage and validation helpers for local-first publish pipeline."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ArtifactInput:
    name: str
    path: Path


def compute_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _count_rows(path: Path) -> int:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for _ in reader)
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            return len(payload)
        return 1
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    return 0


def build_snapshot_manifest(
    *,
    snapshot_id: str,
    snapshot_date: str,
    schema_version: str,
    source_lineage: Iterable[str],
    artifacts: Iterable[ArtifactInput],
    bucket: str,
    prefix: str,
    office_snapshot_dates: dict[str, str] | None = None,
) -> dict[str, Any]:
    artifact_payload: list[dict[str, Any]] = []
    for artifact in artifacts:
        row_count = _count_rows(artifact.path)
        artifact_payload.append(
            {
                "artifactName": artifact.name,
                "fileName": artifact.path.name,
                "uri": f"s3://{bucket}/{prefix}/{artifact.path.name}",
                "contentHash": compute_file_hash(artifact.path),
                "rowCount": row_count,
                "bytes": artifact.path.stat().st_size,
            }
        )

    manifest: dict[str, Any] = {
        "snapshotId": snapshot_id,
        "snapshotDate": snapshot_date,
        "schemaVersion": schema_version,
        "generatedAt": snapshot_id,
        "sourceLineage": list(source_lineage),
        "artifacts": artifact_payload,
    }
    if office_snapshot_dates:
        manifest["officeSnapshotDates"] = office_snapshot_dates
    return manifest


def evaluate_validation_gates(
    *,
    unresolved_high_impact: int,
    unresolved_included_senate_markets: int,
    schema_contract_ok: bool,
    artifact_hashes_ok: bool,
    required_artifacts_present: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    if unresolved_high_impact > 0:
        failures.append("unresolved_high_impact")
    if unresolved_included_senate_markets > 0:
        failures.append("unresolved_included_senate_markets")
    if not schema_contract_ok:
        failures.append("schema_contract")
    if not artifact_hashes_ok:
        failures.append("artifact_hash_mismatch")
    if not required_artifacts_present:
        failures.append("missing_required_artifacts")
    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "metrics": {
            "unresolvedHighImpact": unresolved_high_impact,
            "unresolvedIncludedSenateMarkets": unresolved_included_senate_markets,
            "schemaContractOk": schema_contract_ok,
            "artifactHashesOk": artifact_hashes_ok,
            "requiredArtifactsPresent": required_artifacts_present,
        },
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
