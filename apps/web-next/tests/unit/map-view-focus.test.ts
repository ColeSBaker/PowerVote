import { describe, expect, test } from "vitest";

import {
  buildFocusFilters,
  deriveSeatOptions,
  deriveStateOptions,
  resolveFocusTarget,
} from "@/lib/client/map-view-focus";

const DISTRICTS = [
  { seatId: "AK-AL", state: "AK", districtLabel: "AK At-Large" },
  { seatId: "HI-01", state: "HI", districtLabel: "HI-01" },
  { seatId: "HI-02", state: "HI", districtLabel: "HI-02" },
  { seatId: "CA-01", state: "CA", districtLabel: "CA-01" },
  { seatId: "CA-02", state: "CA", districtLabel: "CA-02" },
];

describe("map view focus helpers", () => {
  test("derives deterministic state and seat options", () => {
    expect(deriveStateOptions(DISTRICTS)).toEqual(["AK", "CA", "HI"]);
    expect(deriveSeatOptions(DISTRICTS, "HI").map((seat) => seat.seatId)).toEqual(["HI-01", "HI-02"]);
  });

  test("seat selection takes precedence over state", () => {
    const focus = resolveFocusTarget({
      selectedState: "CA",
      selectedSeat: "HI-02",
      districts: DISTRICTS,
    });
    expect(focus).toEqual({ kind: "seat", seatId: "HI-02", stateCode: "HI" });
  });

  test("state focus builds active+dim filters for contiguous map", () => {
    const focus = resolveFocusTarget({ selectedState: "CA", selectedSeat: null, districts: DISTRICTS });
    const filters = buildFocusFilters("contiguous", focus);
    expect(filters.activeFilter).toEqual([
      "all",
      ["all", ["!=", ["get", "state"], "AK"], ["!=", ["get", "state"], "HI"]],
      ["==", ["get", "state"], "CA"],
    ]);
    expect(filters.dimFilter).toEqual([
      "all",
      ["all", ["!=", ["get", "state"], "AK"], ["!=", ["get", "state"], "HI"]],
      ["!=", ["get", "state"], "CA"],
    ]);
  });

  test("all focus uses valid expression filters for empty layers", () => {
    const focus = resolveFocusTarget({ selectedState: null, selectedSeat: null, districts: DISTRICTS });
    const filters = buildFocusFilters("contiguous", focus);
    expect(filters.dimFilter).toEqual(["all", ["!=", ["get", "state"], "AK"], ["!=", ["get", "state"], "HI"]]);
    expect(filters.highlightFilter).toEqual(["==", ["get", "seatId"], "__PV_NO_MATCH__"]);
  });
});
