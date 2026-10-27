/**
 * Measures static artifact serving vs dynamic generation for the two
 * endpoints targeted by P1#6.
 *
 * Static path:  resolveStaticArtifactsDirectory() + existsSync + readFile + Response
 * Dynamic path: buildMapDistrictsResponse / buildMobileBootstrapResponse (cold)
 *
 * Run: npx vitest run tests/perf/static-vs-dynamic.bench.ts
 */

import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, test, expect, beforeAll, afterAll } from "vitest";

import { buildMapDistrictsResponse, resetMapDistrictsResponseCacheForTesting } from "@/lib/server/api-service";
import { buildMobileBootstrapResponse } from "@/lib/server/mobile-api";
import { resetCanonicalDataBundleCacheForTesting } from "@/lib/server/data-source";
import { resolveStaticArtifactsDirectory } from "@/lib/server/paths";

function ms(start: bigint) {
  return Number(process.hrtime.bigint() - start) / 1_000_000;
}

async function measureCold(fn: () => Promise<unknown>): Promise<number> {
  resetMapDistrictsResponseCacheForTesting();
  resetCanonicalDataBundleCacheForTesting();
  const t = process.hrtime.bigint();
  await fn();
  return ms(t);
}

async function measureStatic(fn: () => Promise<unknown>, runs = 5): Promise<number> {
  // Warm up once (first call may have OS file cache cold)
  await fn();
  // Average over several runs
  let total = 0;
  for (let i = 0; i < runs; i++) {
    const t = process.hrtime.bigint();
    await fn();
    total += ms(t);
  }
  return total / runs;
}

// ── Static helpers ────────────────────────────────────────────────────────────

async function serveStaticMapDistricts(office: string, electionView: string, colorMode: string): Promise<string> {
  const staticDir = resolveStaticArtifactsDirectory();
  if (!staticDir) throw new Error("Static artifacts directory not found");
  const filePath = path.join(staticDir, `map-districts--${office}--${electionView}--${colorMode}.json`);
  if (!existsSync(filePath)) throw new Error(`Static file not found: ${filePath}`);
  return readFile(filePath, "utf-8");
}

async function serveStaticMobileBootstrap(): Promise<string> {
  const staticDir = resolveStaticArtifactsDirectory();
  if (!staticDir) throw new Error("Static artifacts directory not found");
  const filePath = path.join(staticDir, "mobile-bootstrap.json");
  if (!existsSync(filePath)) throw new Error(`Static file not found: ${filePath}`);
  return readFile(filePath, "utf-8");
}

// ── Results ───────────────────────────────────────────────────────────────────

type Row = {
  endpoint: string;
  dynamic_cold_ms: string;
  static_avg_ms: string;
  speedup: string;
};

const rows: Row[] = [];

describe("P1#6 static vs dynamic serving latency", () => {
  let staticDirExists = false;

  beforeAll(() => {
    staticDirExists = resolveStaticArtifactsDirectory() !== null;
  });

  test("static artifacts directory exists", () => {
    expect(staticDirExists).toBe(true);
  });

  test("map/districts — us_house general contention", async () => {
    const dynamicMs = await measureCold(() =>
      buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" }),
    );
    const staticMs = await measureStatic(() => serveStaticMapDistricts("us_house", "general", "contention"));
    const speedup = (dynamicMs / staticMs).toFixed(1);
    rows.push({ endpoint: "map/districts (us_house/general/contention)", dynamic_cold_ms: dynamicMs.toFixed(1), static_avg_ms: staticMs.toFixed(1), speedup: `${speedup}×` });
    expect(staticMs).toBeLessThan(dynamicMs);
  }, 30_000);

  test("map/districts — us_senate general contention", async () => {
    const dynamicMs = await measureCold(() =>
      buildMapDistrictsResponse({ office: "us_senate", electionView: "general", colorMode: "contention" }),
    );
    const staticMs = await measureStatic(() => serveStaticMapDistricts("us_senate", "general", "contention"));
    const speedup = (dynamicMs / staticMs).toFixed(1);
    rows.push({ endpoint: "map/districts (us_senate/general/contention)", dynamic_cold_ms: dynamicMs.toFixed(1), static_avg_ms: staticMs.toFixed(1), speedup: `${speedup}×` });
    expect(staticMs).toBeLessThan(dynamicMs);
  }, 30_000);

  test("mobile/bootstrap", async () => {
    const dynamicMs = await measureCold(() => buildMobileBootstrapResponse());
    const staticMs = await measureStatic(() => serveStaticMobileBootstrap());
    const speedup = (dynamicMs / staticMs).toFixed(1);
    rows.push({ endpoint: "mobile/bootstrap", dynamic_cold_ms: dynamicMs.toFixed(1), static_avg_ms: staticMs.toFixed(1), speedup: `${speedup}×` });
    expect(staticMs).toBeLessThan(dynamicMs);
  }, 30_000);

  afterAll(() => {
    // eslint-disable-next-line no-console
    console.table(rows);
  });
});
