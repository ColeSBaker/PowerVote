-- PowerVote canonical schema (PostgreSQL + PostGIS)

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enumerations
CREATE TYPE area_level AS ENUM ('country', 'state', 'congressional_district', 'state_leg_upper', 'state_leg_lower', 'county', 'precinct');
CREATE TYPE election_level AS ENUM ('federal', 'state', 'county', 'municipal', 'special');
CREATE TYPE election_kind AS ENUM ('primary', 'general', 'runoff', 'special', 'referendum');
CREATE TYPE office_level AS ENUM ('federal', 'state', 'county', 'municipal');

-- Geography
CREATE TABLE IF NOT EXISTS areas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  level area_level NOT NULL,
  country_code TEXT NOT NULL DEFAULT 'US',
  state_fips TEXT,
  county_fips TEXT,
  district_code TEXT,
  name TEXT NOT NULL,
  cycle_year INTEGER,
  geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
  centroid GEOMETRY(POINT, 4326),
  effective_from DATE,
  effective_to DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_areas_level ON areas(level);
CREATE INDEX IF NOT EXISTS idx_areas_cycle_year ON areas(cycle_year);
CREATE INDEX IF NOT EXISTS idx_areas_geom_gist ON areas USING GIST (geom);

-- Elections
CREATE TABLE IF NOT EXISTS elections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  level election_level NOT NULL,
  kind election_kind NOT NULL,
  name TEXT NOT NULL,
  election_date DATE NOT NULL,
  area_id UUID REFERENCES areas(id),
  source_url TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_elections_date ON elections(election_date);
CREATE INDEX IF NOT EXISTS idx_elections_area_id ON elections(area_id);

CREATE TABLE IF NOT EXISTS offices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  office_level office_level NOT NULL,
  name TEXT NOT NULL,
  seat_count INTEGER NOT NULL DEFAULT 1,
  area_id UUID REFERENCES areas(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS election_offices (
  election_id UUID NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
  office_id UUID NOT NULL REFERENCES offices(id) ON DELETE CASCADE,
  PRIMARY KEY (election_id, office_id)
);

CREATE TABLE IF NOT EXISTS candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name TEXT NOT NULL,
  party TEXT,
  incumbent BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS election_candidates (
  election_id UUID NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
  office_id UUID NOT NULL REFERENCES offices(id) ON DELETE CASCADE,
  candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  ballot_position INTEGER,
  PRIMARY KEY (election_id, office_id, candidate_id)
);

-- Address geocoding cache
CREATE TABLE IF NOT EXISTS geocoded_addresses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_address TEXT NOT NULL,
  normalized_address TEXT,
  location GEOMETRY(POINT, 4326) NOT NULL,
  -- Derived seat and state — stored so lookup can skip the spatial join.
  seat_id TEXT,
  state_code TEXT,
  provider TEXT NOT NULL,
  provider_place_id TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast address lookup (case-insensitive comparison uses lower() index).
CREATE INDEX IF NOT EXISTS idx_geocoded_addresses_raw_address ON geocoded_addresses (lower(raw_address));
CREATE INDEX IF NOT EXISTS idx_geocoded_addresses_location_gist ON geocoded_addresses USING GIST (location);

-- Source registry + mapping
CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  base_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  source_entity_id TEXT NOT NULL,
  canonical_entity_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (source_id, entity_type, source_entity_id)
);

-- Poll snapshots
CREATE TABLE IF NOT EXISTS poll_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id),
  election_id UUID NOT NULL REFERENCES elections(id),
  office_id UUID REFERENCES offices(id),
  area_id UUID REFERENCES areas(id),
  pollster TEXT,
  start_date DATE,
  end_date DATE,
  sample_size INTEGER,
  population TEXT,
  methodology TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at TIMESTAMPTZ,
  confidence NUMERIC(5,2),
  raw_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_poll_snapshots_election_id ON poll_snapshots(election_id);
CREATE INDEX IF NOT EXISTS idx_poll_snapshots_fetched_at ON poll_snapshots(fetched_at DESC);

CREATE TABLE IF NOT EXISTS poll_candidate_results (
  poll_snapshot_id UUID NOT NULL REFERENCES poll_snapshots(id) ON DELETE CASCADE,
  candidate_id UUID NOT NULL REFERENCES candidates(id),
  percentage NUMERIC(6,3) NOT NULL,
  PRIMARY KEY (poll_snapshot_id, candidate_id)
);

-- Market snapshots
CREATE TABLE IF NOT EXISTS market_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id),
  election_id UUID NOT NULL REFERENCES elections(id),
  office_id UUID REFERENCES offices(id),
  area_id UUID REFERENCES areas(id),
  contract_code TEXT,
  contract_name TEXT,
  implied_probability NUMERIC(6,3),
  price NUMERIC(10,4),
  volume NUMERIC(18,2),
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  confidence NUMERIC(5,2),
  raw_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_election_id ON market_snapshots(election_id);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_fetched_at ON market_snapshots(fetched_at DESC);

CREATE TABLE IF NOT EXISTS market_candidate_results (
  market_snapshot_id UUID NOT NULL REFERENCES market_snapshots(id) ON DELETE CASCADE,
  candidate_id UUID NOT NULL REFERENCES candidates(id),
  implied_probability NUMERIC(6,3) NOT NULL,
  PRIMARY KEY (market_snapshot_id, candidate_id)
);

-- Common lookup helper: all containing areas for a point
CREATE OR REPLACE VIEW point_area_lookup AS
SELECT
  a.id AS area_id,
  a.level,
  a.name,
  a.cycle_year,
  a.effective_from,
  a.effective_to
FROM areas a;
