# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Frontend (Next.js)
```bash
cd apps/web-next
npm run dev          # Start dev server
npm run build        # Production build
npm run lint         # ESLint
npm test             # Vitest unit tests
npm run test:watch   # Watch mode
npm run test:e2e     # Playwright E2E tests
```

**If the dev server returns 500 on `/powervote` or any App Router page** after significant code changes, the `.next` cache is stale. Clear it and restart:
```bash
cd apps/web-next && rm -rf .next && npm run dev
```
This happens because Next.js caches compiled server bundles; adding new components or rearranging imports can leave the cache in a state that can't serve the page. The API routes (`/api/v1/*`) are compiled separately and typically survive, which is why the API can return 200 while the page itself returns 500.

**Import ordering in `"use client"` components:** All `import` statements must appear before any `const`/`let` declarations at the module level. Mixing them (e.g., `const X = false` before an `import`) can confuse Next.js's App Router module analysis and trigger cache corruption on the next build.

### Python Data Pipeline
```bash
# Run full daily ETL (all five offices: House, Senate, Governor, Lt. Governor, Attorney General)
python scripts/pipeline/run_daily_refresh.py

# Common flags
python scripts/pipeline/run_daily_refresh.py --skip-db-load           # Skip PostgreSQL load/promote
python scripts/pipeline/run_daily_refresh.py --skip-frontend-tests    # Skip Next.js test run
python scripts/pipeline/run_daily_refresh.py --skip-kalshi-fetch      # Use existing ../kalshi/data/ files
python scripts/pipeline/run_daily_refresh.py --force-refresh          # Re-scrape all Ballotpedia pages

# Individual pipeline steps — per-office order: scrape → parse → build_kalshi → build_rollup
# House
python scripts/scrape_ballotpedia_house_raw.py --outdir data/raw/ballotpedia_house_raw
python scripts/parse_ballotpedia_house_raw.py
python scripts/build_kalshi_us_rep_contest_index.py --no-strict
python scripts/build_candidate_rollup.py

# Senate
python scripts/scrape_ballotpedia_senate_raw.py --outdir data/raw/ballotpedia_senate_raw
python scripts/parse_ballotpedia_senate_raw.py
python scripts/build_kalshi_us_senate_contest_index.py --no-strict
python scripts/build_senate_fec_linkage.py
python scripts/build_candidate_rollup_senate.py

# Governor + Lt. Governor
python scripts/scrape_ballotpedia_governor_raw.py --outdir data/raw/ballotpedia_governor_raw
python scripts/parse_ballotpedia_governor_raw.py
python scripts/build_kalshi_us_governor_contest_index.py --no-strict
python scripts/build_kalshi_us_ltgov_contest_index.py --no-strict
python scripts/build_governor_candidate_rollup.py

# Attorney General
python scripts/scrape_ballotpedia_attorney_general_raw.py
python scripts/parse_ballotpedia_attorney_general_raw.py
python scripts/build_kalshi_us_attorney_general_contest_index.py --no-strict
python scripts/build_attorney_general_candidate_rollup.py

# Publish snapshot artifacts (manifest + validation report)
python scripts/pipeline/publish_snapshot_artifacts.py

# Python tests
python -m unittest discover -s tests -v
pytest -q tests/test_ballotpedia_rollup_parser.py   # Run a single test module
```

### Raw Input Data (`data/raw/`)

Parse scripts read Ballotpedia HTML snapshots from `data/raw/<office>/` by default:

| Script | Default input directory |
|--------|------------------------|
| `parse_ballotpedia_house_raw.py` | `data/raw/ballotpedia_house_raw/` |
| `parse_ballotpedia_senate_raw.py` | `data/raw/ballotpedia_senate_raw/` |
| `parse_ballotpedia_governor_raw.py` | `data/raw/ballotpedia_governor_raw/` |
| `parse_ballotpedia_attorney_general_raw.py` | `data/raw/ballotpedia_attorney_general_raw/` |

The `data/raw/` tree is gitignored. Scrape scripts populate it automatically when the pipeline runs. To scrape manually:

```bash
python scripts/scrape_ballotpedia_house_raw.py --outdir data/raw/ballotpedia_house_raw
python scripts/scrape_ballotpedia_senate_raw.py --outdir data/raw/ballotpedia_senate_raw
python scripts/scrape_ballotpedia_governor_raw.py --outdir data/raw/ballotpedia_governor_raw
python scripts/scrape_ballotpedia_attorney_general_raw.py
```

