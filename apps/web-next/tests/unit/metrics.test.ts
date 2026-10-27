import { describe, expect, test } from "vitest";

import {
  computeMarketCompetitiveness,
  computeWeightedCompetitiveness,
  getPrimaryKalshiMarketKey,
  getPollingProxyMapKey,
  getMarketFavoriteParty,
  getPrimaryState,
  getTargetingKey,
  scoreBand,
} from "@/lib/server/metrics";

describe("metrics", () => {
  test("computes market favorite party from odds map", () => {
    const odds = JSON.stringify({ "Democratic party": 48.1, "Republican party": 51.2 });
    expect(getMarketFavoriteParty(odds)).toBe("REP");
  });

  test("computes market competitiveness from top-two spread", () => {
    const odds = JSON.stringify({ "Democratic party": 49.5, "Republican party": 50.5 });
    expect(computeMarketCompetitiveness(odds)).toBe(99);
  });

  test("derives primary state with runoff precedence", () => {
    const primaryRows = [{ status: "upcoming" }, { status: "complete" }] as any;
    const runoffRows = [{ status: "runoff" }] as any;
    expect(getPrimaryState(primaryRows, runoffRows)).toBe("ongoing_runoff");
  });

  test("weighted competitiveness keeps deterministic fallback behavior", () => {
    const generalRow = {
      kalshi_general_odds_map: JSON.stringify({ "Democratic party": 45, "Republican party": 55 }),
      general_election_race_ratings: JSON.stringify({
        outlet_ratings: [{ rating: "Lean Republican" }, { rating: "Likely Republican" }],
      }),
      dccc_target: "False",
      nrcc_target: "True",
    } as any;
    const score = computeWeightedCompetitiveness(generalRow);
    expect(score.score).not.toBeNull();
    expect(score.breakdown.market.weight).toBe(0.6);
    expect(score.breakdown.pollingProxy.weight).toBe(0.25);
    expect(score.breakdown.targeting.weight).toBe(0.15);
  });

  test("targeting key and score band are stable", () => {
    expect(getTargetingKey({ dccc_target: "True", nrcc_target: "False" } as any)).toBe("dccc");
    expect(getTargetingKey({ dccc_target: "True", nrcc_target: "False", dscc_target: "False", nrsc_target: "False" } as any)).toBe("dccc");
    expect(getTargetingKey({ dccc_target: "False", nrcc_target: "True", dscc_target: "False", nrsc_target: "False" } as any)).toBe("nrcc");
    expect(getTargetingKey({ dccc_target: "False", nrcc_target: "False", dscc_target: "True", nrsc_target: "False" } as any)).toBe("dccc");
    expect(getTargetingKey({ dccc_target: "False", nrcc_target: "False", dscc_target: "False", nrsc_target: "True" } as any)).toBe("nrcc");
    expect(scoreBand(80)).toBe("Toss-up");
    expect(scoreBand(52)).toBe("Lean");
    expect(scoreBand(null)).toBe("Unknown");
  });

  test("detects toss-up polling proxy key when no party lead is explicit", () => {
    const ratings = JSON.stringify({
      outlet_ratings: [{ rating: "Toss-up" }, { rating: "Toss-up" }],
    });
    expect(getPollingProxyMapKey(ratings, null)).toBe("poll_tossup");
  });

  test("derives primary kalshi market key by party-lane availability", () => {
    expect(getPrimaryKalshiMarketKey({ kalshi_primary_d: "{}", kalshi_primary_r: "{}" } as any)).toBe("none");
    expect(
      getPrimaryKalshiMarketKey({
        kalshi_primary_d: '{"contestId":"US-REP:AL-01:2026:D"}',
        kalshi_primary_r: "{}",
      } as any),
    ).toBe("dem");
    expect(
      getPrimaryKalshiMarketKey({
        kalshi_primary_d: "{}",
        kalshi_primary_r: '{"contestId":"US-REP:AL-01:2026:R"}',
      } as any),
    ).toBe("rep");
    expect(
      getPrimaryKalshiMarketKey({
        kalshi_primary_d: '{"contestId":"US-REP:AL-01:2026:D"}',
        kalshi_primary_r: '{"contestId":"US-REP:AL-01:2026:R"}',
      } as any),
    ).toBe("both");
  });
});
