import { describe, expect, test } from "vitest";

import { buildPowerVoteDescriptiveContext } from "@/lib/server/powervote-descriptive";

describe("powervote descriptive formatter", () => {
  test("builds general overview with open-seat and targeting labels", () => {
    const context = buildPowerVoteDescriptiveContext({
      generalRow: {
        seat: "CA-11",
        district: "11",
        general_status: "contested",
        incumbent_party: "D",
        incumbent_name: "Incumbent Name",
        incumbent_status: "retiring",
        kalshi_general_odds_map: '{"Democratic party": 64, "Republican party": 36}',
        general_election_race_ratings:
          '{"most_recent_poll_date":"3/17/2026","outlet_ratings":[{"outlet":"Cook","rating":"Toss-up","date":"3/17/2026"},{"outlet":"Inside Elections","rating":"Lean Republican"},{"outlet":"","rating":"Likely Democratic"},{"outlet":"Pending Outlet","rating":"Pending"}]}',
        dccc_target: "True",
        nrcc_target: "False",
        primary_status_d: "upcoming",
        primary_status_r: "complete",
        nominee_d: "",
        nominee_r: "Rep Nominee",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-06-02",
        runoff_date: "",
      } as any,
      primaryRows: [] as any,
      runoffRows: [] as any,
      candidateRows: [] as any,
      departureRow: null,
    });

    expect(context.generalOverview.targeting.label).toBe("DCCC");
    expect(context.generalOverview.isOpen).toBe(true);
    expect(context.generalOverview.kalshiGeneral.hasMarket).toBe(true);
    expect(context.generalOverview.pollingProxy.sources).toEqual([
      { outlet: "Cook", rating: "Toss-up", date: "3/17/2026" },
      { outlet: "Inside Elections", rating: "Lean Republican", date: null },
      { outlet: "Pending Outlet", rating: "Pending", date: null },
    ]);
  });

  test("primary status precedence and winner fallback behave deterministically", () => {
    const context = buildPowerVoteDescriptiveContext({
      generalRow: {
        seat: "TX-01",
        district: "1",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Name",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "True",
        primary_status_d: "upcoming",
        primary_status_r: "complete",
        nominee_d: "",
        nominee_r: "Nominee R",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-03-03",
        runoff_date: "2026-05-26",
      } as any,
      primaryRows: [
        { party: "D", status: "upcoming", primary_date: "2026-03-03", kalshi_primary_odds_map: "{}" },
        { party: "R", status: "complete", primary_date: "2026-03-03", kalshi_primary_odds_map: '{"Nominee R":60}' },
      ] as any,
      runoffRows: [
        { party: "D", status: "runoff", runoff_candidate_1: "A", runoff_candidate_2: "B", runoff_date: "2026-05-26" },
      ] as any,
      candidateRows: [
        { BallotpediaName: "Nominee R", Party: "R", Status: "general (nominated)", "Primary ID": "x", RunoffID: "", KalshiBestPrimaryOdds: "60" },
      ] as any,
      departureRow: null,
    });

    const dem = context.primaries.find((entry) => entry.party === "DEM");
    const rep = context.primaries.find((entry) => entry.party === "REP");
    expect(dem?.status).toBe("Runoff Active");
    expect(rep?.status).toBe("Complete");
    expect(rep?.winner).toBe("Nominee R");
  });

  test("primary market presence falls back to contest payload when odds map is empty", () => {
    const context = buildPowerVoteDescriptiveContext({
      generalRow: {
        seat: "AL-01",
        district: "1",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Name",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "complete",
        primary_status_r: "upcoming",
        primary_date: "2026-03-03",
        runoff_date: "",
        nominee_d: "Nominee D",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        kalshi_primary_d:
          '{"contestId":"US-REP:AL-01:2026:D","marketCount":2,"marketTickers":["KXAL01D-26-A","KXAL01D-26-B"]}',
        kalshi_primary_r: "{}",
      } as any,
      primaryRows: [{ party: "D", status: "complete", primary_date: "2026-03-03", kalshi_primary_odds_map: "{}" }] as any,
      runoffRows: [] as any,
      candidateRows: [] as any,
      departureRow: null,
    });

    const dem = context.primaries.find((entry) => entry.party === "DEM");
    expect(dem).toBeDefined();
    expect(dem?.kalshiPrimary.hasMarket).toBe(true);
    expect(dem?.kalshiPrimary.marketCount).toBe(2);
    expect(dem?.kalshiPrimary.marketTickers).toEqual(["KXAL01D-26-A", "KXAL01D-26-B"]);
    expect(dem?.kalshiPrimary.oddsMap).toEqual({});
  });

  test("polling source normalization ignores blank outlet/rating values and preserves order", () => {
    const context = buildPowerVoteDescriptiveContext({
      generalRow: {
        seat: "CA-04",
        district: "4",
        general_status: "contested",
        incumbent_party: "D",
        incumbent_name: "Incumbent",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings:
          '{"outlet_ratings":[{"outlet":"A","rating":"Lean Democratic","date":"3/01/2026"},{"outlet":"   ","rating":"Toss-up"},{"outlet":"B","rating":"Likely Democratic"},{"outlet":"C","rating":"  "}]}',
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "none",
        primary_status_r: "none",
        primary_date: "",
        runoff_date: "",
        nominee_d: "",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
      } as any,
      primaryRows: [] as any,
      runoffRows: [] as any,
      candidateRows: [] as any,
      departureRow: null,
    });

    expect(context.generalOverview.pollingProxy.sources).toEqual([
      { outlet: "A", rating: "Lean Democratic", date: "3/01/2026" },
      { outlet: "B", rating: "Likely Democratic", date: null },
    ]);
  });
});
