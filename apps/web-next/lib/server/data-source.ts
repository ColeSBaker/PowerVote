import { readFile, stat } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import { assertRequiredColumns, normalizeSeatId, parseCsvText } from "@/lib/server/csv";
import { getActiveBatch, loadGeneralPayloads, loadPrimaryPayloads, loadRunoffPayloads } from "@/lib/server/db";
import { resolveDataDirectory } from "@/lib/server/paths";
import type { Office } from "@/lib/domain/schemas";

const GENERAL_COLUMNS = [
  "seat",
  "district",
  "general_status",
  "incumbent_party",
  "kalshi_general_odds_map",
  "general_election_race_ratings",
  "dccc_target",
  "nrcc_target",
  "primary_status_d",
  "primary_status_r",
] as const;

const PRIMARY_COLUMNS = ["seat", "party", "primary_id", "status", "round"] as const;
const RUNOFF_COLUMNS = ["seat", "party", "primary_id", "status", "runoff_id"] as const;
const DEPARTURES_COLUMNS = ["seat", "departure_reason", "departure_subreason", "name", "party"] as const;
const CANDIDATE_COLUMNS = [
  "BallotpediaName",
  "2026 Seat",
  "Party",
  "Status",
  "Primary ID",
  "RunoffID",
  "Finance (Receipts)",
  "Finance (Cash in hand)",
  "KalshiBestPrimaryOdds",
  "KalshiBestGeneralOdds",
  "KalshiPrimaryMarkets",
] as const;

const generalRowSchema = z.object({
  seat: z.string().min(1),
  district: z.string().default(""),
  general_status: z.string().default("unknown"),
  incumbent_party: z.string().default(""),
  kalshi_general_odds_map: z.string().default(""),
  general_election_race_ratings: z.string().default(""),
  dccc_target: z.string().default("False"),
  nrcc_target: z.string().default("False"),
  dscc_target: z.string().optional().default("False"),
  nrsc_target: z.string().optional().default("False"),
  primary_status_d: z.string().default("none"),
  primary_status_r: z.string().default("none"),
  primary_status_np: z.string().optional().default("none"),
  incumbent_name: z.string().default(""),
  incumbent_status: z.string().default(""),
  primary_date: z.string().default(""),
  runoff_date: z.string().default(""),
  nominee_d: z.string().optional().default(""),
  nominee_r: z.string().optional().default(""),
  nominee_green: z.string().optional().default(""),
  nominee_libertarian: z.string().optional().default(""),
  kalshi_primary_d: z.string().optional().default(""),
  kalshi_primary_r: z.string().optional().default(""),
  kalshi_integrity_passed: z.string().optional().default("True"),
  kalshi_integrity_issue_missing_sum_status: z.string().optional().default("False"),
  kalshi_integrity_issue_sum_status_mismatch: z.string().optional().default("False"),
  kalshi_integrity_issue_odds_map_sum_out_of_band: z.string().optional().default("False"),
  kalshi_integrity_issue_missing_odds_map_with_markets: z.string().optional().default("False"),
  general_contention: z.string().default("no_election"),
  primary_contention: z.string().default("no_election"),
  source_url: z.string().optional().default(""),
});

const primaryRowSchema = z.object({
  seat: z.string().min(1),
  party: z.string().default(""),
  primary_id: z.string().default(""),
  status: z.string().default(""),
  round: z.string().default(""),
  primary_date: z.string().optional().default(""),
  runoff_date: z.string().optional().default(""),
  runoff_candidate_1: z.string().optional().default(""),
  runoff_candidate_2: z.string().optional().default(""),
  kalshi_primary_odds_map: z.string().optional().default(""),
  kalshi_integrity_passed: z.string().optional().default("True"),
  kalshi_integrity_issue_missing_sum_status: z.string().optional().default("False"),
  kalshi_integrity_issue_sum_status_mismatch: z.string().optional().default("False"),
  kalshi_integrity_issue_odds_map_sum_out_of_band: z.string().optional().default("False"),
  kalshi_integrity_issue_missing_odds_map_with_markets: z.string().optional().default("False"),
  advance_count: z.coerce.number().int().min(1).default(1),
  primary_type: z.string().optional().default("partisan_binary"),
});

const runoffRowSchema = z.object({
  seat: z.string().min(1),
  party: z.string().default(""),
  primary_id: z.string().default(""),
  status: z.string().default(""),
  runoff_id: z.string().default(""),
  runoff_candidate_1: z.string().optional().default(""),
  runoff_candidate_2: z.string().optional().default(""),
  runoff_date: z.string().optional().default(""),
});

