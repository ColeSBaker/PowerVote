import { afterAll, describe, expect, test } from "vitest";

import {
  loadCanonicalDataBundleByOffice,
  loadCanonicalDataBundleForMapByOffice,
  resetCanonicalDataBundleCacheForTesting,
} from "@/lib/server/data-source";

type Sample = { fullMs: number; mapMs: number; deltaMs: number; deltaPct: number };

const samples: Sample[] = [];

function elapsedMs(start: bigint) {
  return Number(process.hrtime.bigint() - start) / 1_000_000;
}

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

async function measureOnce() {
  resetCanonicalDataBundleCacheForTesting();
  const fullStart = process.hrtime.bigint();
  const full = await loadCanonicalDataBundleByOffice("us_house");
  const fullMs = elapsedMs(fullStart);

  resetCanonicalDataBundleCacheForTesting();
  const mapStart = process.hrtime.bigint();
  const map = await loadCanonicalDataBundleForMapByOffice("us_house");
  const mapMs = elapsedMs(mapStart);

  expect(full.departureRows.length).toBeGreaterThan(0);
  expect(map.departureRows).toHaveLength(0);

  const deltaMs = fullMs - mapMs;
  const deltaPct = fullMs > 0 ? (deltaMs / fullMs) * 100 : 0;
  samples.push({ fullMs, mapMs, deltaMs, deltaPct });
}

describe("map loader profile latency", () => {
  test("map-specific profile reduces or holds cold load time vs full profile", async () => {
    for (let i = 0; i < 5; i += 1) {
      await measureOnce();
    }

    const fullMedian = median(samples.map((s) => s.fullMs));
    const mapMedian = median(samples.map((s) => s.mapMs));

    expect(mapMedian).toBeLessThanOrEqual(fullMedian * 1.2);
  }, 30_000);

  afterAll(() => {
    const fullMedian = median(samples.map((s) => s.fullMs));
    const mapMedian = median(samples.map((s) => s.mapMs));
    const deltaMs = fullMedian - mapMedian;
    const deltaPct = fullMedian > 0 ? (deltaMs / fullMedian) * 100 : 0;

    // eslint-disable-next-line no-console
    console.table(
      samples.map((sample, index) => ({
        run: index + 1,
        full_ms: sample.fullMs.toFixed(2),
        map_profile_ms: sample.mapMs.toFixed(2),
        delta_ms: sample.deltaMs.toFixed(2),
        delta_pct: sample.deltaPct.toFixed(2),
      })),
    );

    // eslint-disable-next-line no-console
    console.log(
      `[map-loader-profile] median_full_ms=${fullMedian.toFixed(2)} median_map_profile_ms=${mapMedian.toFixed(2)} median_delta_ms=${deltaMs.toFixed(2)} median_delta_pct=${deltaPct.toFixed(2)}`,
    );
  });
});
