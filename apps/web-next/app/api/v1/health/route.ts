import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextResponse } from "next/server";

import { resolveDataDirectory } from "@/lib/server/paths";

const STALE_THRESHOLD_HOURS = 36;

export async function GET() {
  const dataDir = resolveDataDirectory();
  let snapshotDate: string | null = null;
  let snapshotAgeHours: number | null = null;
  let stale = false;

  try {
    const raw = await readFile(path.join(dataDir, "rollup-snapshot-date.txt"), "utf8");
    snapshotDate = raw.trim();
    const snapshotMs = new Date(snapshotDate).getTime();
    if (!Number.isNaN(snapshotMs)) {
      snapshotAgeHours = Math.round(((Date.now() - snapshotMs) / 3_600_000) * 10) / 10;
      stale = snapshotAgeHours > STALE_THRESHOLD_HOURS;
    }
  } catch {
    // snapshot date file unreadable — surface as stale
    stale = true;
  }

  const status = stale ? "stale" : "ok";
  return NextResponse.json(
    {
      status,
      snapshotDate,
      snapshotAgeHours,
      staleThresholdHours: STALE_THRESHOLD_HOURS,
    },
    {
      status: stale ? 503 : 200,
      headers: { "Cache-Control": "no-store" },
    },
  );
}
