import { describe, expect, test } from "vitest";

import { assertRequiredColumns, isHouseSeatId, isSenateSeatId, normalizeSeatId, parseBooleanText, parseCsvText } from "@/lib/server/csv";

describe("csv validation", () => {
  test("normalizes seat ids consistently", () => {
    expect(normalizeSeatId("tx-1")).toBe("TX-01");
    expect(normalizeSeatId("AK-AL")).toBe("AK-AL");
    expect(normalizeSeatId("oh-sen-c3-spl")).toBe("OH-SEN-C3-SPL");
    expect(isHouseSeatId("TX-01")).toBe(true);
    expect(isSenateSeatId("OH-SEN-C3-SPL")).toBe(true);
  });

  test("validates required columns", () => {
    const rows = parseCsvText("seat,district\nTX-01,1\n");
    expect(() => assertRequiredColumns(rows, ["seat", "district"], "fixture.csv")).not.toThrow();
    expect(() => assertRequiredColumns(rows, ["seat", "missing"], "fixture.csv")).toThrow(/missing required columns/i);
  });

  test("parses booleans from canonical rollup text", () => {
    expect(parseBooleanText("True")).toBe(true);
    expect(parseBooleanText("False")).toBe(false);
    expect(parseBooleanText("1")).toBe(true);
  });
});
