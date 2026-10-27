import type { PartyCode } from "@/lib/domain/schemas";
import { parseJsonObject } from "@/lib/server/csv";
import type { CandidateRow, DepartureRow, GeneralRow, PrimaryRow, RunoffRow } from "@/lib/server/data-source";
import { buildDetailEntities } from "@/lib/server/district-detail";
import { parsePartyFromLabel } from "@/lib/server/metrics";

type PrimaryStatusLabel = "No Primary" | "Upcoming" | "In Progress" | "Runoff Active" | "Complete" | "Unknown";

function normalizeTargetingLabel(key: "both" | "dccc" | "nrcc" | "none" | "n_a"): "Both" | "DCCC" | "NRCC" | "None" | "N/A" {
  if (key === "both") return "Both";
  if (key === "dccc") return "DCCC";
  if (key === "nrcc") return "NRCC";
  if (key === "n_a") return "N/A";
  return "None";
}

function statusFromRows(primaryRows: PrimaryRow[], runoffRows: RunoffRow[]): PrimaryStatusLabel {
  const primaryStatuses = primaryRows.map((row) => row.status.toLowerCase().trim()).filter(Boolean);
  const runoffStatuses = runoffRows.map((row) => row.status.toLowerCase().trim()).filter(Boolean);

  if (runoffStatuses.some((status) => status === "runoff" || status.includes("active"))) {
    return "Runoff Active";
  }
  if (primaryStatuses.some((status) => status === "in_progress" || status === "in progress" || status === "active" || status === "ongoing")) {
    return "In Progress";
  }
  if (primaryStatuses.some((status) => status === "upcoming")) {
    return "Upcoming";
  }
  if (primaryStatuses.some((status) => status === "complete")) {
    return "Complete";
  }
  if (!primaryRows.length && !runoffRows.length) {
    return "No Primary";
  }
  return "Unknown";
}

function mergedPrimaryOddsMap(primaryRows: PrimaryRow[]): Record<string, number> {
  const merged = new Map<string, number>();
  for (const row of primaryRows) {
    const oddsMap = parseJsonObject<Record<string, number>>(row.kalshi_primary_odds_map);
    if (!oddsMap) continue;
    for (const [name, odds] of Object.entries(oddsMap)) {
      const value = Number(odds);
      if (!Number.isFinite(value)) continue;
      const current = merged.get(name);
      if (current === undefined || value > current) {
        merged.set(name, value);
      }
    }
  }
  return Object.fromEntries(Array.from(merged.entries()).sort((a, b) => b[1] - a[1]));
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter((value) => value.trim()).map((value) => value.trim())));
}

function parsePrimaryContestMarkets(raw: string | undefined): { marketCount: number; marketTickers: string[]; hasMarket: boolean } {
  const parsed = parseJsonObject<{ contestId?: string; marketCount?: number; marketTickers?: string[] }>(raw);
  if (!parsed) {
    return { marketCount: 0, marketTickers: [], hasMarket: false };
  }
  const marketTickers = Array.isArray(parsed.marketTickers) ? parsed.marketTickers.map((ticker) => String(ticker || "").trim()).filter(Boolean) : [];
  const numericCount = Number(parsed.marketCount);
  const marketCount = Number.isFinite(numericCount) && numericCount > 0 ? Math.trunc(numericCount) : marketTickers.length;
  const hasMarket = Boolean((parsed.contestId || "").trim()) || marketCount > 0 || marketTickers.length > 0;
  return { marketCount, marketTickers, hasMarket };
}

