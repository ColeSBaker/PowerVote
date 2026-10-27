-- PowerVote rollup-to-db pipeline schema
-- Canonical inputs:
-- - ballotpedia-general-election-rollup.csv
-- - ballotpedia-primary-election-rollup.csv
-- - ballotpedia-runoff-election-rollup.csv
-- - kalshi-us-rep-contest-index.csv
-- - kalshi-rollup-join-audit.csv

CREATE SCHEMA IF NOT EXISTS pv;

CREATE TABLE IF NOT EXISTS pv.ingest_batches (
  id BIGSERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status TEXT NOT NULL DEFAULT 'staged',
  source_lineage JSONB NOT NULL DEFAULT '[]'::jsonb,
  UNIQUE (snapshot_date, generated_at)
);

CREATE TABLE IF NOT EXISTS pv.active_batch (
  singleton_id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (singleton_id = 1),
  batch_id BIGINT REFERENCES pv.ingest_batches(id)
);

INSERT INTO pv.active_batch (singleton_id, batch_id)
VALUES (1, NULL)
ON CONFLICT (singleton_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS pv.stg_general_rollup (
  batch_id BIGINT NOT NULL REFERENCES pv.ingest_batches(id) ON DELETE CASCADE,
  seat_id TEXT NOT NULL,
  state_code TEXT NOT NULL,
  general_status TEXT,
  incumbent_party TEXT,
  dccc_target BOOLEAN,
  nrcc_target BOOLEAN,
  primary_status_d TEXT,
  primary_status_r TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (batch_id, seat_id)
);

CREATE TABLE IF NOT EXISTS pv.stg_primary_rollup (
  batch_id BIGINT NOT NULL REFERENCES pv.ingest_batches(id) ON DELETE CASCADE,
  primary_id TEXT NOT NULL,
  seat_id TEXT NOT NULL,
  party TEXT,
  status TEXT,
  round TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (batch_id, primary_id)
);

CREATE TABLE IF NOT EXISTS pv.stg_runoff_rollup (
  batch_id BIGINT NOT NULL REFERENCES pv.ingest_batches(id) ON DELETE CASCADE,
  primary_id TEXT NOT NULL,
  seat_id TEXT NOT NULL,
  party TEXT,
  status TEXT,
  runoff_id TEXT,
  payload JSONB NOT NULL,
  PRIMARY KEY (batch_id, primary_id)
);

CREATE TABLE IF NOT EXISTS pv.stg_kalshi_contest_index (
  batch_id BIGINT NOT NULL REFERENCES pv.ingest_batches(id) ON DELETE CASCADE,
  contest_id TEXT NOT NULL,
  seat_id TEXT,
  round TEXT,
  party_lane TEXT,
  market_count INTEGER,
  payload JSONB NOT NULL,
  PRIMARY KEY (batch_id, contest_id)
);

CREATE TABLE IF NOT EXISTS pv.stg_kalshi_join_audit (
  batch_id BIGINT NOT NULL REFERENCES pv.ingest_batches(id) ON DELETE CASCADE,
  audit_id TEXT NOT NULL,
  seat_id TEXT,
  row_type TEXT,
  sum_status TEXT,
  odds_map_sum NUMERIC,
  payload JSONB NOT NULL,
  PRIMARY KEY (batch_id, audit_id)
);

CREATE OR REPLACE VIEW pv.v_general_rollup_current AS
SELECT s.*
FROM pv.stg_general_rollup s
JOIN pv.active_batch a ON a.batch_id = s.batch_id;

CREATE OR REPLACE VIEW pv.v_primary_rollup_current AS
SELECT s.*
FROM pv.stg_primary_rollup s
JOIN pv.active_batch a ON a.batch_id = s.batch_id;

CREATE OR REPLACE VIEW pv.v_runoff_rollup_current AS
SELECT s.*
FROM pv.stg_runoff_rollup s
JOIN pv.active_batch a ON a.batch_id = s.batch_id;

CREATE OR REPLACE VIEW pv.v_kalshi_contest_index_current AS
SELECT s.*
FROM pv.stg_kalshi_contest_index s
JOIN pv.active_batch a ON a.batch_id = s.batch_id;

CREATE OR REPLACE VIEW pv.v_kalshi_join_audit_current AS
SELECT s.*
FROM pv.stg_kalshi_join_audit s
JOIN pv.active_batch a ON a.batch_id = s.batch_id;

-- Derived map metrics model
CREATE OR REPLACE VIEW pv.v_map_district_metrics AS
SELECT
  g.seat_id,
  g.state_code,
  g.general_status,
  g.incumbent_party,
  g.dccc_target,
  g.nrcc_target,
  g.primary_status_d,
  g.primary_status_r
FROM pv.v_general_rollup_current g;

-- Derived district detail model
CREATE OR REPLACE VIEW pv.v_district_details AS
SELECT
  g.seat_id,
  g.general_status,
  g.incumbent_party,
  g.dccc_target,
  g.nrcc_target,
  COALESCE(p.primary_count, 0) AS primary_count,
  COALESCE(r.runoff_count, 0) AS runoff_count
FROM pv.v_general_rollup_current g
LEFT JOIN (
  SELECT seat_id, COUNT(*) AS primary_count
  FROM pv.v_primary_rollup_current
  GROUP BY seat_id
) p ON p.seat_id = g.seat_id
LEFT JOIN (
  SELECT seat_id, COUNT(*) AS runoff_count
  FROM pv.v_runoff_rollup_current
  GROUP BY seat_id
) r ON r.seat_id = g.seat_id;

-- Derived address-resolution model anchor (seat-based today, point-resolution in API)
CREATE OR REPLACE VIEW pv.v_powervote_elections AS
SELECT
  d.seat_id,
  d.general_status,
  d.incumbent_party,
  d.dccc_target,
  d.nrcc_target,
  d.primary_count,
  d.runoff_count
FROM pv.v_district_details d;

