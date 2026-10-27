# PowerVote

**Where does your vote matter most?** PowerVote combines prediction-market odds, historical results, and party targeting data to show how competitive every 2026 U.S. race on your ballot is.

It covers **U.S. House, U.S. Senate, Governor, Lieutenant Governor, and Attorney General** races in all 50 states.

- **Map View** (`/map`): an interactive map of districts and states, colored by competitiveness, incumbency, market favorite, or primary status.
- **PowerVote View** (`/powervote`): enter an address or ZIP code and see every race on your ballot, ranked by how close it is, with candidates and live market odds. You can compare up to three locations side by side.

## How it works

```
Ballotpedia ──scrape──▶ parse ──▶ FEC candidate matching ──▶ Kalshi market join ──▶ rollups
                                                                                     │
                       apps/web/data/*.csv|json (snapshots) ◀────────────────────────┘
                                   │            └──▶ Postgres (optional)
                                   ▼
                       Next.js API (/api/v1/*) ──▶ Map View / PowerVote View
```

1. **Python pipeline** (`scripts/`) scrapes Ballotpedia race pages, parses candidates and primaries, links candidates to FEC IDs, and maps Kalshi election markets to seats. It writes CSV/JSON snapshots to `apps/web/data/`.
2. **Scoring** (`apps/web-next/lib/scoring/`) blends four signals into a competitiveness band from `safe_dem` to `safe_rep`: market odds, a polling proxy from historical vote totals, DCCC/NRCC/DSCC/NRSC targeting, and incumbency.
3. **Next.js app** (`apps/web-next/`) serves the API and UI. It reads the snapshots directly, or Postgres if `DATABASE_URL` is set. It geocodes addresses with the free U.S. Census geocoder.

See [`docs/architecture.md`](docs/architecture.md) and [`docs/pipeline-reference.md`](docs/pipeline-reference.md) for detail.

## Quick start

The repo ships with data snapshots, so the web app runs without running the pipeline.

```bash
cd apps/web-next
npm install
npm run dev        # http://localhost:3000
```

Requires Node 22 (the version CI uses).

### Optional environment variables

| Variable | Purpose |
|---|---|
| `MAPBOX_ACCESS_TOKEN` | Enables address autocomplete (`/api/v1/address-suggest`). Lookups work without it. |
| `DATABASE_URL` | Read rollups from Postgres instead of CSV snapshots. |
| `DATA_DIR` | Override the snapshot directory (defaults to `apps/web/data/`). |
| `POWERVOTE_CDN_BASE_URL` | Redirect static map payloads to a CDN. |

## Running the data pipeline

Requires Python 3.13+.

```bash
pip install -r requirements.txt
python scripts/pipeline/run_daily_refresh.py --skip-db-load
```

This fetches fresh Kalshi markets, re-scrapes Ballotpedia, rebuilds every office's rollups, and runs the tests. Useful flags: `--skip-kalshi-fetch`, `--skip-frontend-tests`, `--force-refresh`. To run individual offices step by step, see [`CLAUDE.md`](CLAUDE.md#python-data-pipeline).

### Local Postgres (optional)

```bash
cp .env.storage.example .env.storage   # then replace the CHANGE_ME values
docker compose -f docker-compose.storage.yml --env-file .env.storage up -d
python scripts/pipeline/load_rollups_to_postgres.py
```

## Tests

```bash
# Python pipeline
python -m pytest tests -m "not slow_integrity" -q   # fast lane
python -m pytest tests -m "slow_integrity" -q       # data-integrity lane

# Web app
cd apps/web-next
npm test           # Vitest unit + integration
npm run test:e2e   # Playwright
npm run lint
```

Some Python parser and integrity tests read raw Ballotpedia page captures and Kalshi API snapshots from `test_data/candidates/ballotpedia/`, `test_data/kalshi/` and `test_data/kalshi_json_data/`. That third-party data is not distributed with the repo, so those tests are skipped on a fresh clone. To run them, populate the directories with the scrape and fetch scripts.

## Repository layout

| Path | Contents |
|---|---|
| `apps/web-next/` | Next.js app: UI, `/api/v1` routes, scoring, data loading |
| `apps/web/data/` | Pipeline output snapshots consumed by the app |
| `apps/web/` | Original static HTML/JS prototype |
| `scripts/` | Python pipeline: scrapers, parsers, FEC/Kalshi linkage, builders |
| `scripts/ballotpedia_rollup/` | Core parsing, FEC matching, and Kalshi mapping package |
| `db/` | Postgres/PostGIS schema and migrations |
| `api/openapi.yaml` | API contract |
| `tests/` | Python tests |
| `test_data/` | Fixtures: frozen rollup snapshots, FEC candidate summary, district geometry |
| `docs/` | Architecture notes, playbooks, design docs |

## Data sources

- **[Ballotpedia](https://ballotpedia.org)**: candidate lists, primaries, and historical results.
- **[Kalshi](https://kalshi.com)**: election market prices, from its public API.
- **[FEC](https://www.fec.gov)**: candidate IDs.
- **[U.S. Census Bureau](https://www.census.gov)**: geocoding and state boundaries.
- **[NTAD](https://geodata.bts.gov)** (U.S. DOT): congressional district geometry.

Data from these sources remains subject to each provider's terms. PowerVote is not affiliated with any of them, and market odds are not predictions or endorsements.

## License

Code is released under the [MIT License](LICENSE).
