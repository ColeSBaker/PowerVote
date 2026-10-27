import type { PartyCode } from "@/lib/domain/schemas";
import { parseBooleanText, parseJsonObject, parseNullableNumber, normalizeSeatId } from "@/lib/server/csv";
import type { CandidateRow, DepartureRow, GeneralRow, PrimaryRow, RunoffRow } from "@/lib/server/data-source";
import { getPollingProxyPartyAndScore, getPrimaryState, getTargetingKey, parsePartyFromLabel } from "@/lib/server/metrics";

const BASE_GENERAL_PARTIES: PartyCode[] = ["DEM", "REP"];

type VisibleContext = "general" | "runoff";

type GeneralLane = {
  party: PartyCode;
  hasNominee: boolean;
  nomineeName: string | null;
  primaryOngoing: boolean;
  primaryDate: string | null;
  primaryCandidates: string[];
  runoffOngoing: boolean;
  runoffDate: string | null;
  runoffCandidates: string[];
  visibleCandidates: Array<{ name: string; context: VisibleContext; eliminated: boolean; odds: number | null }>;
};

type PrimaryCandidate = {
  name: string;
  status: string;
  stage: "runoff" | "nominee" | "candidate" | "general";
  odds: number | null;
  eliminated: boolean;
  kalshiMarketUrl: string | null;
};

type UnifiedCandidate = {
  name: string;
  stage: "nominee" | "runoff" | "candidate" | "general";
  primaryOdds: number | null;
  generalOdds: number | null;
  eliminated: boolean;
  nameUnmatched: boolean;
  partyAffiliation: string | null;
};

function partyAffiliationTag(partyCode: string): string | null {
  switch (partyCode.toUpperCase()) {
    case "DEM": return "D";
    case "REP": return "R";
    case "NPA": return "I";
    case "GRE": return "G";
    case "LIB": return "L";
    case "OTH": return "O";
    default: return null;
  }
}

const PARTY_LABELS: Record<PartyCode, string> = {
  DEM: "Democratic party",
  REP: "Republican party",
  IND: "Independent",
  LIB: "Libertarian",
  GRE: "Green",
  OTH: "Other",
  NP: "Non-Partisan Primary",
};

function normalizePartyFromNomineeColumn(column: string): PartyCode | null {
  if (column === "nominee_d") return "DEM";
  if (column === "nominee_r") return "REP";
  if (column === "nominee_green") return "GRE";
  if (column === "nominee_libertarian") return "LIB";
  return null;
}

function nomineeNameForParty(generalRow: GeneralRow, party: PartyCode): string | null {
  if (party === "DEM") return generalRow.nominee_d || null;
  if (party === "REP") return generalRow.nominee_r || null;
  if (party === "GRE") return generalRow.nominee_green || null;
  if (party === "LIB") return generalRow.nominee_libertarian || null;
  return null;
}

function isPrimaryStatusOngoing(status: string): boolean {
  const normalized = status.trim().toLowerCase();
  return normalized === "upcoming" || normalized === "runoff";
}

function partyStatusInGeneralRow(generalRow: GeneralRow, party: PartyCode): string {
  const npStatus = generalRow.primary_status_np ?? "";
  if (party === "DEM") {
    const dStatus = generalRow.primary_status_d ?? "";
    return dStatus && dStatus !== "none" ? dStatus : npStatus;
  }
  if (party === "REP") {
    const rStatus = generalRow.primary_status_r ?? "";
    return rStatus && rStatus !== "none" ? rStatus : npStatus;
  }
  return npStatus;
}

function runoffByParty(runoffRows: RunoffRow[]): Map<PartyCode, RunoffRow[]> {
  const map = new Map<PartyCode, RunoffRow[]>();
  for (const row of runoffRows) {
    const party = parsePartyFromLabel(row.party);
    if (!party) continue;
    if (!map.has(party)) map.set(party, []);
    map.get(party)!.push(row);
  }
  return map;
}

function primaryByParty(primaryRows: PrimaryRow[]): Map<PartyCode, PrimaryRow[]> {
  const map = new Map<PartyCode, PrimaryRow[]>();
  for (const row of primaryRows) {
    const party = parsePartyFromLabel(row.party);
    if (!party) continue;
    if (!map.has(party)) map.set(party, []);
    map.get(party)!.push(row);
  }
  return map;
}

function candidateByParty(candidateRows: CandidateRow[]): Map<PartyCode, CandidateRow[]> {
  const map = new Map<PartyCode, CandidateRow[]>();
  for (const row of candidateRows) {
    const party = parsePartyFromLabel(row.Party);
    if (!party) continue;
    if (!map.has(party)) map.set(party, []);
    map.get(party)!.push(row);
  }
  return map;
}

function uniqueOrdered(values: string[]): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const value of values) {
    const trimmed = value.trim();
    if (!trimmed) continue;
    if (seen.has(trimmed.toLowerCase())) continue;
    seen.add(trimmed.toLowerCase());
    ordered.push(trimmed);
  }
  return ordered;
}

function parsePrimaryOddsFromRow(candidate: CandidateRow): number | null {
  return parseNullableNumber(candidate.KalshiBestPrimaryOdds);
}

