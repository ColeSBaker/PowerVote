import { afterAll, beforeAll, describe, expect, test, vi } from "vitest";

// Force dynamic path so Server-Timing headers are emitted.
// Static artifact serving (tested separately in static-vs-dynamic.test.ts) bypasses
// the timing instrumentation that these tests verify.
vi.mock("@/lib/server/paths", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server/paths")>();
  return { ...actual, resolveStaticArtifactsDirectory: () => null };
});

import { GET as getMapDistricts } from "@/app/api/v1/map/districts/route";
import { GET as getMobileBootstrap } from "@/app/api/v1/mobile/bootstrap/route";
import { GET as getPowerVote } from "@/app/api/v1/powervote/route";
import { resetMapDistrictsResponseCacheForTesting } from "@/lib/server/api-service";
import { resetCanonicalDataBundleCacheForTesting } from "@/lib/server/data-source";

type TimingMetrics = Record<string, { dur?: number; desc?: string }>;

type RouteBenchRow = {
  route: string;
  coldTotalMs: number;
  warmTotalMs: number;
  speedupPct: number;
  coldLoadMs?: number;
  warmLoadMs?: number;
  coldBuildMs?: number;
  warmBuildMs?: number;
  coldSchemaMs?: number;
  warmSchemaMs?: number;
  coldTransformMs?: number;
  warmTransformMs?: number;
  coldResolveMs?: number;
  warmResolveMs?: number;
  warmCache?: string;
};

const rows: RouteBenchRow[] = [];

function parseServerTiming(header: string): TimingMetrics {
  return header
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .reduce<TimingMetrics>((acc, entry) => {
      const [namePart, ...rest] = entry.split(";");
      const name = namePart.trim();
      const metric: { dur?: number; desc?: string } = {};
      for (const part of rest) {
        const trimmed = part.trim();
        if (trimmed.startsWith("dur=")) {
          const parsed = Number(trimmed.slice(4));
          if (Number.isFinite(parsed)) {
            metric.dur = parsed;
          }
        }
        if (trimmed.startsWith("desc=")) {
          metric.desc = trimmed.slice(5).replace(/^"|"$/g, "");
        }
      }
      acc[name] = metric;
      return acc;
    }, {});
}

async function measureRoute(
  route: string,
  buildRequest: () => Request,
  run: (request: Request) => Promise<Response>,
): Promise<RouteBenchRow> {
  resetMapDistrictsResponseCacheForTesting();
  resetCanonicalDataBundleCacheForTesting();

  const coldResponse = await run(buildRequest());
  const warmResponse = await run(buildRequest());

  expect(coldResponse.status).toBe(200);
  expect(warmResponse.status).toBe(200);

  const coldTiming = parseServerTiming(coldResponse.headers.get("Server-Timing") ?? "");
  const warmTiming = parseServerTiming(warmResponse.headers.get("Server-Timing") ?? "");

  const coldTotalMs = coldTiming.total?.dur ?? 0;
  const warmTotalMs = warmTiming.total?.dur ?? 0;
  const speedupPct = coldTotalMs > 0 ? ((coldTotalMs - warmTotalMs) / coldTotalMs) * 100 : 0;

  return {
    route,
    coldTotalMs,
    warmTotalMs,
    speedupPct,
    coldLoadMs: coldTiming.load?.dur,
    warmLoadMs: warmTiming.load?.dur,
    coldBuildMs: coldTiming.build?.dur,
    warmBuildMs: warmTiming.build?.dur,
    coldSchemaMs: coldTiming.schema?.dur,
    warmSchemaMs: warmTiming.schema?.dur,
    coldTransformMs: coldTiming.transform?.dur,
    warmTransformMs: warmTiming.transform?.dur,
    coldResolveMs: coldTiming.resolve?.dur,
    warmResolveMs: warmTiming.resolve?.dur,
    warmCache: warmTiming.cache?.desc,
  };
}

describe("route Server-Timing warm/cold latency", () => {
  beforeAll(async () => {
    rows.push(
      await measureRoute(
        "/api/v1/map/districts?office=us_house&election_view=general&color_mode=contention",
        () =>
          new Request(
            "http://localhost/api/v1/map/districts?office=us_house&election_view=general&color_mode=contention",
          ),
        getMapDistricts,
      ),
    );

    rows.push(
      await measureRoute(
        "/api/v1/powervote?seat_id=CA-01&office=us_house",
        () => new Request("http://localhost/api/v1/powervote?seat_id=CA-01&office=us_house"),
        getPowerVote,
      ),
    );

    rows.push(
      await measureRoute(
        "/api/v1/mobile/bootstrap",
        () => new Request("http://localhost/api/v1/mobile/bootstrap"),
        getMobileBootstrap,
      ),
    );
  });

  test("captures cold and warm total timings for each instrumented route", () => {
    expect(rows).toHaveLength(3);
    for (const row of rows) {
      expect(row.coldTotalMs).toBeGreaterThan(0);
      expect(row.warmTotalMs).toBeGreaterThan(0);
      expect(row.warmTotalMs).toBeLessThanOrEqual(row.coldTotalMs * 1.25);
    }
  });

  test("marks map route warm requests as cache hit", () => {
    const mapRow = rows.find((row) => row.route.startsWith("/api/v1/map/districts"));
    expect(mapRow?.warmCache).toBe("hit");
  });

  afterAll(() => {
    // eslint-disable-next-line no-console
    console.table(
      rows.map((row) => ({
        route: row.route,
        cold_total_ms: row.coldTotalMs.toFixed(2),
        warm_total_ms: row.warmTotalMs.toFixed(2),
        speedup_pct: row.speedupPct.toFixed(2),
        cold_load_ms: row.coldLoadMs?.toFixed(2),
        warm_load_ms: row.warmLoadMs?.toFixed(2),
        cold_transform_ms: row.coldTransformMs?.toFixed(2),
        warm_transform_ms: row.warmTransformMs?.toFixed(2),
        cold_resolve_ms: row.coldResolveMs?.toFixed(2),
        warm_resolve_ms: row.warmResolveMs?.toFixed(2),
        cold_build_ms: row.coldBuildMs?.toFixed(2),
        warm_build_ms: row.warmBuildMs?.toFixed(2),
        cold_schema_ms: row.coldSchemaMs?.toFixed(2),
        warm_schema_ms: row.warmSchemaMs?.toFixed(2),
        warm_cache: row.warmCache,
      })),
    );
  });
});
