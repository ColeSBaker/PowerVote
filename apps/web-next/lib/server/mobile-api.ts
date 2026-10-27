import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { parseCandidateOdds } from "@/lib/server/metrics";
import { loadCanonicalDataBundleByOffice } from "@/lib/server/data-source";
import { resolveDataDirectory } from "@/lib/server/paths";
import { ClientInputError } from "@/lib/server/errors";
import { mobileBootstrapResponseSchema, mobileDeltaResponseSchema, mobileSeatResponseSchema } from "@/lib/domain/schemas";
import type { Office } from "@/lib/domain/schemas";

export type SnapshotMetadata = {
  snapshotId: string;
  snapshotDate: string;
  schemaVersion: string;
  generatedAt: string;
};

type MobileBootstrapTimingCollector = (timing: {
  loadMs: number;
  buildMs: number;
  schemaMs: number;
  totalMs: number;
}) => void;


async function loadSnapshotMetadata(): Promise<SnapshotMetadata> {
  const dataDir = resolveDataDirectory();
  const manifestPath = path.join(dataDir, "snapshot_manifest.json");
  if (existsSync(manifestPath)) {
    const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as Record<string, unknown>;
    return {
      snapshotId: String(manifest.snapshotId ?? ""),
      snapshotDate: String(manifest.snapshotDate ?? ""),
      schemaVersion: String(manifest.schemaVersion ?? "v1"),
      generatedAt: String(manifest.generatedAt ?? new Date().toISOString()),
    };
  }

  const bundle = await loadCanonicalDataBundleByOffice("us_house");
  return {
    snapshotId: `${bundle.snapshotDate}-fallback`,
    snapshotDate: bundle.snapshotDate,
    schemaVersion: "v1",
    generatedAt: bundle.updatedAt,
  };
}

function buildEtag(snapshotId: string, schemaVersion: string): string {
  const digest = createHash("sha256").update(`${snapshotId}:${schemaVersion}`).digest("hex");
  return `\"${digest}\"`;
}

function buildOfficePayload(bundle: Awaited<ReturnType<typeof loadCanonicalDataBundleByOffice>>) {
  const seatSummaries = bundle.generalRows.map((row) => ({
    seatId: row.seat,
    state: row.seat.split("-")[0],
    generalStatus: row.general_status || "unknown",
    incumbentParty: row.incumbent_party || null,
    primaryStatusD: row.primary_status_d || null,
    primaryStatusR: row.primary_status_r || null,
    primaryStatusNP: row.primary_status_np || null,
    kalshiGeneralOddsMap: row.kalshi_general_odds_map || "",
  }));

  const candidateOdds = bundle.candidateRows.map((row) => ({
    seatId: row["2026 Seat"],
    ballotpediaName: row.BallotpediaName,
    party: row.Party,
    bestPrimaryOdds: parseCandidateOdds(row.KalshiBestPrimaryOdds),
    bestGeneralOdds: parseCandidateOdds(row.KalshiBestGeneralOdds),
  }));

  return {
    seatSummaries,
    candidateOdds,
  };
}

export async function buildMobileBootstrapResponse(onTiming?: MobileBootstrapTimingCollector) {
  const totalStart = process.hrtime.bigint();
  const loadStart = process.hrtime.bigint();
  const [houseBundle, senateBundle, snapshot] = await Promise.all([
    loadCanonicalDataBundleByOffice("us_house"),
    loadCanonicalDataBundleByOffice("us_senate"),
    loadSnapshotMetadata(),
  ]);
  const loadMs = Number(process.hrtime.bigint() - loadStart) / 1_000_000;
  const buildStart = process.hrtime.bigint();
  const etag = buildEtag(snapshot.snapshotId, snapshot.schemaVersion);

  const payload = {
    snapshotId: snapshot.snapshotId,
    snapshotDate: snapshot.snapshotDate,
    schemaVersion: snapshot.schemaVersion,
    etag,
    generatedAt: snapshot.generatedAt,
    data: {
      us_house: buildOfficePayload(houseBundle),
      us_senate: buildOfficePayload(senateBundle),
    },
  };
  const buildMs = Number(process.hrtime.bigint() - buildStart) / 1_000_000;
  const schemaStart = process.hrtime.bigint();
  const parsed = mobileBootstrapResponseSchema.parse(payload);
  const schemaMs = Number(process.hrtime.bigint() - schemaStart) / 1_000_000;
  onTiming?.({
    loadMs,
    buildMs,
    schemaMs,
    totalMs: Number(process.hrtime.bigint() - totalStart) / 1_000_000,
  });
  return parsed;
}

export async function buildMobileDeltaResponse(since: string | null) {
  const current = await buildMobileBootstrapResponse();
  const hasChanges = !since || since !== current.snapshotId;

  const payload = {
    snapshotId: current.snapshotId,
    snapshotDate: current.snapshotDate,
    schemaVersion: current.schemaVersion,
    etag: current.etag,
    generatedAt: current.generatedAt,
    since: since ?? null,
    hasChanges,
    changes: hasChanges
      ? current.data
      : {
          us_house: { seatSummaries: [], candidateOdds: [] },
          us_senate: { seatSummaries: [], candidateOdds: [] },
        },
  };

  return mobileDeltaResponseSchema.parse(payload);
}

type MobileOffice = "us_house" | "us_senate";

export async function buildMobileSeatResponse(seatId: string, office?: Office) {
  const normalizedSeatId = seatId.trim().toUpperCase();
  const current = await buildMobileBootstrapResponse();
  const mobileOffice = office === "us_house" || office === "us_senate" ? office : undefined;
  const officeKeys: MobileOffice[] = mobileOffice ? [mobileOffice] : ["us_house", "us_senate"];

  for (const officeKey of officeKeys) {
    const officeData = current.data[officeKey as MobileOffice];
    const seat = officeData.seatSummaries.find((row) => row.seatId === normalizedSeatId);
    if (!seat) continue;

    const payload = {
      snapshotId: current.snapshotId,
      snapshotDate: current.snapshotDate,
      schemaVersion: current.schemaVersion,
      etag: current.etag,
      generatedAt: current.generatedAt,
      data: {
        office: officeKey,
        seat,
        candidates: officeData.candidateOdds.filter((row) => row.seatId === normalizedSeatId),
      },
    };
    return mobileSeatResponseSchema.parse(payload);
  }

  throw new ClientInputError(`No seat found for ${normalizedSeatId}`);
}

export function buildMobileCacheHeaders(payload: { etag: string; generatedAt: string; snapshotId: string }) {
  return {
    ETag: payload.etag,
    "Last-Modified": payload.generatedAt,
    "X-Snapshot-Id": payload.snapshotId,
    "Cache-Control": "public, max-age=60, stale-while-revalidate=300",
  };
}