function extractBestPrimaryMarketUrl(candidate: CandidateRow): string | null {
  const raw = candidate.KalshiPrimaryMarkets?.trim();
  if (!raw) return null;
  try {
    const markets = JSON.parse(raw) as Array<{ marketTicker?: string; oddsPercent?: number }>;
    if (!markets.length) return null;
    const bestOdds = parsePrimaryOddsFromRow(candidate);
    const match =
      bestOdds != null
        ? markets.find((m) => Math.abs((m.oddsPercent ?? -1) - bestOdds) < 0.1)
        : null;
    const ticker = (match ?? markets[0])?.marketTicker;
    return ticker ? `https://kalshi.com/markets/${ticker}` : null;
  } catch {
    return null;
  }
}

function parseOddsMap(raw: string): Record<string, number> {
  const parsed = parseJsonObject<Record<string, number>>(raw) ?? {};
  const output: Record<string, number> = {};
  for (const [key, value] of Object.entries(parsed)) {
    const asNumber = Number(value);
    if (Number.isFinite(asNumber)) {
      output[key] = asNumber;
    }
  }
  return output;
}

function normalizeName(value: string): string {
  // Split camelCase compounds before lowercasing ("WalkingChild" → "Walking Child")
  const expanded = value.replace(/([a-z])([A-Z])/g, "$1 $2");
  const base = expanded
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  // Strip middle initials: single-letter tokens between longer words
  // e.g. "janet t mills" → "janet mills", "charles a walking child" → "charles walking child"
  const tokens = base.split(" ");
  if (tokens.length > 2) {
    const filtered = tokens.filter(
      (token, i) => token.length > 1 || i === 0 || i === tokens.length - 1,
    );
    return filtered.join(" ");
  }
  return base;
}

/**
 * Resolves the market-favorite party from a general-election odds map.
 *
 * Accepts either a pre-parsed `Record<string, number>` or the raw JSON string
 * from the CSV (matching `getMarketFavoriteParty`'s call sites in api-service.ts).
 *
 * Falls back beyond `parsePartyFromLabel` to nominee-name matching when the
 * top-odds key is a candidate name (e.g. "James Talarico": 42) rather than a
 * party label (e.g. "Democratic party": 42).
 */
export function resolveMarketFavoriteParty(
  rawOrParsed: string | Record<string, number>,
  generalRow: GeneralRow,
): PartyCode | null {
  const oddsMap =
    typeof rawOrParsed === "string" ? parseOddsMap(rawOrParsed) : rawOrParsed;
  const entries = Object.entries(oddsMap)
    .map(([key, value]) => ({ key, value: Number(value) }))
    .filter((entry) => Number.isFinite(entry.value));
  if (!entries.length) return null;
  entries.sort((a, b) => b.value - a.value);
  const topKey = entries[0].key;
  // Fast path: key is already a recognisable party label
  const fromLabel = parsePartyFromLabel(topKey);
  if (fromLabel) return fromLabel;
  // Slow path: key is a nominee name — match against known nominee columns
  const topNorm = normalizeName(topKey);
  if (generalRow.nominee_d && normalizeName(generalRow.nominee_d) === topNorm) return "DEM";
  if (generalRow.nominee_r && normalizeName(generalRow.nominee_r) === topNorm) return "REP";
  if (generalRow.nominee_green && normalizeName(generalRow.nominee_green) === topNorm) return "GRE";
  if (generalRow.nominee_libertarian && normalizeName(generalRow.nominee_libertarian) === topNorm) return "LIB";
  return null;
}

function partyOddsLabels(party: PartyCode): string[] {
  // "Democratic (DFL) party" is Minnesota's official label — normalizeName produces "democratic dfl party"
  if (party === "DEM") return ["democratic party", "democratic dfl party", "democratic", "democrat", "dem", "dfl"];
  if (party === "REP") return ["republican party", "republican", "gop", "rep"];
  if (party === "GRE") return ["green party", "green", "gre"];
  if (party === "LIB") return ["libertarian party", "libertarian", "lib"];
  if (party === "IND") return ["independent", "ind"];
  return [party.toLowerCase()];
}

function partyOddsForLane(party: PartyCode, oddsMap: Record<string, number>): number | null {
  const normalized = new Map<string, number>();
  for (const [label, odds] of Object.entries(oddsMap)) {
    normalized.set(normalizeName(label), odds);
  }
  for (const label of partyOddsLabels(party)) {
    const found = normalized.get(normalizeName(label));
    if (typeof found === "number") return found;
  }
  return null;
}

function candidateOddsForLane(name: string, oddsMap: Record<string, number>): number | null {
  const target = normalizeName(name);
  if (!target) return null;
  for (const [label, odds] of Object.entries(oddsMap)) {
    if (normalizeName(label) === target) {
      return odds;
    }
  }
  return null;
}

const PRIMARY_CANDIDATES_CAP = 6;

const PARTY_LABEL_PATTERNS = /\bparty\b|democratic|republican|libertarian|green|independent|\bdem\b|\brep\b|\bnp\b/i;

