import { describe, expect, test } from "vitest";

import {
  districtDetailResponseSchema,
  mapDistrictsResponseSchema,
  powerVoteAllResponseSchema,
  powerVoteCompareResponseSchema,
  powerVoteSeatOptionsResponseSchema,
  powerVoteResponseSchema,
} from "@/lib/domain/schemas";
import {
  buildPowerVoteAllResponse,
  buildDistrictDetailResponse,
  buildMapDistrictsResponse,
  buildPowerVoteCompareResponse,
  buildPowerVoteSeatOptionsResponse,
  buildPowerVoteResponse,
} from "@/lib/server/api-service";

async function findHouseSeatWithNoSenateRace(): Promise<string> {
  const houseOptions = await buildPowerVoteSeatOptionsResponse({ office: "us_house" });
  const senateOptions = await buildPowerVoteSeatOptionsResponse({ office: "us_senate" });
  const senateStates = new Set(senateOptions.states.map((state) => state.stateCode));
  const noSenateState = houseOptions.states.find((state) => !senateStates.has(state.stateCode) && state.seats.length > 0);
  if (!noSenateState) {
    throw new Error("No house state without senate races found in fixture data.");
  }
  return noSenateState.seats[0].seatId;
}

describe("api contract integration", () => {
  test("map districts endpoint payload matches schema", async () => {
    const payload = await buildMapDistrictsResponse({
      office: "us_house",
      electionView: "general",
      colorMode: "contention",
    });
    expect(() => mapDistrictsResponseSchema.parse(payload)).not.toThrow();
    expect(payload.districts.length).toBeGreaterThan(400);
    const featureSeatIds = new Set(payload.featureCollection.features.map((feature) => String(feature.properties.seatId || "")));
    expect(featureSeatIds.has("AK-AL")).toBe(true);
    expect(featureSeatIds.has("HI-01")).toBe(true);
    expect(featureSeatIds.has("HI-02")).toBe(true);
  });

  test("primary kalshi color mode exposes party-lane market legend keys", async () => {
    const payload = await buildMapDistrictsResponse({
      office: "us_house",
      electionView: "primary",
      colorMode: "primary_kalshi",
    });
    expect(() => mapDistrictsResponseSchema.parse(payload)).not.toThrow();
    expect(payload.legend.map((entry) => entry.key)).toEqual(["primary_market_both", "primary_market_dem", "primary_market_rep", "primary_market_none"]);
    const al01 = payload.districts.find((row) => row.seatId === "AL-01");
    expect(al01).toBeDefined();
    expect(al01?.colorKey).not.toBe("primary_market_none");
    expect(payload.districts.some((row) => row.colorKey !== "primary_market_none")).toBe(true);
  });

  test("district detail payload matches schema", async () => {
    const payload = await buildDistrictDetailResponse({
      seatId: "AL-01",
      office: "us_house",
      electionView: "general",
    });
    expect(() => districtDetailResponseSchema.parse(payload)).not.toThrow();
    expect(payload.seatId).toBe("AL-01");
    expect(payload.generalElection.partyLanes.length).toBeGreaterThanOrEqual(2);
    expect(payload.generalElection.partyLanes.some((lane) => lane.party === "DEM")).toBe(true);
    expect(payload.generalElection.partyLanes.some((lane) => lane.party === "REP")).toBe(true);
    expect(payload.incumbencyAndControl).toBeDefined();
    expect(payload.competitiveness).toBeDefined();
    expect(payload.primaryElection.parties.length).toBeGreaterThan(0);
  });

  test("powervote payload matches schema with mocked geocode", async () => {
    const payload = await buildPowerVoteResponse({
      address: "Mock Address",
      office: "us_house",
      geocode: async () => ({
        normalizedAddress: "Mock Address",
        latitude: 38.89,
        longitude: -77.03,
        seatId: "CA-01",
        stateCode: "CA",
      }),
    });
    expect(() => powerVoteResponseSchema.parse(payload)).not.toThrow();
    expect(payload.generalOverview).toBeDefined();
    expect(payload.primaries).toBeDefined();
    expect(Array.isArray(payload.generalOverview?.pollingProxy.sources)).toBe(true);
  });

  test("powervote address lookup retries with normalized state-zip punctuation", async () => {
    const rawAddress = "1228 Jerome Street, Brooklyn, New York 11239, United States";
    const normalizedAddress = "1228 Jerome Street, Brooklyn, New York, 11239, United States";
    const geocodeCalls: string[] = [];
    const payload = await buildPowerVoteResponse({
      address: rawAddress,
      office: "us_house",
      geocode: async (address) => {
        geocodeCalls.push(address);
        if (address === rawAddress) {
          return {
            normalizedAddress: null,
            latitude: null,
            longitude: null,
            seatId: null,
            stateCode: null,
          };
        }
        return {
          normalizedAddress,
          latitude: 40.649,
          longitude: -73.872,
          seatId: "NY-08",
          stateCode: "NY",
        };
      },
    });
    expect(() => powerVoteResponseSchema.parse(payload)).not.toThrow();
    expect(geocodeCalls).toEqual([rawAddress, normalizedAddress]);
    expect(payload.address.input).toBe(rawAddress);
    expect(payload.address.normalized).toBe(normalizedAddress);
    expect(payload.address.seatId).toBe("NY-08");
  });

  test("powervote polling proxy keeps summary fields while adding per-source rows", async () => {
    const payload = await buildPowerVoteResponse({
      office: "us_house",
      seatId: "CA-01",
    });
    expect(() => powerVoteResponseSchema.parse(payload)).not.toThrow();
    expect(typeof payload.generalOverview?.pollingProxy.summary).toBe("string");
    expect(payload.generalOverview?.pollingProxy).toHaveProperty("latestDate");
    expect(payload.generalOverview?.pollingProxy).toHaveProperty("leadingParty");
    expect(Array.isArray(payload.generalOverview?.pollingProxy.sources)).toBe(true);
  });

  test("powervote options payload matches schema and sort behavior", async () => {
    const payload = await buildPowerVoteSeatOptionsResponse({
      office: "us_house",
    });
    expect(() => powerVoteSeatOptionsResponseSchema.parse(payload)).not.toThrow();
    expect(payload.states.length).toBeGreaterThan(0);
    expect(payload.states[0].stateCode <= payload.states[payload.states.length - 1].stateCode).toBe(true);
    const ak = payload.states.find((state) => state.stateCode === "AK");
    expect(ak?.seats[0]?.seatLabel).toBe("AL");
  });

  test("powervote payload supports seat_id lookup and seat precedence over address", async () => {
    const payload = await buildPowerVoteResponse({
      office: "us_house",
      seatId: "ca-1",
      address: "Ignored Address",
      geocode: async () => {
        throw new Error("geocode should not be called when seat_id is provided");
      },
    });
    expect(() => powerVoteResponseSchema.parse(payload)).not.toThrow();
    expect(payload.address.seatId).toBe("CA-01");
    expect(payload.generalOverview).toBeDefined();
    expect(Array.isArray(payload.primaries)).toBe(true);
  });

  test("powervote compare payload matches schema", async () => {
    const payload = await buildPowerVoteCompareResponse({
      office: "us_house",
      addresses: ["Address One", "Address Two"],
      geocode: async () => ({
        normalizedAddress: "Mock Address",
        latitude: 34.05,
        longitude: -118.24,
        seatId: "CA-34",
        stateCode: "CA",
      }),
    });
    expect(() => powerVoteCompareResponseSchema.parse(payload)).not.toThrow();
    expect(payload.results.length).toBe(2);
  });

  test("powervote compare supports seatIds for 2-3 seat side-by-side", async () => {
    const payload = await buildPowerVoteCompareResponse({
      office: "us_house",
      seatIds: ["CA-01", "CA-02", "AK-AL"],
    });
    expect(() => powerVoteCompareResponseSchema.parse(payload)).not.toThrow();
    expect(payload.results.length).toBe(3);
    expect(payload.results[0].address.seatId).toBe("CA-01");
    expect(payload.results[1].address.seatId).toBe("CA-02");
    expect(payload.results[2].address.seatId).toBe("AK-AL");
  });

  test("powervote compare rejects duplicate seatIds", async () => {
    await expect(
      buildPowerVoteCompareResponse({
        office: "us_house",
        seatIds: ["CA-01", "CA-01"],
      }),
    ).rejects.toThrow(/duplicate/i);
  });

  test("senate map payload matches schema and uses statewide mode", async () => {
    const payload = await buildMapDistrictsResponse({
      office: "us_senate",
      electionView: "general",
      colorMode: "targeting",
    });
    expect(() => mapDistrictsResponseSchema.parse(payload)).not.toThrow();
    expect(payload.mapMode).toBe("statewide");
    expect(payload.districts.some((row) => row.seatId === "OH-SEN-C3-SPL")).toBe(true);
  });

  test("senate powervote address lookup fails when state has multiple contests and seat_id is omitted", async () => {
    await expect(
      buildPowerVoteResponse({
        office: "us_senate",
        address: "Columbus, OH",
        geocode: async () => ({
          normalizedAddress: "Columbus, OH",
          latitude: 39.96,
          longitude: -83.0,
          seatId: null,
          stateCode: "OH",
        }),
      }),
    ).rejects.toThrow(/multiple senate contests/i);
  });

  test("senate powervote supports explicit senate seat_id", async () => {
    const payload = await buildPowerVoteResponse({
      office: "us_senate",
      seatId: "oh-sen-c3-spl",
    });
    expect(() => powerVoteResponseSchema.parse(payload)).not.toThrow();
    expect(payload.address.seatId).toBe("OH-SEN-C3-SPL");
  });

  test("powervote all response supports house seat input", async () => {
    const payload = await buildPowerVoteAllResponse({ seatId: "OH-01" });
    expect(() => powerVoteAllResponseSchema.parse(payload)).not.toThrow();
    expect(payload.locations.length).toBe(1);
    expect(payload.locations[0].resolvedContext.houseSeatId).toBe("OH-01");
    expect(payload.locations[0].resolvedContext.senateSeatIds.length).toBeGreaterThanOrEqual(0);
  });

  test("powervote all response supports house seat input when state has no senate race", async () => {
    const seatId = await findHouseSeatWithNoSenateRace();
    const payload = await buildPowerVoteAllResponse({ seatId });
    expect(() => powerVoteAllResponseSchema.parse(payload)).not.toThrow();
    expect(payload.locations.length).toBe(1);
    expect(payload.locations[0].resolvedContext.houseSeatId).toBe(seatId);
    expect(payload.locations[0].resolvedContext.senateSeatIds).toEqual([]);
    expect(payload.locations[0].senate).toEqual([]);
    expect(payload.locations[0].elections.every((entry) => entry.office !== "us_senate")).toBe(true);
  });

  test("powervote all response supports senate seat input", async () => {
    const payload = await buildPowerVoteAllResponse({ seatId: "OH-SEN-C3-SPL" });
    expect(() => powerVoteAllResponseSchema.parse(payload)).not.toThrow();
    expect(payload.locations[0].resolvedContext.stateCode).toBe("OH");
    expect(payload.locations[0].senate.some((row) => row.address.seatId === "OH-SEN-C3-SPL")).toBe(true);
  });

  test("powervote all response supports compare seat input", async () => {
    const payload = await buildPowerVoteAllResponse({
      seatId: "OH-01",
      compareSeatId: "OH-02",
    });
    expect(() => powerVoteAllResponseSchema.parse(payload)).not.toThrow();
    expect(payload.locations.length).toBe(2);
  });

  test("powervote all response supports zipcode input", async () => {
    const payload = await buildPowerVoteAllResponse({
      zipcode: "90210",
      compareZipcode: "10001",
    });
    expect(() => powerVoteAllResponseSchema.parse(payload)).not.toThrow();
    expect(payload.locations.length).toBe(2);
  });
});
