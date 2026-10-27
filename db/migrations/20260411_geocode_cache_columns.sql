-- Migration: add seat_id / state_code columns and raw_address index to geocoded_addresses.
-- These columns let the Next.js API return cached seat+state results without an extra
-- spatial join, and the index enables fast exact-match lookups by raw address string.

ALTER TABLE geocoded_addresses
  ADD COLUMN IF NOT EXISTS seat_id TEXT,
  ADD COLUMN IF NOT EXISTS state_code TEXT;

CREATE INDEX IF NOT EXISTS idx_geocoded_addresses_raw_address
  ON geocoded_addresses (lower(raw_address));
