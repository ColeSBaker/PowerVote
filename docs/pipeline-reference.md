# Pipeline Reference

Detailed notes on individual pipeline builders, canonical data files, and legacy tooling. See the top-level `README.md` for an overview and quick start.

## Repository status
This repository now includes an initial clickable state-level web map with U.S. address lookup:

- Web prototype (static HTML/CSS/JS): `apps/web`
- Next.js product surface (Map View + PowerVote View): `apps/web-next`
- Architecture blueprint: `docs/architecture.md`
- Initial PostgreSQL/PostGIS schema: `db/schema.sql`
- MVP OpenAPI contract: `api/openapi.yaml`

## Next.js application (new system of record)

The repository now includes a Next.js + TypeScript implementation with:

- API contracts under `/api/v1/*` for map districts, district detail, and PowerVote address flows
- MapLibre-based district map with general/primary color modes
- U.S. Census geocoder integration for PowerVote
- Weighted competitiveness scoring (market + polling proxy + targeting)

### Run locally
```bash
cd apps/web-next
npm install
npm run dev
```

### Run frontend tests
```bash
cd apps/web-next
npm test
```

## Web prototype (state map + address lookup)
The prototype includes:

- Clickable U.S. state map (state selection/highlight)
- Address lookup powered by OpenStreetMap Nominatim
- Automatic state selection from lookup results

### Run locally
```bash
cd apps/web
python -m http.server 5173
```

Then open `http://localhost:5173`.

## Run test suite
A Python unit test suite is included for ingestion and indexing components. Run:

```bash
python -m unittest discover -s tests -v
```

To profile pytest runtime concentration (slowest tests + module totals), run (includes setup/call/teardown phase timing when pytest is executed):

```bash
python scripts/profile_pytest_timings.py -- tests -q
```

If you already have a JUnit XML report and do not want to re-run tests (call-phase timing only):

```bash
python scripts/profile_pytest_timings.py --parse-only --junitxml .tmp/pytest-timings.xml
```

To split CI/local runs into fast vs heavy lanes:

```bash
# Fast lane
python -m pytest tests -m "not slow_integrity" -q

# Heavy integrity lane
python -m pytest tests -m "slow_integrity" -q
```

## Daily ETL and DB promotion

Daily automation is implemented by:

- Orchestrator script: `scripts/pipeline/run_daily_refresh.py`
- PostgreSQL loader/promoter: `scripts/pipeline/load_rollups_to_postgres.py`
- CI schedule: `.github/workflows/daily-rollup-etl.yml`
- DB staging/view migration: `db/migrations/20260402_rollup_pipeline.sql`

Local run (without DB load):

```bash
python scripts/pipeline/run_daily_refresh.py --skip-db-load
```

## Local-first production storage stack

Use the local Docker stack for production-grade parity:

```bash
docker compose -f docker-compose.storage.yml --env-file .env.storage.example up -d
```

This provisions:
- PostgreSQL + PostGIS (`localhost:5432`)
- MinIO S3-compatible snapshot lake (`localhost:9000`, console `localhost:9001`)

Snapshot publishing artifacts:
- `apps/web/data/snapshot_manifest.json`
- `apps/web/data/snapshot_validation_report.json`

Retention utility:

```bash
python scripts/pipeline/retention_prune_postgres.py --days-to-keep 90
```

## Recommended stack
- TypeScript for frontend and API services
- Python for ingestion and normalization workers
- PostgreSQL + PostGIS for canonical geospatial/election data

## Kalshi public market ingestion (no API key)
To support autonomous ingestion from Kalshi's public elections API, this repo includes:

- Script: `scripts/fetch_kalshi_series.py`
- Default endpoint: `https://api.elections.kalshi.com/trade-api/v2/series`
- Default output file and fallback cache: `data/kalshi/series.json`

Run it with:

```bash
python scripts/fetch_kalshi_series.py
```

Recommended autonomous mode (retries + direct fallback if proxy blocks Kalshi):