const departureRowSchema = z.object({
  seat: z.string().min(1),
  departure_reason: z.string().default(""),
  departure_subreason: z.string().default(""),
  name: z.string().default(""),
  party: z.string().default(""),
});

const candidateRowSchema = z.object({
  BallotpediaName: z.string().default(""),
  "2026 Seat": z.string().min(1),
  Party: z.string().default(""),
  Status: z.string().default(""),
  "Primary ID": z.string().default(""),
  RunoffID: z.string().default(""),
  "Finance (Receipts)": z.string().default(""),
  "Finance (Cash in hand)": z.string().default(""),
  KalshiBestPrimaryOdds: z.string().default(""),
  KalshiBestGeneralOdds: z.string().default(""),
  KalshiPrimaryMarkets: z.string().default(""),
});

export type GeneralRow = z.infer<typeof generalRowSchema>;
export type PrimaryRow = z.infer<typeof primaryRowSchema>;
export type RunoffRow = z.infer<typeof runoffRowSchema>;
export type DepartureRow = z.infer<typeof departureRowSchema>;
export type CandidateRow = z.infer<typeof candidateRowSchema>;

export type CanonicalDataBundle = {
  office: Office;
  mapMode: "district" | "statewide";
  snapshotDate: string;
  updatedAt: string;
  sourceAttribution: string[];
  generalRows: GeneralRow[];
  primaryRows: PrimaryRow[];
  runoffRows: RunoffRow[];
  departureRows: DepartureRow[];
  candidateRows: CandidateRow[];
  geometryGeoJson: Record<string, unknown>;
};

type LoadProfile = {
  includeDepartures: boolean;
  includeCandidates: boolean;
};

const DEFAULT_LOAD_PROFILE: LoadProfile = {
  includeDepartures: true,
  includeCandidates: true,
};

const MAP_LOAD_PROFILE: LoadProfile = {
  includeDepartures: false,
  includeCandidates: true,
};

// Column projections for MAP_LOAD_PROFILE — only fields accessed by buildMapDistrictsResponse.
// IMPORTANT: update these sets whenever new generalRow/primaryRow fields are read in buildMapDistrictsResponse.
const MAP_GENERAL_KEEP = new Set([
  "seat", "district", "general_status", "incumbent_party",
  "kalshi_general_odds_map", "general_election_race_ratings",
  "dccc_target", "nrcc_target", "dscc_target", "nrsc_target",
  "primary_status_d", "primary_status_r", "primary_status_np",
  "nominee_d", "nominee_r", "nominee_green", "nominee_libertarian",
  "kalshi_primary_d", "kalshi_primary_r", "kalshi_integrity_passed",
  "incumbent_name", "incumbent_status",
  "general_contention", "primary_contention",
]);

const MAP_PRIMARY_KEEP = new Set([
  "seat", "party", "primary_id", "status", "round",
  "primary_date", "runoff_date", "runoff_candidate_1", "runoff_candidate_2",
  "kalshi_primary_odds_map", "kalshi_integrity_passed",
  "advance_count", "primary_type",
]);

const FILES_BY_OFFICE: Record<
  Office,
  {
    general: string;
    primary: string;
    runoff: string;
    departures: string;
    contestIndex: string;
    joinAudit: string;
    candidateRollup: string;
    snapshotDate: string;
    geometryGeoJson: string;
    mapMode: "district" | "statewide";
  }
