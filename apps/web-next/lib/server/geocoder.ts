import { lookupGeocode, insertGeocode } from "./db";

// ---------------------------------------------------------------------------
// In-process geocode result cache (L1).
// Keyed by a normalized form of the raw address string. Persists for the
// lifetime of the Node.js server process (survives across requests in warm
// invocations; lost on cold starts). Capped at MAX_CACHE_SIZE to prevent
// unbounded growth in long-running processes.
//
// Cache hierarchy:
//   L1 — in-memory Map (sub-millisecond, process-scoped)
//   L2 — PostgreSQL `geocoded_addresses` table (< 5ms, survives cold starts)
//   L3 — US Census geocoding API (300–600ms, authoritative)
// ---------------------------------------------------------------------------
const MAX_CACHE_SIZE = 5_000;
const _geocodeCache = new Map<string, CensusGeocodeResult>();

function _cacheKey(address: string): string {
  return address.trim().toUpperCase().replace(/\s+/g, " ");
}

function _putCache(key: string, value: CensusGeocodeResult): void {
  if (_geocodeCache.size >= MAX_CACHE_SIZE) {
    // Evict the oldest entry (insertion-order iteration in Map).
    const firstKey = _geocodeCache.keys().next().value;
    if (firstKey !== undefined) _geocodeCache.delete(firstKey);
  }
  _geocodeCache.set(key, value);
}

// Exported for testing only.
export function _clearGeocodeCache(): void {
  _geocodeCache.clear();
}

const STATE_BY_FIPS: Record<string, string> = {
  "01": "AL",
  "02": "AK",
  "04": "AZ",
  "05": "AR",
  "06": "CA",
  "08": "CO",
  "09": "CT",
  "10": "DE",
  "11": "DC",
  "12": "FL",
  "13": "GA",
  "15": "HI",
  "16": "ID",
  "17": "IL",
  "18": "IN",
  "19": "IA",
  "20": "KS",
  "21": "KY",
  "22": "LA",
  "23": "ME",
  "24": "MD",
  "25": "MA",
  "26": "MI",
  "27": "MN",
  "28": "MS",
  "29": "MO",
  "30": "MT",
  "31": "NE",
  "32": "NV",
  "33": "NH",
  "34": "NJ",
  "35": "NM",
  "36": "NY",
  "37": "NC",
  "38": "ND",
  "39": "OH",
  "40": "OK",
  "41": "OR",
  "42": "PA",
  "44": "RI",
  "45": "SC",
  "46": "SD",
  "47": "TN",
  "48": "TX",
  "49": "UT",
  "50": "VT",
  "51": "VA",
  "53": "WA",
  "54": "WV",
  "55": "WI",
  "56": "WY",
};

export type CensusGeocodeResult = {
  normalizedAddress: string | null;
  latitude: number | null;
  longitude: number | null;
  seatId: string | null;
  stateCode: string | null;
};

type AddressMatch = {
  matchedAddress?: string;
  coordinates?: { x?: number; y?: number };
  geographies?: Record<string, Array<Record<string, string>>>;
};

function inferSeatIdFromGeographies(geographies: Record<string, Array<Record<string, string>>> | undefined): string | null {
  if (!geographies) return null;
  const entries = Object.entries(geographies);
  const congressional = entries.find(([key]) => /congressional district/i.test(key));
  const row = congressional?.[1]?.[0];
  if (!row) return null;
  const stateFips = String(row.STATE || row.STATEFP || "").padStart(2, "0");
  const districtRaw = String(row.CD118 || row.CD || row.CDFP || "").trim();
  const state = STATE_BY_FIPS[stateFips];
  if (!state || !districtRaw) return null;
  const district = Number(districtRaw) === 0 ? "AL" : String(Number(districtRaw)).padStart(2, "0");
  return `${state}-${district}`;
}

function inferStateCodeFromGeographies(geographies: Record<string, Array<Record<string, string>>> | undefined): string | null {
  if (!geographies) return null;
  for (const rows of Object.values(geographies)) {
    const row = rows?.[0];
    if (!row) continue;
    const stateFips = String(row.STATE || row.STATEFP || "").padStart(2, "0");
    const state = STATE_BY_FIPS[stateFips];
    if (state) return state;
  }
  return null;
}

export async function geocodeAddressWithCensus(address: string): Promise<CensusGeocodeResult> {
  const key = _cacheKey(address);

  // L1: in-memory cache
  const cached = _geocodeCache.get(key);
  if (cached !== undefined) return cached;

  // L2: persistent DB cache (survives cold starts)
  const dbRow = await lookupGeocode(key);
  if (dbRow !== null) {
    const result: CensusGeocodeResult = {
      normalizedAddress: dbRow.normalizedAddress,
      latitude: dbRow.latitude,
      longitude: dbRow.longitude,
      seatId: dbRow.seatId,
      stateCode: dbRow.stateCode,
    };
    _putCache(key, result);
    return result;
  }

  // L3: Census API
  const query = new URLSearchParams({
    address,
    benchmark: "Public_AR_Current",
    vintage: "Current_Current",
    format: "json",
  });
  const url = `https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress?${query.toString()}`;
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Census geocoder request failed (${response.status}).`);
  }

  const payload = (await response.json()) as {
    result?: { addressMatches?: AddressMatch[] };
  };

  const first = payload.result?.addressMatches?.[0];
  if (!first) {
    const miss: CensusGeocodeResult = { normalizedAddress: null, latitude: null, longitude: null, seatId: null, stateCode: null };
    _putCache(key, miss);
    return miss;
  }

  const longitude = Number(first.coordinates?.x);
  const latitude = Number(first.coordinates?.y);

  const result: CensusGeocodeResult = {
    normalizedAddress: first.matchedAddress ?? null,
    latitude: Number.isFinite(latitude) ? latitude : null,
    longitude: Number.isFinite(longitude) ? longitude : null,
    seatId: inferSeatIdFromGeographies(first.geographies),
    stateCode: inferStateCodeFromGeographies(first.geographies),
  };
  _putCache(key, result);

  // Persist to DB cache if we have coordinates (location column is NOT NULL).
  if (result.latitude !== null && result.longitude !== null) {
    void insertGeocode(key, {
      normalizedAddress: result.normalizedAddress,
      latitude: result.latitude,
      longitude: result.longitude,
      seatId: result.seatId,
      stateCode: result.stateCode,
    });
  }

  return result;
}
