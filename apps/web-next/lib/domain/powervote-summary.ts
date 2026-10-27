import type { PowerVoteAllResponse } from "./schemas";

export interface PerPartyPrimaryStats {
  total: number;
  competitive: number;
  uncontested: number;
  runoff: number;
}

export interface PowerVoteSummaryStats {
  generalCount: number;
  tossUpCount: number;
  competitiveCount: number;
  leanCount: number;
  safeCount: number;
  primaryCount: number;
  runoffCount: number;
  primaryByParty: Record<string, PerPartyPrimaryStats>;
}

export type PowerVoteLocation = PowerVoteAllResponse["locations"][number];

function allSeats(location: PowerVoteLocation): PowerVoteLocation["house"][] {
  return [
    location.house,
    ...location.senate,
    ...location.governor,
    ...location.lieutenantGovernor,
    ...location.attorneyGeneral,
  ];
}

export function computeLocationSummary(location: PowerVoteLocation): PowerVoteSummaryStats {
  let generalCount = 0;
  let tossUpCount = 0;
  let competitiveCount = 0;
  let leanCount = 0;
  let safeCount = 0;
  let primaryCount = 0;
  let runoffCount = 0;
  const primaryByParty: Record<string, PerPartyPrimaryStats> = {};

  for (const election of location.elections) {
    if (election.electionKind === "general") {
      generalCount++;
      if (election.band === "Toss-up") tossUpCount++;
      else if (election.band === "Competitive") competitiveCount++;
      else if (election.band === "Lean") leanCount++;
      else if (election.band === "Safe") safeCount++;
    } else if (election.electionKind === "primary") {
      primaryCount++;
    } else if (election.electionKind === "runoff") {
      runoffCount++;
    }
  }

  for (const seat of allSeats(location)) {
    for (const primary of seat.primaries ?? []) {
      if (primary.status === "No Primary" || primary.status === "Unknown") continue;
      const p = primary.party;
      if (!primaryByParty[p]) primaryByParty[p] = { total: 0, competitive: 0, uncontested: 0, runoff: 0 };
      primaryByParty[p].total++;
      if (primary.status === "Runoff Active") primaryByParty[p].runoff++;
      if (primary.kalshiPrimary.hasMarket) primaryByParty[p].competitive++;
      else if (primary.details.primaryCandidates.length <= 1) primaryByParty[p].uncontested++;
    }
  }

  return { generalCount, tossUpCount, competitiveCount, leanCount, safeCount, primaryCount, runoffCount, primaryByParty };
}

export function hasCompetitiveRace(stats: PowerVoteSummaryStats): boolean {
  return stats.tossUpCount >= 1 || stats.competitiveCount >= 1 || stats.leanCount > 2;
}
