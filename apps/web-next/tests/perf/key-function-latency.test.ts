import { afterAll, beforeAll, describe, expect, test } from "vitest";

import {
  buildDistrictDetailResponse,
  buildMapDistrictsResponse,
  buildPowerVoteAllResponse,
  buildPowerVoteCompareResponse,
  buildPowerVoteResponse,
  buildPowerVoteSeatOptionsResponse,
  resetMapDistrictsResponseCacheForTesting,
} from "@/lib/server/api-service";
import {
  buildMobileBootstrapResponse,
  buildMobileDeltaResponse,
  buildMobileSeatResponse,
} from "@/lib/server/mobile-api";
import { resetCanonicalDataBundleCacheForTesting } from "@/lib/server/data-source";

type BenchRow = {
  fn: string;
  coldMs: number;
  warmMs: number;
  speedupPct: number;
};

const results: BenchRow[] = [];

function ms(start: bigint): number {
  return Number(process.hrtime.bigint() - start) / 1_000_000;
}

async function measure(name: string, fn: () => Promise<unknown>) {
  resetMapDistrictsResponseCacheForTesting();
  resetCanonicalDataBundleCacheForTesting();

  const coldStart = process.hrtime.bigint();
  await fn();
  const coldMs = ms(coldStart);

  const warmStart = process.hrtime.bigint();
  await fn();
  const warmMs = ms(warmStart);

  const speedupPct = coldMs > 0 ? ((coldMs - warmMs) / coldMs) * 100 : 0;
  results.push({ fn: name, coldMs, warmMs, speedupPct });
}

describe("frontend key function latency (cold vs warm)", () => {
  beforeAll(async () => {
    await measure("buildMapDistrictsResponse(us_house/general/contention)", () =>
      buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" }),
    );
    await measure("buildDistrictDetailResponse(AL-01)", () =>
      buildDistrictDetailResponse({ seatId: "AL-01", office: "us_house", electionView: "general" }),
    );
    await measure("buildPowerVoteSeatOptionsResponse(us_house)", () =>
      buildPowerVoteSeatOptionsResponse({ office: "us_house" }),
    );
    await measure("buildPowerVoteResponse(seatId=CA-01)", () =>
      buildPowerVoteResponse({ office: "us_house", seatId: "CA-01" }),
    );
    await measure("buildPowerVoteAllResponse(2 seats)", () =>
      buildPowerVoteAllResponse({ seatId: "CA-01", compareSeatId: "CA-02" }),
    );
    await measure("buildPowerVoteCompareResponse(3 seats)", () =>
      buildPowerVoteCompareResponse({ office: "us_house", seatIds: ["CA-01", "CA-02", "AK-AL"] }),
    );
    await measure("buildMobileBootstrapResponse()", () => buildMobileBootstrapResponse());
    await measure("buildMobileDeltaResponse(since=none)", () => buildMobileDeltaResponse(null));
    await measure("buildMobileSeatResponse(AL-01)", () => buildMobileSeatResponse("AL-01", "us_house"));
  }, 60_000);

  test("records latency values for all key functions", () => {
    expect(results.length).toBe(9);
    for (const row of results) {
      expect(row.coldMs).toBeGreaterThan(0);
      expect(row.warmMs).toBeGreaterThan(0);
    }
  });

  test("warm-path stays within 20% of cold-path for all functions", () => {
    for (const row of results) {
      expect(row.warmMs).toBeLessThanOrEqual(row.coldMs * 1.2);
    }
  });

  afterAll(() => {
    // eslint-disable-next-line no-console
    console.table(
      results.map((row) => ({
        fn: row.fn,
        cold_ms: row.coldMs.toFixed(2),
        warm_ms: row.warmMs.toFixed(2),
        speedup_pct: row.speedupPct.toFixed(2),
      })),
    );
  });
});