> = {
  us_house: {
    general: "ballotpedia-general-election-rollup.csv",
    primary: "ballotpedia-primary-election-rollup.csv",
    runoff: "ballotpedia-runoff-election-rollup.csv",
    departures: "ballotpedia-incumbent-departures.csv",
    contestIndex: "kalshi-us-rep-contest-index.csv",
    joinAudit: "kalshi-rollup-join-audit.csv",
    candidateRollup: "candidate-rollup-2026.csv",
    snapshotDate: "rollup-snapshot-date.txt",
    geometryGeoJson: "congressional-districts.geojson",
    mapMode: "district",
  },
  us_senate: {
    general: "ballotpedia-senate-general-election-rollup.csv",
    primary: "ballotpedia-senate-primary-election-rollup.csv",
    runoff: "ballotpedia-senate-runoff-election-rollup.csv",
    departures: "ballotpedia-senate-incumbent-departures.csv",
    contestIndex: "kalshi-us-senate-contest-index.csv",
    joinAudit: "kalshi-us-senate-contest-integrity-violations.csv",
    candidateRollup: "candidate-rollup-senate-2026.csv",
    snapshotDate: "rollup-snapshot-date.txt",
    // Data Source: U.S. Census Bureau Congressional Districts (2024)
    // Using House districts as geometry for Senate view, colored by state
    // This avoids problematic state boundary geometry while showing cohesive state-level color
    geometryGeoJson: "congressional-districts.geojson",
    mapMode: "statewide",
  },
  us_governor: {
    general: "ballotpedia-governor-general-election-rollup.csv",
    primary: "ballotpedia-governor-primary-election-rollup.csv",
    runoff: "ballotpedia-governor-runoff-election-rollup.csv",
    departures: "ballotpedia-governor-incumbent-departures.csv",
    contestIndex: "kalshi-us-governor-contest-index.csv",
    joinAudit: "kalshi-us-governor-contest-integrity-violations.csv",
    candidateRollup: "governor-candidate-rollup-2026.csv",
    snapshotDate: "rollup-snapshot-date.txt",
    geometryGeoJson: "congressional-districts.geojson",
    mapMode: "statewide",
  },
  us_lieutenant_governor: {
    general: "ballotpedia-lieutenant-governor-general-election-rollup.csv",
    primary: "ballotpedia-lieutenant-governor-primary-election-rollup.csv",
    runoff: "ballotpedia-lieutenant-governor-runoff-election-rollup.csv",
    departures: "ballotpedia-lieutenant-governor-incumbent-departures.csv",
    contestIndex: "kalshi-us-lt-governor-contest-index.csv",
    joinAudit: "kalshi-us-lt-governor-contest-integrity-violations.csv",
    candidateRollup: "lieutenant-governor-candidate-rollup-2026.csv",
    snapshotDate: "rollup-snapshot-date.txt",
    geometryGeoJson: "congressional-districts.geojson",
    mapMode: "statewide",
  },
  us_attorney_general: {
    general: "ballotpedia-attorney-general-general-election-rollup.csv",
    primary: "ballotpedia-attorney-general-primary-election-rollup.csv",
    runoff: "ballotpedia-attorney-general-runoff-election-rollup.csv",
    departures: "ballotpedia-attorney-general-incumbent-departures.csv",
    contestIndex: "kalshi-us-attorney-general-contest-index.csv",
    joinAudit: "kalshi-us-attorney-general-contest-integrity-violations.csv",
    candidateRollup: "attorney-general-candidate-rollup-2026.csv",
    snapshotDate: "rollup-snapshot-date.txt",
    geometryGeoJson: "congressional-districts.geojson",
    mapMode: "statewide",
  },
};


const cachedBundleByScope = new Map<string, CanonicalDataBundle>();
const cachedRevisionByScope = new Map<string, string>();
const cachedGeoJsonByPath = new Map<string, { mtime: number; size: number; parsed: Record<string, unknown> }>();

function getScopeKey(office: Office, profile: LoadProfile): string {
  return `${office}:departures=${profile.includeDepartures ? "1" : "0"}:candidates=${profile.includeCandidates ? "1" : "0"}`;
}

export function resetCanonicalDataBundleCacheForTesting() {
  cachedBundleByScope.clear();
  cachedRevisionByScope.clear();
  cachedGeoJsonByPath.clear();
}

/**
 * Compute a cache revision key.
 *
 * In DB mode (DATABASE_URL set and an active batch exists): the revision is
 * `db:<batchId>` plus file mtimes for CSV-only data (candidates/departures).
 * This means a new batch promotion instantly invalidates the in-process cache.
 *
 * In CSV-only mode: revision is derived from file mtimes (existing behaviour).
 */
async function computeRevision(dataDir: string, office: Office, profile: LoadProfile): Promise<string> {
  const files = FILES_BY_OFFICE[office];

  const activeBatch = await getActiveBatch();
  if (activeBatch) {
    const parts = [`db:${activeBatch.batchId}`];
    // Candidates and departures still come from CSV — track their mtimes.
    const csvTracked: string[] = [];
    if (profile.includeCandidates) csvTracked.push(files.candidateRollup);
    if (profile.includeDepartures) csvTracked.push(files.departures);
    if (csvTracked.length) {
      const stats = await Promise.all(
        csvTracked.map(async (fileName) => {
          const filePath = path.join(dataDir, fileName);
          const s = await stat(filePath).catch(() => null);
          return s ? `${fileName}:${s.mtimeMs}:${s.size}` : `${fileName}:missing`;
        }),
      );
      parts.push(...stats);
    }
    return parts.join("|");
  }

  // CSV fallback: track all relevant files.
  const watched = [files.general, files.primary, files.runoff, files.snapshotDate];
  if (profile.includeCandidates) watched.push(files.candidateRollup);
  if (profile.includeDepartures) watched.push(files.departures);

  const parts = await Promise.all(
    watched.map(async (fileName) => {
      const filePath = path.join(dataDir, fileName);
      const s = await stat(filePath);
      return `${fileName}:${s.mtimeMs}:${s.size}`;
    }),
  );
  return parts.join("|");
}

