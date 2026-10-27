import { describe, expect, test } from "vitest";

import {
  loadCanonicalDataBundleByOffice,
  loadCanonicalDataBundleForMapByOffice,
  resetCanonicalDataBundleCacheForTesting,
} from "@/lib/server/data-source";

describe("map-specific canonical loader", () => {
  test("skips departures dataset for map profile while preserving core rows", async () => {
    resetCanonicalDataBundleCacheForTesting();

    const full = await loadCanonicalDataBundleByOffice("us_house");
    resetCanonicalDataBundleCacheForTesting();
    const map = await loadCanonicalDataBundleForMapByOffice("us_house");

    expect(full.generalRows.length).toBeGreaterThan(0);
    expect(map.generalRows.length).toBe(full.generalRows.length);
    expect(map.departureRows).toHaveLength(0);
    expect(full.sourceAttribution).toContain("ballotpedia-incumbent-departures.csv");
    expect(map.sourceAttribution).not.toContain("ballotpedia-incumbent-departures.csv");
  });
});