```bash
python scripts/fetch_kalshi_series.py --bypass-proxy-for-kalshi --retries 3 --retry-delay 2
```

Common options:

```bash
python scripts/fetch_kalshi_series.py \
  --output data/kalshi/custom.json \
  --cache-fallback data/kalshi/series.json \
  --timeout 20
```

### Tunnel/proxy 403 troubleshooting
If you still get proxy tunnel `403` errors:

1. Ensure egress policy allows `api.elections.kalshi.com:443`.
2. Set `NO_PROXY=api.elections.kalshi.com` (or use `--bypass-proxy-for-kalshi`).
3. Keep cache fallback enabled so scheduled jobs can continue with stale data.


## State market categorization workflow (Kalshi snapshots)
A workflow is now included to categorize locally saved Kalshi markets by:

- U.S. state
- seat type (Statewide, US-SEN, US-REP, State-SEN, State-REP)
- election type (`primary` vs `main`)
- winner-focused contracts only (candidate/party winner or nominee winner style markets)

### Build the state market index
```bash
python scripts/build_state_market_index.py
```

This reads files from `test_data/kalshi_json_data` and writes:

- `apps/web/data/state-election-markets.json`

The web app loads this JSON and shows the indexed markets whenever a state is selected.

## Canonical U.S. House seat index (Census / NTAD)
A new builder is included for canonical congressional seat metadata sourced from Census/NTAD district rows. It is designed to become the ground-truth join layer between market data and future GIS features.

Run:

```bash
python scripts/build_us_house_seat_index.py
```

Expected input:

- `test_data/maps/Congressional/NTAD_Congressional_Districts_-128469763264767056*.csv`
- or `test_data/maps/NTAD_Congressional_Districts_03182026/NTAD_Congressional_Districts_-128469763264767056.csv`

Output:

- `apps/web/data/us-house-seats.json`

Each seat object includes canonical seat identifiers, state/district metadata, source lineage, market ID aliases for at-large seats, and GIS placeholders such as centroid and area fields.

**Canonical role:** `apps/web/data/us-house-seats.json` is the canonical raw-filings dataset. It is the ground-truth record for official seat metadata, filed candidates, election structure, and nomination status before any UI-specific derivation.

**Repository rule:** Whenever seat-election schema, nomination rules, canonical candidate status logic, or any other official filing data changes, rerun `python scripts/build_us_house_seat_index.py`. The script now also refreshes `apps/web/data/us-house-election-view.json`, and both generated JSON files should be committed together in the same change.

## Ballotpedia U.S. House text normalization
A separate parser now normalizes Ballotpedia text dumps into seat-keyed records under a Ballotpedia-specific namespace so the source can be merged later without replacing the canonical FEC/Census seat index.

Run:

```bash
python scripts/parse_ballotpedia_house_text.py
```

Expected input:

- `test_data/candidates/ballotpedia/output_house_text/*.txt`

Output:

- `apps/web/data/us-house-ballotpedia.json`

The output preserves Ballotpedia-specific notes, general-election candidate lines, primary sections grouped by party, advanced-from-primary text, and scrape-quality flags for downstream merge/testing.

**Canonical role:** `apps/web/data/us-house-ballotpedia.json` is the canonical Ballotpedia merge/debug dataset. It is intentionally source-shaped so reconciliation logic can inspect Ballotpedia notes, scrape flags, and unmatched candidate lines without overwriting the raw filings dataset.

**Repository rule:** Whenever Ballotpedia text parsing changes, rerun `python scripts/parse_ballotpedia_house_text.py`. That parser now also refreshes `apps/web/data/us-house-election-view.json`, so Ballotpedia/debug changes propagate into the district UI payload in the same update.

## Ballotpedia raw scrape ingestion (House + Senate)
Raw HTML acquisition is now package-backed and reusable under `scripts/ballotpedia_rollup`, with CLI wrappers for operations:

