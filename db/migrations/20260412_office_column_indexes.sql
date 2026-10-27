-- P0#1: Add office column to staging tables + seat_id indexes
-- Enables per-office queries from Next.js API and eliminates O(n) linear scans
-- on the district-detail hot path (was doing 4 separate full-table scans per request).

ALTER TABLE pv.stg_general_rollup      ADD COLUMN IF NOT EXISTS office TEXT;
ALTER TABLE pv.stg_primary_rollup      ADD COLUMN IF NOT EXISTS office TEXT;
ALTER TABLE pv.stg_runoff_rollup       ADD COLUMN IF NOT EXISTS office TEXT;
ALTER TABLE pv.stg_kalshi_contest_index ADD COLUMN IF NOT EXISTS office TEXT;
ALTER TABLE pv.stg_kalshi_join_audit   ADD COLUMN IF NOT EXISTS office TEXT;

-- seat_id indexes — primary hot path for district-detail endpoint
CREATE INDEX IF NOT EXISTS idx_stg_general_seat  ON pv.stg_general_rollup  (seat_id);
CREATE INDEX IF NOT EXISTS idx_stg_primary_seat  ON pv.stg_primary_rollup  (seat_id);
CREATE INDEX IF NOT EXISTS idx_stg_runoff_seat   ON pv.stg_runoff_rollup   (seat_id);

-- (batch_id, office) composite indexes for per-office full-load queries
CREATE INDEX IF NOT EXISTS idx_stg_general_batch_office   ON pv.stg_general_rollup      (batch_id, office);
CREATE INDEX IF NOT EXISTS idx_stg_primary_batch_office   ON pv.stg_primary_rollup      (batch_id, office);
CREATE INDEX IF NOT EXISTS idx_stg_runoff_batch_office    ON pv.stg_runoff_rollup        (batch_id, office);
CREATE INDEX IF NOT EXISTS idx_stg_kalshi_idx_batch_office ON pv.stg_kalshi_contest_index (batch_id, office);
CREATE INDEX IF NOT EXISTS idx_stg_kalshi_aud_batch_office ON pv.stg_kalshi_join_audit    (batch_id, office);