Each parse script also accepts `--input-dir <path>` to override the default.

### Kalshi Market Data

`scripts/fetch_kalshi_markets.py` fetches all Election series and open markets from the public Kalshi API (no API key required) and writes individual JSON files to `../kalshi/data/markets/` and `../kalshi/data/series/` (a sibling workspace directory). This runs as **step 1** of the daily pipeline, before any contest index builder, so all five offices always use fresh prices.

```bash
# Fetch fresh Kalshi market + series data (run before building contest indices)
python scripts/fetch_kalshi_markets.py

# Optional overrides
python scripts/fetch_kalshi_markets.py --market-dir /path/to/markets --series-dir /path/to/series
```

`build_kalshi_us_*_contest_index.py` scripts read from those directories. If the directory doesn't exist or the fetch is skipped (via `--skip-kalshi-fetch`), they fall back to `test_data/kalshi/` for minimal coverage. The committed contest index files in `apps/web/data/` serve as the stable deployed baseline.

### Adding Test Fixtures

Parser tests in `tests/` load real Ballotpedia HTML snapshots from `test_data/candidates/ballotpedia/<office>_raw/`. That directory, `test_data/kalshi/` and `test_data/kalshi_json_data/` are gitignored third-party data kept only locally; tests that need them skip when they are absent (see `tests/conftest.py`). To add coverage for a new state or edge case:

1. Scrape the target page into the fixture directory:
   ```bash
   # Example: capture CA governor page
   python scripts/scrape_ballotpedia_governor_raw.py --states CA --output-dir test_data/candidates/ballotpedia/ballotpedia_governor_raw/
   ```
2. Add assertions for the new seat in `tests/test_ballotpedia_governor_rollup_parser.py`.

Priority states to add for broader governor coverage: **CA** (top-two primary), **TX** (open seat), **FL** (term-limited incumbent).

### Local Storage Stack
```bash
docker compose -f docker-compose.storage.yml up -d   # PostgreSQL + PostGIS + MinIO
python scripts/pipeline/load_rollups_to_postgres.py  # Load CSV data to DB
```

## Architecture

PowerVote is a three-tier election intelligence platform:

### 1. Data Ingestion Layer (Python, `/scripts/`)

Raw HTML scrapers pull from Ballotpedia for House/Senate/Governor races. The core parsing logic lives in the `scripts/ballotpedia_rollup/` package:
- `parser.py` — core election parsing; emits `GeneralElectionRow` / `PrimaryElectionRow`
- `fec_matching.py` — deterministic FEC candidate linkage (name + state fuzzy match)
- `kalshi.py` — maps Kalshi prediction market tickers to districts/candidates
- `models.py` — data contracts (Pydantic-like dataclasses)

Output: CSV files written to `apps/web/data/` (e.g., `ballotpedia-house-election-rollup.csv`, `candidate-rollup-2026.json`).

### 2. Canonical Data Layer (PostgreSQL + JSON/CSV snapshots + static artifacts)

- **PostgreSQL + PostGIS** schema at `db/schema.sql` — staging tables, promotion views, geocoding cache. Used by the pipeline for ingestion staging, by `geocoder.ts` for address caching, and (optionally) by the frontend's data layer for general/primary/runoff rows when `DATABASE_URL` is set.
- **JSON/CSV snapshots** in `apps/web/data/` — committed to git daily by CI; consumed by the build-time artifact generator and by API routes (always for candidate rollups/departures; for core rows when no DB is configured)
- **Pre-rendered static artifacts** in `apps/web-next/public/data/` — generated at build time from the snapshots; served directly for the most common API responses (~30ms cold-load)
- `us-house-election-view.json` — UI-ready display data combining seat metadata, candidates, and market signals
- `candidate-rollup-2026.json` — per-candidate data with FEC IDs and Kalshi odds

### 3. Frontend Application Layer (Next.js, `/apps/web-next/`)

**Two primary views:**
- **Map View** (`/map`) — Interactive MapLibre GL map of U.S. House/Senate districts, color-coded by competitiveness
- **PowerVote View** (`/powervote`) — Address-to-ballot lookup with competitiveness scoring and candidate comparison

