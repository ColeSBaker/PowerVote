-- Snapshot storage metadata and mobile read views

CREATE TABLE IF NOT EXISTS pv.snapshot_artifacts (
  id BIGSERIAL PRIMARY KEY,
  batch_id BIGINT NOT NULL REFERENCES pv.ingest_batches(id) ON DELETE CASCADE,
  artifact_name TEXT NOT NULL,
  artifact_uri TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  schema_version TEXT NOT NULL,
  source_lineage JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (batch_id, artifact_name)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_artifacts_batch ON pv.snapshot_artifacts(batch_id);

CREATE TABLE IF NOT EXISTS pv.snapshot_validation_results (
  id BIGSERIAL PRIMARY KEY,
  batch_id BIGINT NOT NULL REFERENCES pv.ingest_batches(id) ON DELETE CASCADE,
  gate_name TEXT NOT NULL,
  status TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (batch_id, gate_name)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_validation_batch ON pv.snapshot_validation_results(batch_id);

CREATE OR REPLACE VIEW pv.v_mobile_seat_summary_current AS
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

CREATE OR REPLACE VIEW pv.v_mobile_powervote_current AS
SELECT
  d.seat_id,
  d.general_status,
  d.incumbent_party,
  d.dccc_target,
  d.nrcc_target,
  d.primary_count,
  d.runoff_count
FROM pv.v_district_details d;
