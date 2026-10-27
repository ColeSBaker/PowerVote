#!/usr/bin/env python3
"""Load canonical rollup CSV artifacts into PostgreSQL staging and optionally promote atomically.

Loads all five offices (us_house, us_senate, us_governor, us_lieutenant_governor,
us_attorney_general) into the same staging tables, keyed by (batch_id, seat_id) with
an `office` column for per-office filtering from the Next.js API.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "apps" / "web" / "data"
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"

SNAPSHOT_DATE_FILE = DATA_DIR / "rollup-snapshot-date.txt"
SNAPSHOT_MANIFEST_FILE = DATA_DIR / "snapshot_manifest.json"
SNAPSHOT_VALIDATION_FILE = DATA_DIR / "snapshot_validation_report.json"

# Per-office CSV file mapping.  Keys match the Office type in the Next.js domain schema.
OFFICE_FILES: dict[str, dict[str, Path]] = {
    "us_house": {
        "general":      DATA_DIR / "ballotpedia-general-election-rollup.csv",
        "primary":      DATA_DIR / "ballotpedia-primary-election-rollup.csv",
        "runoff":       DATA_DIR / "ballotpedia-runoff-election-rollup.csv",
        "kalshi_index": DATA_DIR / "kalshi-us-rep-contest-index.csv",
        "kalshi_audit": DATA_DIR / "kalshi-rollup-join-audit.csv",
    },
    "us_senate": {
        "general":      DATA_DIR / "ballotpedia-senate-general-election-rollup.csv",
        "primary":      DATA_DIR / "ballotpedia-senate-primary-election-rollup.csv",
        "runoff":       DATA_DIR / "ballotpedia-senate-runoff-election-rollup.csv",
        "kalshi_index": DATA_DIR / "kalshi-us-senate-contest-index.csv",
        "kalshi_audit": DATA_DIR / "kalshi-us-senate-contest-integrity-violations.csv",
    },
    "us_governor": {
        "general":      DATA_DIR / "ballotpedia-governor-general-election-rollup.csv",
        "primary":      DATA_DIR / "ballotpedia-governor-primary-election-rollup.csv",
        "runoff":       DATA_DIR / "ballotpedia-governor-runoff-election-rollup.csv",
        "kalshi_index": DATA_DIR / "kalshi-us-governor-contest-index.csv",
        "kalshi_audit": DATA_DIR / "kalshi-us-governor-contest-integrity-violations.csv",
    },
    "us_lieutenant_governor": {
        "general":      DATA_DIR / "ballotpedia-lieutenant-governor-general-election-rollup.csv",
        "primary":      DATA_DIR / "ballotpedia-lieutenant-governor-primary-election-rollup.csv",
        "runoff":       DATA_DIR / "ballotpedia-lieutenant-governor-runoff-election-rollup.csv",
        "kalshi_index": DATA_DIR / "kalshi-us-lt-governor-contest-index.csv",
        "kalshi_audit": DATA_DIR / "kalshi-us-lt-governor-contest-integrity-violations.csv",
    },
    "us_attorney_general": {
        "general":      DATA_DIR / "ballotpedia-attorney-general-general-election-rollup.csv",
        "primary":      DATA_DIR / "ballotpedia-attorney-general-primary-election-rollup.csv",
        "runoff":       DATA_DIR / "ballotpedia-attorney-general-runoff-election-rollup.csv",
        "kalshi_index": DATA_DIR / "kalshi-us-attorney-general-contest-index.csv",
        "kalshi_audit": DATA_DIR / "kalshi-us-attorney-general-contest-integrity-violations.csv",
    },
}

# Offices required to have nonzero general rows for the batch to be promotable.
REQUIRED_OFFICES = {"us_house", "us_senate", "us_governor"}


def normalize_seat_id(raw: str | None) -> str:
    text = (raw or "").strip().upper()
    match = re.match(r"^([A-Z]{2})-(AL|\d{1,2})$", text)
    if not match:
        return text
    state, district = match.groups()
    if district == "AL":
        return f"{state}-AL"
    return f"{state}-{int(district):02d}"


def parse_bool(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"true", "1", "yes"}


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validation_allows_promote(validation_payload: dict) -> bool:
    return bool(validation_payload.get("passed") is True)


def ensure_files_exist(paths: list[Path]) -> None:
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required pipeline inputs:\n- " + "\n- ".join(missing))


def ensure_required_files_exist() -> None:
    """Verify snapshot date and at least the House CSVs exist before connecting to DB."""
    ensure_files_exist([SNAPSHOT_DATE_FILE, *OFFICE_FILES["us_house"].values()])


@dataclass
class OfficeCounts:
    general: int = 0
    primary: int = 0
    runoff: int = 0
    kalshi_index: int = 0
    kalshi_audit: int = 0


@dataclass
class PipelineCounts:
    by_office: dict[str, OfficeCounts] = field(default_factory=dict)

    def total_general(self) -> int:
        return sum(c.general for c in self.by_office.values())

    def summary(self) -> str:
        lines = []
        for office, c in self.by_office.items():
            lines.append(
                f"  {office}: general={c.general} primary={c.primary}"
                f" runoff={c.runoff} kalshi_index={c.kalshi_index} kalshi_audit={c.kalshi_audit}"
            )
        return "\n".join(lines)


def load_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load canonical rollups into PostgreSQL staging tables")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--promote", action="store_true", help="Mark loaded batch as active after integrity checks")
    parser.add_argument("--apply-migration", action="store_true", help="Apply db/migrations/*.sql before loading")
    parser.add_argument("--manifest-path", default=str(SNAPSHOT_MANIFEST_FILE))
    parser.add_argument("--validation-path", default=str(SNAPSHOT_VALIDATION_FILE))
    parser.add_argument(
        "--offices",
        nargs="+",
        default=list(OFFICE_FILES.keys()),
        choices=list(OFFICE_FILES.keys()),
        help="Which offices to load (default: all five)",
    )
    return parser.parse_args()


def load_office_into_db(cur, batch_id: int, office: str, files: dict[str, Path]) -> OfficeCounts:
    """Insert all CSV rows for one office into staging tables.  Returns row counts."""
    counts = OfficeCounts()

    general_rows = load_csv_rows(files["general"]) if files["general"].exists() else []
    primary_rows = load_csv_rows(files["primary"]) if files["primary"].exists() else []
    runoff_rows  = load_csv_rows(files["runoff"])  if files["runoff"].exists()  else []
    index_rows   = load_csv_rows(files["kalshi_index"]) if files["kalshi_index"].exists() else []
    audit_rows   = load_csv_rows(files["kalshi_audit"])  if files["kalshi_audit"].exists()  else []

    for row in general_rows:
        seat = normalize_seat_id(row.get("seat"))
        cur.execute(
            """
            INSERT INTO pv.stg_general_rollup (
              batch_id, seat_id, state_code, office,
              general_status, incumbent_party,
              dccc_target, nrcc_target, primary_status_d, primary_status_r,
              payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (batch_id, seat_id) DO NOTHING
            """,
            (
                batch_id,
                seat,
                seat.split("-")[0] if "-" in seat else "",
                office,
                row.get("general_status"),
                row.get("incumbent_party"),
                parse_bool(row.get("dccc_target")),
                parse_bool(row.get("nrcc_target")),
                row.get("primary_status_d"),
                row.get("primary_status_r"),
                json.dumps(row),
            ),
        )
        counts.general += 1

    for row in primary_rows:
        cur.execute(
            """
            INSERT INTO pv.stg_primary_rollup (
              batch_id, primary_id, seat_id, office, party, status, round, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (batch_id, primary_id) DO NOTHING
            """,
            (
                batch_id,
                row.get("primary_id"),
                normalize_seat_id(row.get("seat")),
                office,
                row.get("party"),
                row.get("status"),
                row.get("round"),
                json.dumps(row),
            ),
        )
        counts.primary += 1

    for row in runoff_rows:
        cur.execute(
            """
            INSERT INTO pv.stg_runoff_rollup (
              batch_id, primary_id, seat_id, office, party, status, runoff_id, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (batch_id, primary_id) DO NOTHING
            """,
            (
                batch_id,
                row.get("primary_id"),
                normalize_seat_id(row.get("seat")),
                office,
                row.get("party"),
                row.get("status"),
                row.get("runoff_id"),
                json.dumps(row),
            ),
        )
        counts.runoff += 1

    for row in index_rows:
        cur.execute(
            """
            INSERT INTO pv.stg_kalshi_contest_index (
              batch_id, contest_id, seat_id, office, round, party_lane, market_count, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (batch_id, contest_id) DO NOTHING
            """,
            (
                batch_id,
                row.get("contest_id"),
                normalize_seat_id(row.get("seat")),
                office,
                row.get("round"),
                row.get("party_lane"),
                int(row.get("market_count") or 0),
                json.dumps(row),
            ),
        )
        counts.kalshi_index += 1

    for row in audit_rows:
        audit_id = row.get("id") or f"{office}:{row.get('row_type','row')}:{row.get('seat','')}"
        cur.execute(
            """
            INSERT INTO pv.stg_kalshi_join_audit (
              batch_id, audit_id, seat_id, office, row_type, sum_status, odds_map_sum, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (batch_id, audit_id) DO NOTHING
            """,
            (
                batch_id,
                audit_id,
                normalize_seat_id(row.get("seat")),
                office,
                row.get("row_type"),
                row.get("sum_status"),
                float(row.get("odds_map_sum") or 0),
                json.dumps(row),
            ),
        )
        counts.kalshi_audit += 1

    return counts


def main() -> int:
    args = load_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required (or pass --database-url).")

    ensure_required_files_exist()

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required. Install with: pip install psycopg[binary]") from exc

    snapshot_date = SNAPSHOT_DATE_FILE.read_text(encoding="utf-8").strip()
    manifest_path = Path(args.manifest_path)
    validation_path = Path(args.validation_path)
    manifest_payload = load_json_payload(manifest_path) if manifest_path.exists() else {}
    validation_payload = load_json_payload(validation_path) if validation_path.exists() else {}

    offices_to_load = args.offices
    source_lineage = json.dumps(
        [str(files[k].name) for office in offices_to_load for k, files in [(office, OFFICE_FILES[office])]]
    )

    counts = PipelineCounts()

    with psycopg.connect(args.database_url) as conn:
        with conn.cursor() as cur:
            if args.apply_migration:
                for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    print(f"  Applying migration: {migration_path.name}")
                    cur.execute(migration_path.read_text(encoding="utf-8"))

            cur.execute(
                """
                INSERT INTO pv.ingest_batches (snapshot_date, status, source_lineage)
                VALUES (%s, 'staged', %s::jsonb)
                RETURNING id
                """,
                (snapshot_date, source_lineage),
            )
            batch_id = int(cur.fetchone()[0])
            print(f"Created batch {batch_id} for snapshot_date={snapshot_date}")

            for office in offices_to_load:
                files = OFFICE_FILES[office]
                office_counts = load_office_into_db(cur, batch_id, office, files)
                counts.by_office[office] = office_counts
                print(f"  {office}: general={office_counts.general} primary={office_counts.primary}"
                      f" runoff={office_counts.runoff}")

            # Integrity check: required offices must have nonzero general rows.
            failed_offices = [
                o for o in REQUIRED_OFFICES
                if o in offices_to_load and counts.by_office.get(o, OfficeCounts()).general == 0
            ]
            if failed_offices:
                raise RuntimeError(
                    f"Integrity failure: zero general rows for required offices: {failed_offices}"
                )

            if manifest_payload:
                for artifact in manifest_payload.get("artifacts", []):
                    cur.execute(
                        """
                        INSERT INTO pv.snapshot_artifacts (
                          batch_id, artifact_name, artifact_uri, content_hash,
                          row_count, schema_version, source_lineage
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (batch_id, artifact_name) DO UPDATE
                        SET artifact_uri = EXCLUDED.artifact_uri,
                            content_hash = EXCLUDED.content_hash,
                            row_count = EXCLUDED.row_count,
                            schema_version = EXCLUDED.schema_version,
                            source_lineage = EXCLUDED.source_lineage
                        """,
                        (
                            batch_id,
                            artifact.get("artifactName", ""),
                            artifact.get("uri", ""),
                            artifact.get("contentHash", ""),
                            int(artifact.get("rowCount") or 0),
                            manifest_payload.get("schemaVersion", "v1"),
                            json.dumps(manifest_payload.get("sourceLineage") or []),
                        ),
                    )

            if validation_payload:
                validation_details = validation_payload.get("metrics", {})
                validation_rows = [
                    ("snapshot_validation_passed", "pass" if validation_payload.get("passed") else "fail", validation_details),
                ]
                for failure in validation_payload.get("failures", []):
                    validation_rows.append((f"gate_{failure}", "fail", {"failure": failure}))
                for gate_name, status, details in validation_rows:
                    cur.execute(
                        """
                        INSERT INTO pv.snapshot_validation_results (batch_id, gate_name, status, details)
                        VALUES (%s, %s, %s, %s::jsonb)
                        ON CONFLICT (batch_id, gate_name) DO UPDATE
                        SET status = EXCLUDED.status,
                            details = EXCLUDED.details
                        """,
                        (batch_id, gate_name, status, json.dumps(details)),
                    )

            if args.promote:
                if validation_payload and not validation_allows_promote(validation_payload):
                    raise RuntimeError(
                        f"Validation report failed blocking gates; promotion aborted: {validation_path}"
                    )
                cur.execute("UPDATE pv.active_batch SET batch_id = %s WHERE singleton_id = 1", (batch_id,))
                cur.execute("UPDATE pv.ingest_batches SET status = 'active' WHERE id = %s", (batch_id,))
                cur.execute(
                    "UPDATE pv.ingest_batches SET status = 'archived' WHERE id <> %s AND status = 'active'",
                    (batch_id,),
                )
                print(f"Promoted batch {batch_id} as active.")

            conn.commit()

    print(f"\nLoaded {counts.total_general()} total general rows across {len(offices_to_load)} offices.")
    print(counts.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