function derivePrimaryCandidateNames(args: {
  primaryOngoing: boolean;
  hasRunoff: boolean;
  hasNominee: boolean;
  candidateRows: CandidateRow[];
  primaryRows: PrimaryRow[];
}): string[] {
  if (!args.primaryOngoing || args.hasRunoff || args.hasNominee) return [];

  const oddsFromRows = new Map<string, number>();
  for (const row of args.primaryRows) {
    const parsed = parseOddsMap(row.kalshi_primary_odds_map);
    for (const [name, odds] of Object.entries(parsed)) {
      const trimmed = name.trim();
      if (!trimmed) continue;
      const existing = oddsFromRows.get(trimmed.toLowerCase());
      if (existing === undefined || odds > existing) {
        oddsFromRows.set(trimmed.toLowerCase(), odds);
      }
    }
  }

  const seen = new Set<string>();
  const candidates: Array<{ name: string; odds: number | null }> = [];

  for (const row of args.candidateRows) {
    const name = row.BallotpediaName?.trim();
    if (!name) continue;
    const status = row.Status.toLowerCase();
    if (!row["Primary ID"] && !status.includes("primary")) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);

    const rowOdds = parsePrimaryOddsFromRow(row);
    const mapOdds = oddsFromRows.get(key) ?? null;
    const odds = rowOdds ?? mapOdds;
    candidates.push({ name, odds: odds !== null && Number.isFinite(odds) ? odds : null });
  }

  candidates.sort((a, b) => {
    if (a.odds !== null && b.odds !== null) return b.odds - a.odds;
    if (a.odds !== null && b.odds === null) return -1;
    if (a.odds === null && b.odds !== null) return 1;
    return a.name.localeCompare(b.name);
  });

  return candidates.slice(0, PRIMARY_CANDIDATES_CAP).map((c) => c.name);
}

function deriveGeneralVisibleCandidates(args: {
  party: PartyCode;
  nomineeName: string | null;
  candidateRows: CandidateRow[];
  activeRunoffCandidateNames: string[];
}): Array<{ name: string; context: VisibleContext; eliminated: boolean }> {
  const hasRunoff = args.activeRunoffCandidateNames.length > 0;
  const visible = new Map<string, { context: VisibleContext; eliminated: boolean }>();
  if (args.nomineeName) {
    visible.set(args.nomineeName.toLowerCase(), { context: "general", eliminated: false });
  }

  for (const row of args.candidateRows) {
    const name = row.BallotpediaName?.trim();
    if (!name) continue;
    const isGeneral = row.Status.toLowerCase().startsWith("general");
    const isRunoff = Boolean(String(row.RunoffID ?? "").trim());
    const hasPrimaryEntry = Boolean(String(row["Primary ID"] ?? "").trim());
    const isEliminated = hasRunoff && hasPrimaryEntry && !isRunoff && !isGeneral;
    if (!isGeneral && !isRunoff && !isEliminated) continue;
    const context: VisibleContext = isRunoff || isEliminated ? "runoff" : "general";
    visible.set(name.toLowerCase(), { context, eliminated: isEliminated });
  }
  for (const name of args.activeRunoffCandidateNames) {
    visible.set(name.toLowerCase(), { context: "runoff", eliminated: false });
  }

  const entries = Array.from(visible.entries()).map(([key, { context, eliminated }]) => ({
    name:
      args.nomineeName && key === args.nomineeName.toLowerCase()
        ? args.nomineeName
        : args.candidateRows.find((row) => row.BallotpediaName.toLowerCase() === key)?.BallotpediaName ??
          args.activeRunoffCandidateNames.find((value) => value.toLowerCase() === key) ??
          key,
    context,
    eliminated,
  }));
  entries.sort((left, right) => {
    if (left.context !== right.context) return left.context === "general" ? -1 : 1;
    if (left.eliminated !== right.eliminated) return left.eliminated ? 1 : -1;
    return left.name.localeCompare(right.name);
  });
  if (!args.nomineeName && !entries.some((entry) => entry.context === "general")) {
    entries.unshift({ name: "TBD", context: "general", eliminated: false });
  }
  return entries;
}

export function inferOpenSeat(generalRow: GeneralRow): boolean {
  const status = String(generalRow.incumbent_status ?? "").trim().toLowerCase();
  if (!status) return false;
  if (status === "incumbent") return false;
  return /(retir|vacant|open|seek|depart|resign|deceas)/.test(status);
}

function resolveIncumbentIndividual(generalRow: GeneralRow, departureRow: DepartureRow | null): string {
  const incumbentName = String(generalRow.incumbent_name ?? "").trim();
  if (incumbentName) return incumbentName;
  const departedName = String(departureRow?.name ?? "").trim();
  if (departedName) return departedName;
  return "Unknown incumbent";
}

function derivePollingSummary(rawRatings: string) {
  const parsed = parseJsonObject<{
    most_recent_poll_date?: string;
    outlet_ratings?: Array<{ outlet?: string; rating?: string; date?: string; poll_date?: string }>;
  }>(rawRatings);
  const ratings = parsed?.outlet_ratings ?? [];
  const usable = ratings.map((item) => String(item.rating ?? "").trim()).filter((item) => item && !/pending/i.test(item));
  const counts = new Map<string, number>();
  for (const rating of usable) counts.set(rating, (counts.get(rating) ?? 0) + 1);
  const summary = Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "No polling proxy";
  const sources = ratings
    .map((item) => ({
      outlet: String(item.outlet ?? "").trim(),
      rating: String(item.rating ?? "").trim(),
      date: String(item.date ?? item.poll_date ?? "").trim() || null,
    }))
    .filter((item) => item.outlet && item.rating);
  return {
    summary,
    latestDate: parsed?.most_recent_poll_date ?? null,
    sourceCount: usable.length,
    sources,
  };
}

