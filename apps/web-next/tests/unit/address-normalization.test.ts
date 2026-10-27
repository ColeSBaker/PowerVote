import { describe, expect, test } from "vitest";

import { normalizeAddressForGeocoder } from "@/lib/server/address-normalization";

describe("normalizeAddressForGeocoder", () => {
  test("inserts comma between state and zip when missing", () => {
    const result = normalizeAddressForGeocoder(
      "1228 Jerome Street, Brooklyn, New York 11239, United States",
    );
    expect(result.rawAddress).toBe("1228 Jerome Street, Brooklyn, New York 11239, United States");
    expect(result.normalizedForGeocoder).toBe(
      "1228 Jerome Street, Brooklyn, New York, 11239, United States",
    );
    expect(result.changed).toBe(true);
  });

  test("keeps already valid state-zip comma format unchanged", () => {
    const result = normalizeAddressForGeocoder(
      "1228 Jerome Street, Brooklyn, New York, 11239, United States",
    );
    expect(result.normalizedForGeocoder).toBe(
      "1228 Jerome Street, Brooklyn, New York, 11239, United States",
    );
    expect(result.changed).toBe(false);
  });

  test("does not rewrite unrelated free text", () => {
    const result = normalizeAddressForGeocoder("Near New York office building");
    expect(result.normalizedForGeocoder).toBe("Near New York office building");
    expect(result.changed).toBe(false);
  });
});