export function buildPowerVoteDescriptiveContext(args: {
  generalRow: GeneralRow;
  primaryRows: PrimaryRow[];
  runoffRows: RunoffRow[];
  candidateRows: CandidateRow[];
  departureRow: DepartureRow | null;
  office?: string;
}) {
  const detail = buildDetailEntities({
    seatId: args.generalRow.seat,
    generalRow: args.generalRow,
    primaryRows: args.primaryRows,
    runoffRows: args.runoffRows,
    candidateRows: args.candidateRows,
    departureRow: args.departureRow,
    office: args.office,
  });

  const primaryParties = detail.primaryElection.parties.map((party) => party.party);
  const primaries = primaryParties.map((party) => {
    const partyPrimaryRows = args.primaryRows.filter((row) => parsePartyFromLabel(row.party) === party);
    const partyRunoffRows = args.runoffRows.filter((row) => parsePartyFromLabel(row.party) === party);
    const status = statusFromRows(partyPrimaryRows, partyRunoffRows);
    const oddsMap = mergedPrimaryOddsMap(partyPrimaryRows);
    const primaryContest = parsePrimaryContestMarkets(party === "DEM" ? args.generalRow.kalshi_primary_d : party === "REP" ? args.generalRow.kalshi_primary_r : "");
    const winner =
      status === "Complete" ? detail.primaryElection.parties.find((entry) => entry.party === party)?.candidates.find((candidate) => candidate.stage === "nominee")?.name ?? null : null;
    const runoffRow = partyRunoffRows.find((row) => row.status.toLowerCase().trim() === "runoff") ?? partyRunoffRows[0];

    const generalLane = detail.generalElection.partyLanes.find((lane) => lane.party === party);

    return {
      party,
      status,
      kalshiPrimary: {
        hasMarket: primaryContest.hasMarket || Object.keys(oddsMap).length > 0,
        marketCount: primaryContest.marketCount,
        marketTickers: primaryContest.marketTickers,
        oddsMap,
      },
      winner,
      details: {
        primaryDate: partyPrimaryRows.find((row) => row.primary_date)?.primary_date || args.generalRow.primary_date || null,
        runoffDate: runoffRow?.runoff_date || args.generalRow.runoff_date || null,
        runoffCandidates: unique([runoffRow?.runoff_candidate_1 ?? "", runoffRow?.runoff_candidate_2 ?? ""]),
        primaryCandidates:
          party === "NP"
            ? unique(detail.generalElection.partyLanes.flatMap((lane) => lane.primaryCandidates))
            : generalLane?.primaryCandidates ?? [],
        rawStatuses: unique([...partyPrimaryRows.map((row) => row.status), ...partyRunoffRows.map((row) => row.status)]),
      },
    };
  });

  return {
    generalOverview: {
      controllingParty: detail.incumbencyAndControl.controllingParty,
      incumbentIndividual: detail.incumbencyAndControl.incumbentIndividual,
      isOpen: detail.incumbencyAndControl.openSeat,
      departureReason: detail.incumbencyAndControl.departureReason,
      kalshiGeneral: {
        hasMarket: Object.keys(detail.competitiveness.kalshiGeneralOdds.oddsMap).length > 0,
        favoriteParty: detail.competitiveness.kalshiGeneralOdds.favoriteParty,
        favoriteLabel: detail.competitiveness.kalshiGeneralOdds.favoriteLabel,
        oddsMap: detail.competitiveness.kalshiGeneralOdds.oddsMap,
      },
      pollingProxy: {
        summary: detail.competitiveness.pollingStatus.summary,
        latestDate: detail.competitiveness.pollingStatus.latestDate,
        leadingParty: detail.competitiveness.pollingStatus.leadingParty,
        sources: detail.competitiveness.pollingStatus.sources,
      },
      targeting: {
        key: detail.competitiveness.targeting.key,
        label: normalizeTargetingLabel(detail.competitiveness.targeting.key),
        dcccTarget: detail.competitiveness.targeting.dcccTarget,
        nrccTarget: detail.competitiveness.targeting.nrccTarget,
      },
    },
    primaries: primaries as Array<{
      party: PartyCode;
      status: PrimaryStatusLabel;
      kalshiPrimary: { hasMarket: boolean; marketCount: number; marketTickers: string[]; oddsMap: Record<string, number> };
      winner: string | null;
      details: { primaryDate: string | null; runoffDate: string | null; runoffCandidates: string[]; primaryCandidates: string[]; rawStatuses: string[] };
    }>,
  };
}