function buildUnifiedPartyLanes(args: {
  orderedParties: PartyCode[];
  primaryPartyOrder: PartyCode[];
  generalRow: GeneralRow;
  primaryByPartyMap: Map<PartyCode, PrimaryRow[]>;
  runoffByPartyMap: Map<PartyCode, RunoffRow[]>;
  candidatesByPartyMap: Map<PartyCode, CandidateRow[]>;
  oddsMap: Record<string, number>;
  allCandidateRows: CandidateRow[];
  advanceCount?: number;
}): Array<{
  party: PartyCode;
  hasNominee: boolean;
  nomineeName: string | null;
  primaryOngoing: boolean;
  runoffOngoing: boolean;
  primaryDate: string | null;
  runoffDate: string | null;
  partyGeneralOdds: number | null;
  candidates: UnifiedCandidate[];
}> {
  // Union: orderedParties order first, then any primary-only parties (e.g. NP) appended
  const seenParties = new Set<PartyCode>(args.orderedParties);
  const unionParties: PartyCode[] = [...args.orderedParties];
  for (const party of args.primaryPartyOrder) {
    if (!seenParties.has(party)) {
      seenParties.add(party);
      unionParties.push(party);
    }
  }

  // When an NP (non-partisan) primary exists, all candidates belong to that lane.
  // Partisan lanes (DEM/REP/etc.) are kept for their general-election odds display
  // but show no candidates — they are non-expandable banners only.
  const hasNpPrimary = args.primaryPartyOrder.includes("NP");

  return unionParties.map((party) => {
    // NP primaries aggregate all candidates regardless of party affiliation.
    // Partisan lanes in an NP-primary race carry no candidates.
    const candidates =
      party === "NP"
        ? args.allCandidateRows.filter((candidate) => {
            const status = candidate.Status.toLowerCase();
            return Boolean(String(candidate["Primary ID"] ?? "").trim()) || status.includes("primary") || status.includes("general");
          })
        : hasNpPrimary
          ? []
          : (args.candidatesByPartyMap.get(party) ?? []).filter((candidate) => {
              const status = candidate.Status.toLowerCase();
              return Boolean(candidate["Primary ID"]) || status.includes("primary") || status.includes("general");
            });

    const activeRunoff = (args.runoffByPartyMap.get(party) ?? []).find((row) => row.status.toLowerCase() === "runoff");
    const runoffPair = activeRunoff
      ? uniqueOrdered([activeRunoff.runoff_candidate_1 ?? "", activeRunoff.runoff_candidate_2 ?? ""]).slice(0, 2)
      : [];
    const nomineeName = nomineeNameForParty(args.generalRow, party);
    const primaryRowsForParty = args.primaryByPartyMap.get(party) ?? [];
    const primaryPartyStatusComplete = primaryRowsForParty.some((row) => row.status.toLowerCase() === "complete");
    const primaryOngoing =
      primaryRowsForParty.some((row) => isPrimaryStatusOngoing(row.status)) ||
      isPrimaryStatusOngoing(partyStatusInGeneralRow(args.generalRow, party));

    // Aggregate per-party primary odds map from primary rows.
    // Used as a fallback when KalshiBestPrimaryOdds is absent from the candidate rollup,
    // and also to surface Kalshi-only primary candidates not matched in Ballotpedia.
    const partyPrimaryOddsMap: Record<string, number> = {};
    for (const primaryRow of primaryRowsForParty) {
      const rowOdds = parseOddsMap(primaryRow.kalshi_primary_odds_map ?? "");
      for (const [name, odds] of Object.entries(rowOdds)) {
        if (PARTY_LABEL_PATTERNS.test(name)) continue;
        if (!(name in partyPrimaryOddsMap) || partyPrimaryOddsMap[name] < odds) {
          partyPrimaryOddsMap[name] = odds;
        }
      }
    }

    // Track normalized names of all Ballotpedia candidates processed, so we
    // can inject Kalshi-only names that have no matching Ballotpedia entry.
    const processedNormNames = new Set<string>();

    const mapped: UnifiedCandidate[] = candidates.map((candidate) => {
      const name = candidate.BallotpediaName.trim();
      processedNormNames.add(normalizeName(name));

      const inRunoffPair = runoffPair.some((runoffName) => runoffName.toLowerCase() === name.toLowerCase());
      const isNominee = nomineeName !== null && nomineeName.toLowerCase() === name.toLowerCase();
      const stage: "nominee" | "runoff" | "candidate" = inRunoffPair ? "runoff" : isNominee ? "nominee" : "candidate";
      const hasDecision = Boolean(runoffPair.length) || Boolean(nomineeName) || primaryPartyStatusComplete;
      const statusText = candidate.Status.toLowerCase();

      // Primary odds: prefer KalshiBestPrimaryOdds; fall back to kalshi_primary_odds_map lookup
      const primaryOdds = parsePrimaryOddsFromRow(candidate) ?? candidateOddsForLane(name, partyPrimaryOddsMap);

      const nameGeneralOdds = candidateOddsForLane(name, args.oddsMap);
      // Only nominees participate in the general election; apply party-level odds fallback for them
      const generalOdds =
        stage === "nominee"
          ? nameGeneralOdds ?? partyOddsForLane(party, args.oddsMap)
          : nameGeneralOdds;
      return {
        name,
        stage,
        primaryOdds,
        generalOdds,
        eliminated: stage === "candidate" && (hasDecision || /eliminat|lost/.test(statusText)),
        nameUnmatched: false,
        partyAffiliation: party === "NP" ? partyAffiliationTag(candidate.Party) : null,
      };
    });

    // Inject Kalshi-only primary candidates: names in the primary odds map that
    // don't match any Ballotpedia candidate by normalized name.
    // These are shown with nameUnmatched: true so the UI can flag them.
    for (const [oddsName, primaryOdds] of Object.entries(partyPrimaryOddsMap)) {
      if (processedNormNames.has(normalizeName(oddsName))) continue;
      const inRunoffPair = runoffPair.some((r) => normalizeName(r) === normalizeName(oddsName));
      const isNominee = nomineeName !== null && normalizeName(nomineeName) === normalizeName(oddsName);
      const stage: "nominee" | "runoff" | "candidate" = inRunoffPair ? "runoff" : isNominee ? "nominee" : "candidate";
      const nameGeneralOdds = candidateOddsForLane(oddsName, args.oddsMap);
      const generalOdds =
        stage === "nominee"
          ? nameGeneralOdds ?? partyOddsForLane(party, args.oddsMap)
          : nameGeneralOdds;
      mapped.push({ name: oddsName, stage, primaryOdds, generalOdds, eliminated: false, nameUnmatched: true, partyAffiliation: null });
    }

    // Inject runoff candidates missing from the candidate rollup
    for (const runoffName of runoffPair) {
      if (!mapped.some((c) => c.name.toLowerCase() === runoffName.toLowerCase())) {
        mapped.push({ name: runoffName, stage: "runoff", primaryOdds: null, generalOdds: null, eliminated: false, nameUnmatched: false, partyAffiliation: null });
      }
    }
    // Inject nominee missing from the candidate rollup
    if (nomineeName && !mapped.some((c) => c.name.toLowerCase() === nomineeName.toLowerCase())) {
      const nomineeGeneralOdds = candidateOddsForLane(nomineeName, args.oddsMap) ?? partyOddsForLane(party, args.oddsMap);
      mapped.push({ name: nomineeName, stage: "nominee", primaryOdds: null, generalOdds: nomineeGeneralOdds, eliminated: false, nameUnmatched: false, partyAffiliation: null });
    }

    // For top-two / top-four primaries on NP lanes: mirror buildDetailEntities logic.
    // Only promote candidates to stage="general" once the primary is complete;
    // while ongoing, leave every candidate at stage="candidate" with eliminated=false.
    const effectiveAdvanceCount = args.advanceCount ?? 1;
    if (party === "NP" && effectiveAdvanceCount > 1) {
      if (primaryPartyStatusComplete) {
        const withOdds = mapped.filter((c) => c.primaryOdds !== null).sort((a, b) => (b.primaryOdds ?? 0) - (a.primaryOdds ?? 0));
        const advancingNames = new Set(withOdds.slice(0, effectiveAdvanceCount).map((c) => c.name.toLowerCase()));
        for (const c of mapped) {
          if (c.stage === "nominee" || c.stage === "runoff") continue;
          c.stage = advancingNames.has(c.name.toLowerCase()) ? "general" : "candidate";
          c.eliminated = c.stage === "candidate";
        }
      } else {
        for (const c of mapped) {
          if (c.stage === "nominee" || c.stage === "runoff") continue;
          c.stage = "candidate";
          c.eliminated = false;
        }
      }
    }

    mapped.sort((left, right) => {
      const stageRank = { general: 0, runoff: 0, nominee: 1, candidate: 2 };
      if (stageRank[left.stage] !== stageRank[right.stage]) {
        return stageRank[left.stage] - stageRank[right.stage];
      }
      if (left.stage === "runoff" && right.stage === "runoff") {
        return (
          runoffPair.findIndex((name) => name.toLowerCase() === left.name.toLowerCase()) -
          runoffPair.findIndex((name) => name.toLowerCase() === right.name.toLowerCase())
        );
      }
      if (left.primaryOdds !== null && right.primaryOdds !== null && left.primaryOdds !== right.primaryOdds) {
        return right.primaryOdds - left.primaryOdds;
      }
      if (left.primaryOdds !== null && right.primaryOdds === null) return -1;
      if (left.primaryOdds === null && right.primaryOdds !== null) return 1;
      return left.name.localeCompare(right.name);
    });

    // For parties whose nominee holds the general market (e.g. "James Talarico": 42)
    // rather than the party label ("Democratic party": 42), partyOddsForLane returns
    // null. Fall back to the nominee's name-keyed odds so the party header shows a value.
    const partyGeneralOdds =
      partyOddsForLane(party, args.oddsMap) ??
      (nomineeName ? candidateOddsForLane(nomineeName, args.oddsMap) : null);

    return {
      party,
      hasNominee: Boolean(nomineeName),
      nomineeName: nomineeName ?? null,
      primaryOngoing,
      runoffOngoing: Boolean(activeRunoff),
      primaryDate: primaryOngoing ? args.generalRow.primary_date || null : null,
      runoffDate: activeRunoff?.runoff_date || args.generalRow.runoff_date || null,
      partyGeneralOdds,
      candidates: mapped,
    };
  });
}

