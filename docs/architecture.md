# PowerVote Architecture Blueprint

## Goals
- Provide election discovery by geography (state, congressional district, state legislative district, county).
- Resolve an entered address into all relevant election jurisdictions.
- Expose up-to-date polling and election market signals via API.
- Support web first, with an easy path to mobile.

## Recommended Technology Stack
- **Web app**: Next.js + TypeScript + Mapbox GL JS.
- **Mobile app**: React Native + TypeScript (shared domain models where possible).
- **API**: NestJS (Node.js + TypeScript).
- **Data ingestion**: Python workers (source connectors, normalization, dedupe).
- **Database**: PostgreSQL + PostGIS.
- **Caching**: Redis (phase 2).
- **Infrastructure**: Docker, GitHub Actions, managed PostgreSQL.

## System Components

### 1) Client Layer
- **Map views** for US/state/county/representative district boundaries.
- **Address entry flow** to geocode and fetch all matching areas.
- **Election detail views** that combine election metadata + polling + markets.

### 2) API Layer
- Read APIs optimized for map drill-down and address lookup.
- Stable response contracts regardless of ingestion source changes.
- Source attribution and freshness timestamps in each response.

### 3) Data Layer
- Canonical election and geography model in PostgreSQL/PostGIS.
- Boundary geometries stored as PostGIS polygons/multipolygons.
- Materialized views for common map and address lookup queries.

### 4) Ingestion Layer
- Provider-specific adapters (polling, prediction markets, official election feeds).
- Normalization pipeline to map source IDs -> canonical IDs.
- Data quality checks: schema checks, freshness checks, duplicate/conflict detection.

## Architecture Principles
1. **Canonical IDs everywhere**: geography, elections, offices, candidates.
2. **Versioned geographies**: support redistricting cycle changes.
3. **Provenance-first data**: keep source, fetched_at, and confidence metadata.
4. **Thin vertical slices**: ship by geography + endpoint slices, not by platform silos.
5. **Schema-driven development**: OpenAPI contract and generated clients.

## Implementation Milestones

### Milestone 1: MVP Vertical Slice
- Load one state's boundary layers and election records.
- Build address lookup API and map click drill-down API.
- Render map + election list in web app.

### Milestone 2: Market/Polling Data
- Integrate one polling source and one market source.
- Normalize records into canonical tables.
- Display source and last-updated metadata in UI.

### Milestone 3: National Expansion
- Expand boundary + election coverage nationally.
- Add caching and materialized views for performance.
- Add observability, alerting, and ingestion reliability dashboards.
