# PowerVote Next.js Frontend

Next.js + TypeScript application for the post-canonicalization product surface.

## Features in this implementation

- Map View with `office`, `election_view`, and `color_mode` controls.
- PowerVote View with U.S. Census address geocoding and weighted competitiveness scoring.
- API contracts exposed under:
  - `GET /api/v1/map/districts`
  - `GET /api/v1/districts/{seat_id}`
  - `GET /api/v1/powervote`
  - `POST /api/v1/powervote/compare`
- Rollup CSV files from `apps/web/data` are the canonical source for all responses.

## Run locally

```bash
cd apps/web-next
npm install
npm run dev
```

## Tests

```bash
cd apps/web-next
npm test
```