**API routes** (`/api/v1/*`) — Next.js route handlers that load data via `lib/server/data-source.ts` (Postgres when configured, else JSON/CSV snapshots), apply Zod validation, and return JSON:
- `GET /api/v1/map/districts` — district geometries with color legend
- `GET /api/v1/districts/[seatId]` — district detail with candidates and markets
- `GET /api/v1/powervote` — address → elections lookup
- `GET /api/v1/powervote/all` — cross-office context (House + Senate + Governor + Lt. Gov + AG)
- `GET /api/v1/powervote/compare` — two-location side-by-side comparison
- `GET /api/v1/powervote/options` — seat options for ambiguous lookups
- `GET /api/v1/mobile/{bootstrap,delta,seat}` — mobile sync
- Also: `zipcode-lookup`, `address-suggest`, `health`

**Key internal libraries** (`/apps/web-next/lib/`):
- `server/data-source.ts` — central data access point; loads and caches rollups (DB-first via `server/db.ts`, CSV fallback); data dir resolved by `server/paths.ts` (`DATA_DIR` env var or probes for `apps/web/data/`)
- `server/api-service.ts` — builds API responses
- `server/metrics.ts` + `scoring/` — competitiveness scoring (market, polling, targeting, incumbency sub-scores → composite → color band)
- `server/geocoder.ts` — US Census geocoding with Postgres L2 cache
- `server/zipcode-centroids.ts` — zipcode → lat/lng for map centering
- `domain/schemas.ts` — Zod schemas for all API payloads

### Data Flow

```
Kalshi API (public)
    ↓ fetch_kalshi_markets.py → ../kalshi/data/{markets,series}/
Ballotpedia HTML
    ↓ scraper (Python)
Raw HTML (ephemeral, not persisted)
    ↓ parser + FEC matching + Kalshi enrichment
apps/web/data/*.json + *.csv  (committed to git by CI)
    ↓ generate-static-artifacts.ts (build time)
apps/web-next/public/data/  (pre-rendered JSON, committed to git)
    ↓ Next.js serves static file (Cache-Control: max-age=3600)
Browser (Map View / PowerVote View)
```

The CI/CD pipeline (`.github/workflows/daily-rollup-etl.yml`) runs this full flow daily at 10:20 UTC, commits updated artifacts to `main`, and triggers an automatic Vercel redeploy.

**Static artifact serving:** `/api/v1/map/districts` and `/api/v1/mobile/bootstrap` check for a pre-rendered file in `apps/web-next/public/data/` first (served in ~30ms). Dynamic generation is retained as fallback for unrecognized param combos.

**PostgreSQL role:** The pipeline stages, validates and promotes each batch (`load_rollups_to_postgres.py`). At request time the frontend uses Postgres in two places, both opt-in via `DATABASE_URL`:
- `lib/server/data-source.ts` reads general/primary/runoff rows from the `pv.v_*_rollup_current` views when an active batch exists. Candidate rollups and departures still come from CSV. If `DATABASE_URL` is unset or the DB has no rows for an office, it falls back to the CSV snapshots. A newly promoted batch changes the cache revision (`db:<batchId>`) and invalidates the in-process cache.
- `geocoder.ts` uses the `geocoded_addresses` table as an L2 cache between in-memory and the US Census API.

### Key Data Files

| File | Purpose |
|------|---------|
| `apps/web/data/candidate-rollup-2026.csv` | House candidate-level FEC + Kalshi data |
| `apps/web/data/candidate-rollup-senate-2026.csv` | Senate candidate-level data |
| `apps/web/data/governor-candidate-rollup-2026.csv` | Governor + Lt. Governor candidate data |
| `apps/web/data/attorney-general-candidate-rollup-2026.csv` | AG candidate data |
| `apps/web/data/kalshi-us-rep-contest-index.json` | Kalshi market ticker → House district map |
| `apps/web/data/kalshi-us-senate-contest-index.json` | Kalshi market ticker → Senate seat map |
| `apps/web/data/ballotpedia-*-election-rollup.csv` | Parsed Ballotpedia election records |
| `db/schema.sql` | PostgreSQL schema (PostGIS) |

### Tests

Python tests in `/tests/` cover parser correctness, data quality, Kalshi rollup integrity, and performance. TypeScript tests in `/apps/web-next/tests/` cover API route handlers and scoring logic. The daily pipeline runs `pytest` against both suites before DB promotion.