async function readCsvFile(dataDir: string, fileName: string, keepColumns?: Set<string>): Promise<Record<string, string>[]> {
  const raw = await readFile(path.join(dataDir, fileName), "utf8");
  return parseCsvText(raw, keepColumns);
}

/**
 * Project a DB payload object to the same column set that CSV projection applies.
 * When DB is the source the full row is already in the payload, so we just filter keys.
 */
function projectPayload(payload: Record<string, string>, keep?: Set<string>): Record<string, string> {
  if (!keep) return payload;
  return Object.fromEntries(Object.entries(payload).filter(([k]) => keep.has(k)));
}

/**
 * Load general/primary/runoff rows from the DB.  Returns null if the DB has no
 * rows for this office (signals caller to fall back to CSV).
 */
async function tryLoadCoreRowsFromDb(office: Office, profile: LoadProfile): Promise<{
  generalRows: GeneralRow[];
  primaryRows: PrimaryRow[];
  runoffRows: RunoffRow[];
  snapshotDate: string;
} | null> {
  const activeBatch = await getActiveBatch();
  if (!activeBatch) return null;

  const generalKeep = !profile.includeCandidates ? MAP_GENERAL_KEEP : undefined;
  const primaryKeep = !profile.includeCandidates ? MAP_PRIMARY_KEEP : undefined;

  const [generalPayloads, primaryPayloads, runoffPayloads] = await Promise.all([
    loadGeneralPayloads(office),
    loadPrimaryPayloads(office),
    loadRunoffPayloads(office),
  ]);

  // If the DB has no general rows for this office the batch hasn't been loaded for it yet.
  if (!generalPayloads.length) return null;

  const generalRows = generalPayloads.map((p) => {
    const projected = projectPayload(p, generalKeep);
    return generalRowSchema.parse({ ...projected, seat: normalizeSeatId(projected.seat) });
  });
  const primaryRows = primaryPayloads.map((p) => {
    const projected = projectPayload(p, primaryKeep);
    return primaryRowSchema.parse({ ...projected, seat: normalizeSeatId(projected.seat) });
  });
  const runoffRows = runoffPayloads.map((p) =>
    runoffRowSchema.parse({ ...p, seat: normalizeSeatId(p.seat) }),
  );

  return { generalRows, primaryRows, runoffRows, snapshotDate: activeBatch.snapshotDate };
}

export async function loadCanonicalDataBundle(): Promise<CanonicalDataBundle> {
  return loadCanonicalDataBundleByOffice("us_house");
}

export async function loadCanonicalDataBundleByOffice(office: Office): Promise<CanonicalDataBundle> {
  return loadCanonicalDataBundleByOfficeWithProfile(office, DEFAULT_LOAD_PROFILE);
}

export async function loadCanonicalDataBundleForMapByOffice(office: Office): Promise<CanonicalDataBundle> {
  return loadCanonicalDataBundleByOfficeWithProfile(office, MAP_LOAD_PROFILE);
}

