import { beforeEach, describe, expect, test, vi } from "vitest";

import * as dataSource from "@/lib/server/data-source";
import {
  buildMapDistrictsResponse,
  resetMapDistrictsResponseCacheForTesting,
} from "@/lib/server/api-service";

function makeBundle(args: { updatedAt: string; snapshotDate: string; generalStatus?: string }) {
  return {
    office: "us_house" as const,
    mapMode: "district" as const,
    snapshotDate: args.snapshotDate,
    updatedAt: args.updatedAt,
    sourceAttribution: ["test"],
    generalRows: [
      {
        seat: "CA-01",
        district: "California 1",
        general_status: args.generalStatus ?? "contested",
        incumbent_party: "DEM",
        kalshi_general_odds_map: "",
        general_election_race_ratings: "",
        dccc_target: "False",
        nrcc_target: "False",
        dscc_target: "False",
        nrsc_target: "False",
        primary_status_d: "none",
        primary_status_r: "none",
      },
    ],
    primaryRows: [],
    runoffRows: [],
    departureRows: [],
    candidateRows: [],
    geometryGeoJson: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { seatId: "CA-01" },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [-122, 38],
                [-121, 38],
                [-121, 37],
                [-122, 37],
                [-122, 38],
              ],
            ],
          },
        },
      ],
    },
  };
}

describe("map districts cache", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-10T00:00:00.000Z"));
    resetMapDistrictsResponseCacheForTesting();
    vi.restoreAllMocks();
  });

  test("serves warm requests from cache without reloading data", async () => {
    const loader = vi
      .spyOn(dataSource, "loadCanonicalDataBundleForMapByOffice")
      .mockResolvedValue(makeBundle({ updatedAt: "2026-04-10T00:00:00.000Z", snapshotDate: "2026-04-10" }) as never);

    const first = await buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" });
    const second = await buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" });

    expect(second).toBe(first);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  test("refreshes TTL but preserves object when revision is unchanged", async () => {
    const loader = vi
      .spyOn(dataSource, "loadCanonicalDataBundleForMapByOffice")
      .mockResolvedValue(makeBundle({ updatedAt: "2026-04-10T00:00:00.000Z", snapshotDate: "2026-04-10" }) as never);

    const first = await buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" });
    vi.advanceTimersByTime(31_000);
    const second = await buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" });

    expect(second).toBe(first);
    expect(loader).toHaveBeenCalledTimes(2);
  });

  test("invalidates cached payload when source revision changes", async () => {
    const loader = vi.spyOn(dataSource, "loadCanonicalDataBundleForMapByOffice");
    loader
      .mockResolvedValueOnce(makeBundle({ updatedAt: "2026-04-10T00:00:00.000Z", snapshotDate: "2026-04-10", generalStatus: "contested" }) as never)
      .mockResolvedValueOnce(makeBundle({ updatedAt: "2026-04-10T00:00:30.000Z", snapshotDate: "2026-04-11", generalStatus: "uncontested" }) as never);

    const first = await buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" });
    vi.advanceTimersByTime(31_000);
    const second = await buildMapDistrictsResponse({ office: "us_house", electionView: "general", colorMode: "contention" });

    expect(second).not.toBe(first);
    expect(second.snapshotDate).toBe("2026-04-11");
    expect(loader).toHaveBeenCalledTimes(2);
  });
});