export function buildDetailEntities(args: {
  seatId: string;
  generalRow: GeneralRow;
  primaryRows: PrimaryRow[];
  runoffRows: RunoffRow[];
  candidateRows: CandidateRow[];
  departureRow: DepartureRow | null;
  office?: string;
}) {
  const primaryState = getPrimaryState(args.primaryRows, args.runoffRows);
  const primaryByPartyMap = primaryByParty(args.primaryRows);
  const runoffByPartyMap = runoffByParty(args.runoffRows);
  const advanceCount = args.primaryRows.reduce((max, r) => Math.max(max, r.advance_count ?? 1), 1);
  const PRIMARY_TYPE_RANK: Record<string, number> = { partisan_binary: 0, jungle: 1, top_two: 2, top_four: 3 };
  const primaryType = args.primaryRows.reduce((best, r) => {
    const t = r.primary_type ?? "partisan_binary";
    return (PRIMARY_TYPE_RANK[t] ?? 0) > (PRIMARY_TYPE_RANK[best] ?? 0) ? t : best;
  }, "partisan_binary");
  const candidatesByPartyMap = candidateByParty(args.candidateRows);
  const oddsMap = parseOddsMap(args.generalRow.kalshi_general_odds_map);

  const extraParties = new Set<PartyCode>();
  for (const row of args.primaryRows) {
    const party = parsePartyFromLabel(row.party);
    if (party && party !== "NP") extraParties.add(party);
  }
  for (const row of args.runoffRows) {
    const party = parsePartyFromLabel(row.party);
    if (party && party !== "NP") extraParties.add(party);
  }
  for (const row of args.candidateRows) {
    const party = parsePartyFromLabel(row.Party);
    if (party && party !== "NP") extraParties.add(party);
  }
  for (const nomineeColumn of ["nominee_d", "nominee_r", "nominee_green", "nominee_libertarian"] as const) {
    if ((args.generalRow[nomineeColumn] ?? "").trim()) {
      const party = normalizePartyFromNomineeColumn(nomineeColumn);
      if (party) extraParties.add(party);
    }
  }
  const orderedParties = [...BASE_GENERAL_PARTIES, ...Array.from(extraParties).filter((party) => !BASE_GENERAL_PARTIES.includes(party))];

  const partyLanes: GeneralLane[] = orderedParties.map((party) => {
    const nomineeName = nomineeNameForParty(args.generalRow, party);
    const primaryRowsForParty = primaryByPartyMap.get(party) ?? [];
    const runoffRowsForParty = runoffByPartyMap.get(party) ?? [];
    const partyCandidates = candidatesByPartyMap.get(party) ?? [];
    const activeRunoff = runoffRowsForParty.find((row) => row.status.toLowerCase() === "runoff");
    const runoffCandidates = activeRunoff
      ? uniqueOrdered([activeRunoff.runoff_candidate_1 ?? "", activeRunoff.runoff_candidate_2 ?? ""]).slice(0, 2)
      : [];
    const primaryOngoing =
      primaryRowsForParty.some((row) => isPrimaryStatusOngoing(row.status)) || isPrimaryStatusOngoing(partyStatusInGeneralRow(args.generalRow, party));

    const primaryCandidates = derivePrimaryCandidateNames({
      primaryOngoing,
      hasRunoff: Boolean(activeRunoff),
      hasNominee: Boolean(nomineeName),
      candidateRows: partyCandidates,
      primaryRows: primaryRowsForParty,
    });

    const visibleCandidates = deriveGeneralVisibleCandidates({
      party,
      nomineeName,
      candidateRows: partyCandidates,
      activeRunoffCandidateNames: runoffCandidates,
    }).map((candidate) => {
      const candidateOdds = candidateOddsForLane(candidate.name, oddsMap);
      const partyOdds = partyOddsForLane(party, oddsMap);
      return {
        ...candidate,
        odds: candidate.context === "general" ? candidateOdds ?? partyOdds : null,
      };
    });

    return {
      party,
      hasNominee: Boolean(nomineeName),
      nomineeName: nomineeName ?? null,
      primaryOngoing,
      primaryDate: primaryOngoing ? args.generalRow.primary_date || null : null,
      primaryCandidates,
      runoffOngoing: Boolean(activeRunoff),
      runoffDate: activeRunoff?.runoff_date || args.generalRow.runoff_date || null,
      runoffCandidates,
      visibleCandidates,
    };
  });

  const openSeat = inferOpenSeat(args.generalRow);
  const incumbentParty = parsePartyFromLabel(args.generalRow.incumbent_party);
  const departedIncumbentParty = parsePartyFromLabel(args.departureRow?.party);
  const controllingParty = incumbentParty ?? (openSeat ? departedIncumbentParty ?? null : null);
  const departureReasonParts = [args.departureRow?.departure_reason, args.departureRow?.departure_subreason]
    .map((part) => String(part ?? "").trim())
    .filter(Boolean);
  const departureReason = openSeat ? (departureReasonParts.length ? departureReasonParts.join(" - ") : "unknown") : "n/a";

  const polling = derivePollingSummary(args.generalRow.general_election_race_ratings);
  const pollingParty = getPollingProxyPartyAndScore(args.generalRow.general_election_race_ratings).party;
  const topOdds = Object.entries(oddsMap).sort((a, b) => b[1] - a[1])[0];
  const marketFavoriteParty = resolveMarketFavoriteParty(oddsMap, args.generalRow);
  const targetingKey = getTargetingKey(args.generalRow, args.office);

  const hasNPPrimary = args.primaryRows.some((row) => parsePartyFromLabel(row.party) === "NP");

  const primaryPartyOrder: PartyCode[] = hasNPPrimary
    ? ["NP"]
    : Array.from(
        new Set<PartyCode>([
          ...args.candidateRows
            .filter((row) => String(row["Primary ID"] ?? "").trim() || row.Status.toLowerCase().includes("primary") || row.Status.toLowerCase().includes("general"))
            .map((row) => parsePartyFromLabel(row.Party))
            .filter((party): party is PartyCode => Boolean(party)),
          ...args.primaryRows.map((row) => parsePartyFromLabel(row.party)).filter((party): party is PartyCode => Boolean(party)),
          ...args.runoffRows.map((row) => parsePartyFromLabel(row.party)).filter((party): party is PartyCode => Boolean(party)),
        ]),
      );

  const primaryParties = primaryPartyOrder.map((party) => {
    // For NP primaries, aggregate all candidates across parties into one section.
    const candidates =
      party === "NP"
        ? args.candidateRows.filter((candidate) => {
            const status = candidate.Status.toLowerCase();
            return Boolean(String(candidate["Primary ID"] ?? "").trim()) || status.includes("primary") || status.includes("general");
          })
        : (candidatesByPartyMap.get(party) ?? []).filter((candidate) => {
            const status = candidate.Status.toLowerCase();
            return Boolean(candidate["Primary ID"]) || status.includes("primary") || status.includes("general");
          });
    const activeRunoff = (runoffByPartyMap.get(party) ?? []).find((row) => row.status.toLowerCase() === "runoff");
    const runoffPair = activeRunoff
      ? uniqueOrdered([activeRunoff.runoff_candidate_1 ?? "", activeRunoff.runoff_candidate_2 ?? ""]).slice(0, 2)
      : [];
    const nomineeName = nomineeNameForParty(args.generalRow, party);
    const primaryRowsForParty = primaryByPartyMap.get(party) ?? [];
    const primaryPartyStatusComplete = primaryRowsForParty.some((row) => row.status.toLowerCase() === "complete");

    const mapped = candidates.map((candidate) => {
      const name = candidate.BallotpediaName.trim();
      const inRunoffPair = runoffPair.some((runoffName) => runoffName.toLowerCase() === name.toLowerCase());
      const isNominee = nomineeName !== null && nomineeName.toLowerCase() === name.toLowerCase();
      // For advance primaries (top-two / top-four), stage is reassigned below after sorting by odds.
      const stage: PrimaryCandidate["stage"] =
        advanceCount > 1 ? "candidate" : inRunoffPair ? "runoff" : isNominee ? "nominee" : "candidate";
      const hasDecision = Boolean(runoffPair.length) || Boolean(nomineeName) || primaryPartyStatusComplete;
      const statusText = candidate.Status.toLowerCase();
      return {
        name,
        status: candidate.Status,
        stage,
        odds: parsePrimaryOddsFromRow(candidate),
        eliminated: stage === "candidate" && (hasDecision || /eliminat|lost/.test(statusText)),
        kalshiMarketUrl: extractBestPrimaryMarketUrl(candidate),
      } as PrimaryCandidate;
    });

    for (const runoffName of runoffPair) {
      if (!mapped.some((candidate) => candidate.name.toLowerCase() === runoffName.toLowerCase())) {
        mapped.push({ name: runoffName, status: "runoff", stage: "runoff", odds: null, eliminated: false, kalshiMarketUrl: null });
      }
    }
    if (nomineeName && !mapped.some((candidate) => candidate.name.toLowerCase() === nomineeName.toLowerCase())) {
      mapped.push({ name: nomineeName, status: "general (nominated)", stage: "nominee", odds: null, eliminated: false, kalshiMarketUrl: null });
    }

    // For top-two / top-four primaries: once the primary is complete, assign
    // stage="general" to the top advanceCount candidates and eliminate all others.
    // While the primary is still ongoing, no one has advanced yet — leave every
    // candidate at stage="candidate" with eliminated=false.
    if (advanceCount > 1) {
      if (primaryPartyStatusComplete) {
        const sortedByOdds = [...mapped]
          .filter((c) => c.odds !== null)
          .sort((a, b) => (b.odds ?? 0) - (a.odds ?? 0));
        const advancingNames = new Set(sortedByOdds.slice(0, advanceCount).map((c) => c.name.toLowerCase()));
        for (const c of mapped) {
          c.stage = advancingNames.has(c.name.toLowerCase()) ? "general" : "candidate";
          c.eliminated = c.stage === "candidate";
        }
      } else {
        for (const c of mapped) {
          c.stage = "candidate";
          c.eliminated = false;
        }
      }
    }

    mapped.sort((left, right) => {
      const stageRank: Record<string, number> = { general: 0, runoff: 0, nominee: 1, candidate: 2 };
      if (stageRank[left.stage] !== stageRank[right.stage]) {
        return stageRank[left.stage] - stageRank[right.stage];
      }
      if (left.stage === "runoff" && right.stage === "runoff") {
        return runoffPair.findIndex((name) => name.toLowerCase() === left.name.toLowerCase()) -
          runoffPair.findIndex((name) => name.toLowerCase() === right.name.toLowerCase());
      }
      if (left.odds !== null && right.odds !== null && left.odds !== right.odds) {
        return right.odds - left.odds;
      }
      if (left.odds !== null && right.odds === null) return -1;
      if (left.odds === null && right.odds !== null) return 1;
      return left.name.localeCompare(right.name);
    });

    return {
      party,
      hasPrimaryMarket: mapped.some((candidate) => candidate.odds !== null),
      candidates: mapped,
    };
  });

  // candidateRows may use zero-padded seat IDs (e.g. "MO-01") while seatId
  // comes from the general rollup using short form ("MO-1"). Normalize both
  // sides so we don't miss any matched Ballotpedia candidates.
  const normalizedSeatId = normalizeSeatId(args.seatId);
  const allCandidateRows = args.candidateRows.filter(
    (r) => normalizeSeatId(r["2026 Seat"]) === normalizedSeatId,
  );
  const knownNames = new Set(
    allCandidateRows.map((r) => r.BallotpediaName.trim().toLowerCase()),
  );

  const kalshiOnlyCandidates = Object.entries(oddsMap)
    .filter(([name]) => !PARTY_LABEL_PATTERNS.test(name) && !knownNames.has(name.trim().toLowerCase()))
    .map(([name, odds]) => ({ name, odds }))
    .sort((a, b) => (b.odds ?? 0) - (a.odds ?? 0));

  // Aggregate Kalshi primary odds maps across all primary rows for this seat,
  // then surface any candidate name not matched in the Ballotpedia rollup.
  const primaryOddsAggregate = new Map<string, number>();
  for (const primaryRow of args.primaryRows) {
    const primaryOddsMap = parseOddsMap(primaryRow.kalshi_primary_odds_map ?? "");
    for (const [name, odds] of Object.entries(primaryOddsMap)) {
      if (!primaryOddsAggregate.has(name) || (primaryOddsAggregate.get(name) ?? 0) < odds) {
        primaryOddsAggregate.set(name, odds);
      }
    }
  }
  const kalshiOnlyPrimaryCandidates = Array.from(primaryOddsAggregate.entries())
    .filter(([name]) => !PARTY_LABEL_PATTERNS.test(name) && !knownNames.has(name.trim().toLowerCase()))
    .map(([name, odds]) => ({ name, odds }))
    .sort((a, b) => b.odds - a.odds);

  return {
    generalElection: {
      partyLanes,
      kalshiOnlyCandidates,
    },
    incumbencyAndControl: {
      controllingParty,
      incumbentIndividual: resolveIncumbentIndividual(args.generalRow, args.departureRow),
      openSeat,
      departureReason,
      departedIncumbentParty: departedIncumbentParty ?? null,
    },
    competitiveness: {
      pollingStatus: {
        summary: polling.summary,
        latestDate: polling.latestDate,
        sourceCount: polling.sourceCount,
        leadingParty: pollingParty,
        sources: polling.sources,
      },
      kalshiGeneralOdds: {
        favoriteParty: marketFavoriteParty,
        favoriteLabel: topOdds?.[0] ?? null,
        favoriteOdds: topOdds?.[1] ?? null,
        oddsMap,
      },
      targeting: {
        key: targetingKey,
        dcccTarget: parseBooleanText(args.generalRow.dccc_target),
        nrccTarget: parseBooleanText(args.generalRow.nrcc_target),
      },
    },
    primaryElection: {
      primaryState,
      primaryType,
      advanceCount,
      parties: primaryParties,
      kalshiOnlyPrimaryCandidates,
    },
    unifiedElection: {
      parties: buildUnifiedPartyLanes({
        orderedParties,
        primaryPartyOrder,
        generalRow: args.generalRow,
        primaryByPartyMap,
        runoffByPartyMap,
        candidatesByPartyMap,
        oddsMap,
        allCandidateRows: args.candidateRows,
        advanceCount,
      }),
      kalshiOnlyCandidates: kalshiOnlyCandidates.map((c) => ({
        name: c.name,
        primaryOdds: null,
        generalOdds: c.odds,
      })),
    },
  };
}

export function partyLabel(party: PartyCode): string {
  return PARTY_LABELS[party] ?? party;
}
