import { describe, expect, test } from "vitest";

import { buildStateSeatOptions, normalizeRequestedSeatId } from "@/lib/server/powervote-seat-options";

describe("powervote seat options", () => {
  test("deduplicates and sorts seats by AL then numeric", () => {
    const options = buildStateSeatOptions([
      { seat: "CA-12" },
      { seat: "CA-1" },
      { seat: "AK-AL" },
      { seat: "CA-01" },
      { seat: "AK-AL" },
      { seat: "CA-02" },
    ] as any);

    const ak = options.find((state) => state.stateCode === "AK");
    const ca = options.find((state) => state.stateCode === "CA");
    expect(ak?.seats.map((seat) => seat.seatLabel)).toEqual(["AL"]);
    expect(ca?.seats.map((seat) => seat.seatLabel)).toEqual(["01", "02", "12"]);
  });

  test("normalizes seat input and rejects invalid values", () => {
    expect(normalizeRequestedSeatId("ca-1")).toBe("CA-01");
    expect(normalizeRequestedSeatId("oh-sen-c3-spl")).toBe("OH-SEN-C3-SPL");
    expect(() => normalizeRequestedSeatId("california-1")).toThrow(/invalid seat_id/i);
  });
});
