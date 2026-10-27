import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import { GET } from "@/app/api/v1/zipcode-lookup/route";
import * as zipcodeModule from "@/lib/server/zipcode-lookup";
import { ClientInputError } from "@/lib/server/errors";

describe("GET /api/v1/zipcode-lookup", () => {
  beforeAll(() => {
    vi.spyOn(zipcodeModule, "lookupZipcode").mockResolvedValue({
      zipcode: "90210",
      state: "CA",
      houseDistrict: "CA-35",
      senateSeats: ["CA-SEN-A", "CA-SEN-B"],
      normalizedAddress: "Beverly Hills, California 90210",
      latitude: 34.0901,
      longitude: -118.4065,
    });
  });

  afterAll(() => {
    vi.restoreAllMocks();
  });

  it("returns 200 with zipcode result", async () => {
    const request = new Request(
      "http://localhost:3000/api/v1/zipcode-lookup?zipcode=90210"
    );
    const response = await GET(request);

    expect(response.status).toBe(200);
    const json = await response.json();
    expect(json).toEqual({
      zipcode: "90210",
      state: "CA",
      houseDistrict: "CA-35",
      senateSeats: ["CA-SEN-A", "CA-SEN-B"],
      normalizedAddress: "Beverly Hills, California 90210",
      latitude: 34.0901,
      longitude: -118.4065,
    });
  });

  it("returns 400 when zipcode parameter is missing", async () => {
    const request = new Request(
      "http://localhost:3000/api/v1/zipcode-lookup"
    );
    const response = await GET(request);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toContain('Missing required query parameter: "zipcode"');
  });

  it("returns 400 when zipcode lookup fails", async () => {
    vi.spyOn(zipcodeModule, "lookupZipcode").mockRejectedValueOnce(
      new ClientInputError("Invalid zipcode format")
    );

    const request = new Request(
      "http://localhost:3000/api/v1/zipcode-lookup?zipcode=invalid"
    );
    const response = await GET(request);

    expect(response.status).toBe(400);
    const json = await response.json();
    expect(json.error).toContain("Invalid zipcode format");
  });

  it("handles empty zipcode parameter", async () => {
    const request = new Request(
      "http://localhost:3000/api/v1/zipcode-lookup?zipcode="
    );
    const response = await GET(request);

    expect(response.status).toBe(400);
  });

  it("passes zipcode to lookupZipcode function", async () => {
    const spy = vi.spyOn(zipcodeModule, "lookupZipcode");
    const request = new Request(
      "http://localhost:3000/api/v1/zipcode-lookup?zipcode=10001"
    );
    await GET(request);

    expect(spy).toHaveBeenCalledWith("10001");
  });

  it("handles various valid zipcode formats", async () => {
    const testCases = ["90210", "10001", "00501", "90210-1234"];
    
    for (const zipcode of testCases) {
      const request = new Request(
        `http://localhost:3000/api/v1/zipcode-lookup?zipcode=${zipcode}`
      );
      const response = await GET(request);
      expect(response.status).toBe(200);
    }
  });
});