async function loadCanonicalDataBundleByOfficeWithProfile(office: Office, profile: LoadProfile): Promise<CanonicalDataBundle> {
  const dataDir = resolveDataDirectory();
  const files = FILES_BY_OFFICE[office];
  const scopeKey = getScopeKey(office, profile);
  const revision = await computeRevision(dataDir, office, profile);
  const cachedBundle = cachedBundleByScope.get(scopeKey);
  const cachedRevision = cachedRevisionByScope.get(scopeKey);
  if (cachedBundle && cachedRevision === revision) {
    return cachedBundle;
  }

  // --- Core rows: DB-first, fall back to CSV ---
  let generalRows: GeneralRow[];
  let primaryRows: PrimaryRow[];
  let runoffRows: RunoffRow[];
  let snapshotDate: string;
  let sourceAttribution: string[];

  const dbResult = await tryLoadCoreRowsFromDb(office, profile);

  if (dbResult) {
    ({ generalRows, primaryRows, runoffRows, snapshotDate } = dbResult);
    sourceAttribution = ["db:pv.v_general_rollup_current", "db:pv.v_primary_rollup_current", "db:pv.v_runoff_rollup_current"];
  } else {
    // CSV fallback
    const generalKeep = !profile.includeCandidates ? MAP_GENERAL_KEEP : undefined;
    const primaryKeep = !profile.includeCandidates ? MAP_PRIMARY_KEEP : undefined;
    const [generalRowsRaw, primaryRowsRaw, runoffRowsRaw, snapshotDateRaw] = await Promise.all([
      readCsvFile(dataDir, files.general, generalKeep),
      readCsvFile(dataDir, files.primary, primaryKeep),
      readCsvFile(dataDir, files.runoff),
      readFile(path.join(dataDir, files.snapshotDate), "utf8"),
    ]);

    assertRequiredColumns(generalRowsRaw, [...GENERAL_COLUMNS], files.general);
    assertRequiredColumns(primaryRowsRaw, [...PRIMARY_COLUMNS], files.primary);
    if (runoffRowsRaw.length) assertRequiredColumns(runoffRowsRaw, [...RUNOFF_COLUMNS], files.runoff);

    generalRows = generalRowsRaw.map((row) => generalRowSchema.parse({ ...row, seat: normalizeSeatId(row.seat) }));
    primaryRows = primaryRowsRaw.map((row) => primaryRowSchema.parse({ ...row, seat: normalizeSeatId(row.seat) }));
    runoffRows = runoffRowsRaw.map((row) => runoffRowSchema.parse({ ...row, seat: normalizeSeatId(row.seat) }));
    snapshotDate = snapshotDateRaw.trim();
    sourceAttribution = [files.general, files.primary, files.runoff, files.contestIndex, files.joinAudit];
  }

  // --- Candidates and departures: always CSV (not in DB yet) ---
  const [candidateRowsRaw, departureRowsRaw] = await Promise.all([
    profile.includeCandidates ? readCsvFile(dataDir, files.candidateRollup) : Promise.resolve([]),
    profile.includeDepartures ? readCsvFile(dataDir, files.departures) : Promise.resolve([]),
  ]);

  if (profile.includeCandidates && candidateRowsRaw.length) {
    assertRequiredColumns(candidateRowsRaw, [...CANDIDATE_COLUMNS], files.candidateRollup);
  }
  if (profile.includeDepartures && departureRowsRaw.length) {
    assertRequiredColumns(departureRowsRaw, [...DEPARTURES_COLUMNS], files.departures);
  }

  const candidateRows = candidateRowsRaw.map((row) =>
    candidateRowSchema.parse({ ...row, "2026 Seat": normalizeSeatId(row["2026 Seat"]) }),
  );
  const departureRows = departureRowsRaw.map((row) =>
    departureRowSchema.parse({ ...row, seat: normalizeSeatId(row.seat) }),
  );

  if (profile.includeCandidates) sourceAttribution.push(files.candidateRollup);
  if (profile.includeDepartures) sourceAttribution.push(files.departures);

  // --- GeoJSON (always file-based, cached by mtime) ---
  const geoJsonPath = path.join(dataDir, files.geometryGeoJson);
  const geoStat = await stat(geoJsonPath);
  const geoEntry = cachedGeoJsonByPath.get(geoJsonPath);
  let geometryGeoJson: Record<string, unknown>;
  if (geoEntry && geoEntry.mtime === geoStat.mtimeMs && geoEntry.size === geoStat.size) {
    geometryGeoJson = geoEntry.parsed;
  } else {
    const raw = await readFile(geoJsonPath, "utf8");
    geometryGeoJson = JSON.parse(raw) as Record<string, unknown>;
    cachedGeoJsonByPath.set(geoJsonPath, { mtime: geoStat.mtimeMs, size: geoStat.size, parsed: geometryGeoJson });
  }

  const bundle: CanonicalDataBundle = {
    office,
    mapMode: files.mapMode,
    snapshotDate,
    updatedAt: new Date().toISOString(),
    sourceAttribution,
    generalRows,
    primaryRows,
    runoffRows,
    departureRows,
    candidateRows,
    geometryGeoJson,
  };
  cachedBundleByScope.set(scopeKey, bundle);
  cachedRevisionByScope.set(scopeKey, revision);

  return bundle;
}