```bash
python scripts/scrape_ballotpedia_house_raw.py
python scripts/scrape_ballotpedia_senate_raw.py
```

Common options:

```bash
python scripts/scrape_ballotpedia_house_raw.py --outdir ballotpedia_house_raw --force-refresh --max-attempts 5 --timeout 30 --request-delay 0.8
python scripts/scrape_ballotpedia_senate_raw.py --outdir ballotpedia_senate_raw --force-refresh
```

Backward-compatible aliases are available:
- `python scripts/scrape_get_all.py`
- `python scripts/scrape_get_all_senate.py`

Output naming remains parser-compatible:
- House: `National.txt`, `XX.txt`, `XX-AL.txt`, `XX-<n>.txt`
- Senate: `National.txt`, `XX.txt`, `XX-SPECIAL.txt`


## District-level U.S. House market join (Kalshi + Seat-ID)
A dedicated builder now joins Kalshi US-REP contracts to canonical congressional districts by `seatId`, ticker patterns, and title/rules metadata.

Run:

```bash
python scripts/build_us_house_market_index.py
```

Output:

- `apps/web/data/us-house-market-index.json`

The congressional district map consumes this index so hovering over a district fills in the district-specific Kalshi contracts and their metadata.

## U.S. House district data flow
The intended flow among the House builders and the district map is:

1. `scripts/build_us_house_seat_index.py` builds `apps/web/data/us-house-seats.json`, the canonical raw-filings dataset used for official seat metadata, filed candidates, and election structure.
2. `scripts/build_us_house_election_view.py` reads `apps/web/data/us-house-seats.json` plus `apps/web/data/us-house-ballotpedia.json` and writes `apps/web/data/us-house-election-view.json`, the derived display dataset for district-level UI rendering.
3. `apps/web/congressional-map.js` loads both datasets, but treats `us-house-election-view.json` as canonical for presentation fields such as `displayCandidates` and `primaryElections`, while retaining `us-house-seats.json` for filing totals, contention metadata, and diagnostics.

### Canonical JSON roles
- **Raw filings:** `apps/web/data/us-house-seats.json`
- **Ballotpedia merge/debugging:** `apps/web/data/us-house-ballotpedia.json`
- **District UI rendering:** `apps/web/data/us-house-election-view.json`

### Review checklist
- If you change `scripts/build_us_house_election_view.py`, also review and usually update `apps/web/congressional-map.js` or this README so the UI contract stays in sync.
- Run `python scripts/check_us_house_election_view_sync.py` to flag election-view builder changes that are not paired with a UI/review update.

## Local congressional map GIS layers
The repository also includes a builder for local congressional district and state geometry used by `apps/web/congressional-map.html`.

Run:

```bash
python scripts/build_congressional_map_layers.py
```

Expected input:

- `test_data/maps/NTAD_Congressional_Districts_03182026/*.kmz`

Outputs:

- `apps/web/data/congressional-districts.geojson`
- `apps/web/data/us-states.geojson`

The district layer is built from the NTAD KMZ geometry and filtered to the contiguous U.S. The state layer is fetched from the official ArcGIS state boundary service and cached locally for the web app.

## PowerVote Cross-Office API
A new additive endpoint is available for unified seat/place context across offices:

- `GET /api/v1/powervote/all`

Accepted query params:
- Primary location: `seat_id` or `zipcode` or `address`
- Optional comparison: `compare_seat_id` or `compare_zipcode` or `compare_address`

Response includes grouped outputs per location:
- `resolvedContext` (`stateCode`, `houseSeatId`, `senateSeatIds[]`)
- `house` (single-office PowerVote payload)
- `senate[]` (one payload per Senate contest in state)
- flattened, deterministic `elections[]`

Existing endpoints remain unchanged:
- `GET /api/v1/powervote`
- `POST /api/v1/powervote/compare`

For repeatable election onboarding and bot handoff guidance, see:
- `docs/election-ingestion-playbook-senate-2026.md`
