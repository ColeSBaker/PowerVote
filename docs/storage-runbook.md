# Snapshot Storage Runbook

## Local stack
1. `docker compose -f docker-compose.storage.yml --env-file .env.storage.example up -d`
2. Validate Postgres is up (`localhost:5432`).

## Run the pipeline locally
```bash
# Full run (Kalshi fetch + all offices + quality tests, skip DB and frontend tests)
python scripts/pipeline/run_daily_refresh.py --skip-db-load --skip-frontend-tests

# With DB load/promote (requires Postgres running)
python scripts/pipeline/run_daily_refresh.py --skip-frontend-tests

# Skip live Kalshi fetch (use existing ../kalshi/data/ files)
python scripts/pipeline/run_daily_refresh.py --skip-kalshi-fetch --skip-db-load --skip-frontend-tests
```

## DB load/promote (standalone)
```bash
python scripts/pipeline/load_rollups_to_postgres.py --apply-migration --promote
```

## Artifact archive (Cloudflare R2)
Artifacts are automatically uploaded to `s3://powervote-snapshots/{snapshot_date}/` by
`publish_snapshot_artifacts.py` when `CLOUDFLARE_R2_ACCOUNT_ID`, `CLOUDFLARE_R2_ACCESS_KEY_ID`,
and `CLOUDFLARE_R2_SECRET_ACCESS_KEY` env vars are set. R2 upload is silently skipped if they
are absent (safe for local dev).

## Restore from snapshot
1. Select the desired `snapshot_date` from `apps/web/data/snapshot_manifest.json` or from
   the R2 bucket prefix list.
2. Download artifacts from R2 key prefix `powervote-snapshots/{snapshot_date}/`.
3. Re-run loader against the restored artifacts and promote:
   `python scripts/pipeline/load_rollups_to_postgres.py --apply-migration --promote`

## Retention defaults
- R2: 30-day rolling window; objects with date prefixes older than 30 days are pruned automatically
  by `publish_snapshot_artifacts.py` after each successful upload.
- Postgres: keep 90 days of staged batches; never delete `pv.active_batch`.
