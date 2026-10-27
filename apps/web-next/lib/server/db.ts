/**
 * PostgreSQL client for the PowerVote Next.js API.
 *
 * Usage is opt-in: if DATABASE_URL is not set the module exports no-op helpers
 * so data-source.ts can fall back to CSV loading transparently.
 *
 * All query functions return the row payload objects (plain JS objects matching
 * the CSV row shape stored in the JSONB `payload` column), so data-source.ts
 * can parse them with the same Zod schemas it uses for CSV rows.
 */

import postgres from "postgres";
import type { Office } from "@/lib/domain/schemas";

type SqlClient = ReturnType<typeof postgres>;
let _sql: SqlClient | null | undefined; // undefined = not yet initialised, null = DB disabled

function getSql(): SqlClient | null {
  if (_sql !== undefined) return _sql;
  const url = process.env.DATABASE_URL;
  if (!url) {
    _sql = null;
    return null;
  }
  try {
    _sql = postgres(url, {
      max: 5,
      idle_timeout: 30,
      connect_timeout: 5,
    });
  } catch {
    _sql = null;
  }
  return _sql;
}

export type ActiveBatch = {
  batchId: number;
  snapshotDate: string;
};

/**
 * Returns the currently promoted batch, or null if the DB is unavailable or no
 * batch has been promoted yet.
 */
export async function getActiveBatch(): Promise<ActiveBatch | null> {
  const sql = getSql();
  if (!sql) return null;
  try {
    const rows = await sql<{ batch_id: number; snapshot_date: string }[]>`
      SELECT a.batch_id, b.snapshot_date::text AS snapshot_date
      FROM pv.active_batch a
      JOIN pv.ingest_batches b ON b.id = a.batch_id
      WHERE a.batch_id IS NOT NULL
      LIMIT 1
    `;
    if (!rows.length) return null;
    return { batchId: Number(rows[0].batch_id), snapshotDate: rows[0].snapshot_date };
  } catch {
    return null;
  }
}

/**
 * Load all general-rollup payload rows for the given office from the current active batch.
 * Returns raw JSON objects matching the CSV row shape (same fields as the CSV).
 */
export async function loadGeneralPayloads(office: Office): Promise<Record<string, string>[]> {
  const sql = getSql();
  if (!sql) return [];
  try {
    const rows = await sql<{ payload: Record<string, string> }[]>`
      SELECT payload FROM pv.v_general_rollup_current WHERE office = ${office}
    `;
    return rows.map((r) => r.payload);
  } catch {
    return [];
  }
}

/**
 * Load all primary-rollup payload rows for the given office.
 */
export async function loadPrimaryPayloads(office: Office): Promise<Record<string, string>[]> {
  const sql = getSql();
  if (!sql) return [];
  try {
    const rows = await sql<{ payload: Record<string, string> }[]>`
      SELECT payload FROM pv.v_primary_rollup_current WHERE office = ${office}
    `;
    return rows.map((r) => r.payload);
  } catch {
    return [];
  }
}

/**
 * Load all runoff-rollup payload rows for the given office.
 */
export async function loadRunoffPayloads(office: Office): Promise<Record<string, string>[]> {
  const sql = getSql();
  if (!sql) return [];
  try {
    const rows = await sql<{ payload: Record<string, string> }[]>`
      SELECT payload FROM pv.v_runoff_rollup_current WHERE office = ${office}
    `;
    return rows.map((r) => r.payload);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Geocoding cache — backed by the `geocoded_addresses` table (public schema).
// ---------------------------------------------------------------------------

export type GeocodeRow = {
  normalizedAddress: string | null;
  latitude: number | null;
  longitude: number | null;
  seatId: string | null;
  stateCode: string | null;
};

/**
 * Look up a previously geocoded address. Returns null on cache miss or DB
 * unavailability — callers should fall through to the Census API in that case.
 */
export async function lookupGeocode(rawAddress: string): Promise<GeocodeRow | null> {
  const sql = getSql();
  if (!sql) return null;
  try {
    const rows = await sql<
      { normalized_address: string | null; lat: string | null; lng: string | null; seat_id: string | null; state_code: string | null }[]
    >`
      SELECT
        normalized_address,
        ST_Y(location::geometry)::text AS lat,
        ST_X(location::geometry)::text AS lng,
        seat_id,
        state_code
      FROM geocoded_addresses
      WHERE lower(raw_address) = lower(${rawAddress})
      LIMIT 1
    `;
    if (!rows.length) return null;
    const r = rows[0];
    return {
      normalizedAddress: r.normalized_address,
      latitude: r.lat !== null ? Number(r.lat) : null,
      longitude: r.lng !== null ? Number(r.lng) : null,
      seatId: r.seat_id,
      stateCode: r.state_code,
    };
  } catch {
    return null;
  }
}

/**
 * Persist a geocoded result. Only called when latitude and longitude are known
 * (the `location` column is NOT NULL). Fire-and-forget — never throws.
 */
export async function insertGeocode(
  rawAddress: string,
  result: { normalizedAddress: string | null; latitude: number; longitude: number; seatId: string | null; stateCode: string | null },
): Promise<void> {
  const sql = getSql();
  if (!sql) return;
  try {
    await sql`
      INSERT INTO geocoded_addresses (raw_address, normalized_address, location, seat_id, state_code, provider)
      SELECT
        ${rawAddress},
        ${result.normalizedAddress},
        ST_SetSRID(ST_MakePoint(${result.longitude}, ${result.latitude}), 4326),
        ${result.seatId},
        ${result.stateCode},
        'census'
      WHERE NOT EXISTS (
        SELECT 1 FROM geocoded_addresses WHERE lower(raw_address) = lower(${rawAddress})
      )
    `;
  } catch {
    // Fire-and-forget — never block a geocode response on a DB write failure.
  }
}

/** Close the connection pool (useful in tests or graceful shutdown). */
export async function closeDb(): Promise<void> {
  if (_sql) {
    await _sql.end();
    _sql = undefined;
  }
}

/** Reset the singleton (for testing). */
export function resetDbForTesting(): void {
  _sql = undefined;
}
