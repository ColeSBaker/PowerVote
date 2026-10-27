import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import { validateZipcodeFormat, lookupZipcode, type ZipcodeResult } from "@/lib/server/zipcode-lookup";
import * as dataSource from "@/lib/server/data-source";
import * as geo from "@/lib/server/geo";
import * as zipcodesCentroids from "@/lib/server/zipcode-centroids-generated";

describe("validateZipcodeFormat", () => {
  it("accepts valid 5-digit zipcode", () => {
    expect(validateZipcodeFormat("90210")).toBe(true);
    expect(validateZipcodeFormat("10001")).toBe(true);
    expect(validateZipcodeFormat("00501")).toBe(true);
  });

  it("accepts valid 9-digit zipcode (with +4)", () => {
    expect(validateZipcodeFormat("90210-1234")).toBe(true);
    expect(validateZipcodeFormat("10001-0001")).toBe(true);
  });

  it("rejects invalid formats", () => {
    expect(validateZipcodeFormat("9021")).toBe(false);
    expect(validateZipcodeFormat("902100")).toBe(false);
    expect(validateZipcodeFormat("9021a")).toBe(false);
    expect(validateZipcodeFormat("90210-123")).toBe(false);
    expect(validateZipcodeFormat("90210-12345")).toBe(false);
    expect(validateZipcodeFormat("")).toBe(false);
    expect(validateZipcodeFormat("   ")).toBe(false);
  });

  it("trims whitespace before validating", () => {
    expect(validateZipcodeFormat("  90210  ")).toBe(true);
    expect(validateZipcodeFormat("\t90210\n")).toBe(true);
  });
});

describe("lookupZipcode", () => {
  beforeAll(() => {
    // Mock centroid lookup to return Beverly Hills coordinates
    vi.spyOn(zipcodesCentroids, "getZipcodeCentroid").mockReturnValue({
      latitude: 34.0901,
      longitude: -118.4065,
    });

    const houseBundleStub = {
      office: "us_house" as const,
      mapMode: "district" as const,
      snapshotDate: "2026-04-02",
      updatedAt: "2026-04-02T00:00:00Z",
      sourceAttribution: [],
      generalRows: [],
      primaryRows: [],
      runoffRows: [],
      departureRows: [],
      candidateRows: [],
      geometryGeoJson: { type: "FeatureCollection", features: [] },
    };

    const senateBundleStub = {
      ...houseBundleStub,
      office: "us_senate" as const,
      generalRows: [
        { seat: "CA-SEN-A", district: "A" } as any,
        { seat: "CA-SEN-B", district: "B" } as any,
      ],
    };

    vi.spyOn(dataSource, "loadCanonicalDataBundleByOffice").mockImplementation(
      (office) =>
        Promise.resolve(
          office === "us_house" ? houseBundleStub : senateBundleStub
        )
    );

    vi.spyOn(geo, "asFeatureCollection").mockReturnValue({
      type: "FeatureCollection",
      features: [],
    } as any);

    vi.spyOn(geo, "findSeatByPoint").mockReturnValue("CA-35");
  });

  afterAll(() => {
    vi.restoreAllMocks();
  });

  it("maps zipcode to district and senate seats via centroid", async () => {
    const result = await lookupZipcode("90210");

    expect(result).toEqual({
      zipcode: "90210",
      state: "CA",
      houseDistrict: "CA-35",
      senateSeats: ["CA-SEN-A", "CA-SEN-B"],
      normalizedAddress: null,
      latitude: 34.0901,
      longitude: -118.4065,
    });
  });

  it("handles zipcode with +4 format", async () => {
    const result = await lookupZipcode("90210-1234");
    expect(result.zipcode).toBe("90210-1234");
  });

  it("returns empty senateSeats for states with no Senate races", async () => {
    vi.spyOn(dataSource, "loadCanonicalDataBundleByOffice").mockImplementation(
      (office) => {
        if (office === "us_house") {
          return Promise.resolve({
            office: "us_house",
            mapMode: "district" as const,
            snapshotDate: "2026-04-02",
            updatedAt: "2026-04-02T00:00:00Z",
            sourceAttribution: [],
            generalRows: [],
            primaryRows: [],
            runoffRows: [],
            departureRows: [],
            candidateRows: [],
            geometryGeoJson: { type: "FeatureCollection", features: [] },
          } as any);
        }
        return Promise.resolve({
          office: "us_senate",
          mapMode: "district",
          snapshotDate: "2026-04-02",
          updatedAt: "2026-04-02T00:00:00Z",
          sourceAttribution: [],
          generalRows: [],
          primaryRows: [],
          runoffRows: [],
          departureRows: [],
          candidateRows: [],
          geometryGeoJson: { type: "FeatureCollection", features: [] },
        } as any);
      }
    );

    const result = await lookupZipcode("90210");
    expect(result.senateSeats).toEqual([]);
  });

  it("throws error for invalid zipcode format", async () => {
    await expect(lookupZipcode("9021")).rejects.toThrow(
      'Invalid zipcode format: "9021". Expected format: 12345 or 12345-6789'
    );
  });

  it("throws error when zipcode not in centroid database", async () => {
    vi.spyOn(zipcodesCentroids, "getZipcodeCentroid").mockReturnValueOnce(null as any);

    await expect(lookupZipcode("00000")).rejects.toThrow(
      "Cannot determine location for zipcode 00000"
    );
  });

  it("throws error on point-in-polygon lookup failure", async () => {
    vi.spyOn(geo, "findSeatByPoint").mockImplementationOnce(() => {
      throw new Error("Geometry lookup failed");
    });

    await expect(lookupZipcode("90210")).rejects.toThrow(
      "Failed to determine congressional district"
    );
  });

  it("throws error when centroid doesn't fall in any district", async () => {
    vi.spyOn(geo, "findSeatByPoint").mockReturnValueOnce(null);

    await expect(lookupZipcode("90210")).rejects.toThrow(
      "does not fall within any congressional district"
    );
  });

  it("throws error on Senate bundle loading failure", async () => {
    vi.spyOn(dataSource, "loadCanonicalDataBundleByOffice").mockImplementation(
      (office) => {
        if (office === "us_house") {
          return Promise.resolve({
            office: "us_house",
            mapMode: "district" as const,
            snapshotDate: "2026-04-02",
            updatedAt: "2026-04-02T00:00:00Z",
            sourceAttribution: [],
            generalRows: [],
            primaryRows: [],
            runoffRows: [],
            departureRows: [],
            candidateRows: [],
            geometryGeoJson: { type: "FeatureCollection", features: [] },
          } as any);
        }
        throw new Error("Senate bundle failed");
      }
    );

    await expect(lookupZipcode("90210")).rejects.toThrow(
      "Failed to load Senate data for state CA"
    );
  });
});
