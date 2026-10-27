import { describe, expect, test } from "vitest";

import {
  buildDistrictDetailResponse,
  buildMapDistrictsResponse,
  buildPowerVoteAllResponse,
  resetMapDistrictsResponseCacheForTesting,
} from "@/lib/server/api-service";
import { buildMobileBootstrapResponse } from "@/lib/server/mobile-api";
import { resetCanonicalDataBundleCacheForTesting } from "@/lib/server/data-source";

type Budget = {
  name: string;
  maxColdMs: number;
  run: () => Promise<unknown>;
};

function elapsedMs(start: bigint) {
  return Number(process.hrtime.bigint() - start) / 1_000_000;
}

async function measureColdMs(run: () => Promise<unknown>) {
  resetMapDistrictsResponseCacheForTesting();
  resetCanonicalDataBundleCacheForTesting();
  const start = process.hrtime.bigint();
  await run();
  return elapsedMs(start);
}

const budgets: Budget[] = [
  {
    // Map profile skips candidate-rollup-2026.csv (2.4 MB), reducing cold IO.
    // Budget reflects Windows/OneDrive cold-read variance; target is <1500ms after further optimization.
    name: "buildMapDistrictsResponse(us_house/general/contention)",
    maxColdMs: 2_500,
    run: () => buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" }),
  },
  {
    name: "buildDistrictDetailResponse(AL-01)",
    maxColdMs: 2_500,
    run: () => buildDistrictDetailResponse({ seatId: "AL-01", office: "us_house", electionView: "general" }),
  },
  {
    name: "buildPowerVoteAllResponse(2 seats)",
    maxColdMs: 2_500,
    run: () => buildPowerVoteAllResponse({ seatId: "CA-01", compareSeatId: "CA-02" }),
  },
  {
    // DEFAULT_LOAD_PROFILE loads full candidate CSV (2.4 MB); budget reflects Windows/OneDrive cold-read variance.
    name: "buildMobileBootstrapResponse()",
    maxColdMs: 3_000,
    run: () => buildMobileBootstrapResponse(),
  },
];

describe("cold-load performance budgets", () => {
  test("key cold paths stay under budget", async () => {
    const rows: Array<{ name: string; coldMs: number; maxColdMs: number }> = [];

    for (const budget of budgets) {
      const coldMs = await measureColdMs(budget.run);
      rows.push({ name: budget.name, coldMs, maxColdMs: budget.maxColdMs });
      expect(coldMs).toBeLessThanOrEqual(budget.maxColdMs);
    }

    // eslint-disable-next-line no-console
    console.table(
      rows.map((row) => ({
        fn: row.name,
        cold_ms: row.coldMs.toFixed(2),
        budget_ms: row.maxColdMs,
      })),
    );
  }, 30_000);
});
