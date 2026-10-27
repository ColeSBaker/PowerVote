import type { PartyCode } from "@/lib/domain/schemas";
import { normalizePartyCode, parseBooleanText, parseJsonObject, parseNullableNumber } from "@/lib/server/csv";
import type { GeneralRow, PrimaryRow, RunoffRow } from "@/lib/server/data-source";
import { computeCompositeScore, scoreIncumbency, scoreMarket, scorePolling, scoreTargeting } from "@/lib/scoring";
import type { CompositeScore, ScoreBand, ScoreWeights } from "@/lib/scoring";

export type PrimaryState = "ongoing_primary" | "ongoing_runoff" | "complete" | "none";

const PARTY_FROM_LABEL: Record<string, PartyCode> = {
  "democratic party": "DEM",
  democrat: "DEM",
  democratic: "DEM",
  "republican party": "REP",
  republican: "REP",
  ind: "IND",
  independent: "IND",
  libertarian: "LIB",
  green: "GRE",
  nonpartisan: "NP",
  "no party preference": "NP",
};

export function parsePartyFromLabel(label: string | undefined): PartyCode | null {
  if (!label) return null;
  const norm = label.trim().toLowerCase();
  if (!norm) return null;
  for (const [key, value] of Object.entries(PARTY_FROM_LABEL)) {
    if (norm.includes(key)) return value;
  }
  return normalizePartyCode(norm);
}

export function getMarketFavoriteParty(rawOddsMap: string): PartyCode | null {
  const map = parseJsonObject<Record<string, number>>(rawOddsMap);
  if (!map) return null;
  const entries = Object.entries(map)
    .map(([key, value]) => ({ key, value: Number(value) }))
    .filter((entry) => Number.isFinite(entry.value));
  if (!entries.length) return null;
  entries.sort((left, right) => right.value - left.value);
  return parsePartyFromLabel(entries[0].key);
}

function competitivenessFromRating(rating: string): number | null {
  const normalized = rating.toLowerCase();
  if (/(toss|tilt)/.test(normalized)) return 90;
  if (/lean/.test(normalized)) return 70;
  if (/likely/.test(normalized)) return 45;
  if (/(safe|solid)/.test(normalized)) return 20;
  return null;
}

export function getPollingProxyPartyAndScore(rawRatings: string): { party: PartyCode | null; score: number | null } {
  const ratings = parseJsonObject<{ outlet_ratings?: Array<{ rating?: string }> }>(rawRatings);
  const outletRatings = ratings?.outlet_ratings ?? [];
  const competitivenessValues: number[] = [];
  const partyVotes: Record<PartyCode, number> = {
    DEM: 0,
    REP: 0,
    IND: 0,
    LIB: 0,
    GRE: 0,
    OTH: 0,
    NP: 0,
  };

  for (const outlet of outletRatings) {
    const rating = String(outlet?.rating ?? "").trim();
    if (!rating) continue;
    const score = competitivenessFromRating(rating);
    if (score !== null) competitivenessValues.push(score);
    if (/democrat/i.test(rating)) partyVotes.DEM += 1;
    if (/republican/i.test(rating)) partyVotes.REP += 1;
  }

  const winner = Object.entries(partyVotes).sort((a, b) => b[1] - a[1])[0];
  const party = winner && winner[1] > 0 ? (winner[0] as PartyCode) : null;
  const score = competitivenessValues.length
    ? Math.round(competitivenessValues.reduce((sum, value) => sum + value, 0) / competitivenessValues.length)
    : null;
  return { party, score };
}

export function getPollingProxyMapKey(rawRatings: string, pollingParty: PartyCode | null): "poll_dem" | "poll_rep" | "poll_tossup" | "poll_unknown" {
  if (pollingParty === "DEM") return "poll_dem";
  if (pollingParty === "REP") return "poll_rep";
  const ratings = parseJsonObject<{ outlet_ratings?: Array<{ rating?: string }> }>(rawRatings);
  const hasTossup = (ratings?.outlet_ratings ?? []).some((outlet) => /(toss|tilt)/i.test(String(outlet?.rating ?? "")));
  if (hasTossup) return "poll_tossup";
  return "poll_unknown";
}

/**
 * Offices for which national committee targeting data is actually scraped
 * and available. All other offices return "n_a".
 * Add "us_senate" here once Ballotpedia exposes DSCC/NRSC targeting sections.
 */
const OFFICES_WITH_TARGETING = new Set<string>(["us_house"]);

export function targetingDataAvailable(office: string): boolean {
  return OFFICES_WITH_TARGETING.has(office);
}

export function getTargetingKey(generalRow: GeneralRow, office?: string): "both" | "dccc" | "nrcc" | "none" | "n_a" {
  if (office !== undefined && !targetingDataAvailable(office)) return "n_a";
  const senate = generalRow as GeneralRow & { dscc_target?: string; nrsc_target?: string };
  const dccc = parseBooleanText(generalRow.dccc_target) || parseBooleanText(senate.dscc_target);
  const nrcc = parseBooleanText(generalRow.nrcc_target) || parseBooleanText(senate.nrsc_target);
  if (dccc && nrcc) return "both";
  if (dccc) return "dccc";
  if (nrcc) return "nrcc";
  return "none";
}

export function getPrimaryState(primaryRows: PrimaryRow[], runoffRows: RunoffRow[]): PrimaryState {
  if (runoffRows.some((row) => row.status.toLowerCase() === "runoff")) {
    return "ongoing_runoff";
  }
  if (primaryRows.some((row) => row.status.toLowerCase() === "upcoming" || row.status.toLowerCase() === "runoff")) {
    return "ongoing_primary";
  }
  if (primaryRows.length && primaryRows.every((row) => row.status.toLowerCase() === "complete")) {
    return "complete";
  }
  return "none";
}

export function mapColorForContention(state: string): { key: string; colorHex: string } {
  if (state === "contested") return { key: "contested", colorHex: "#0f766e" };
  if (state === "uncontested") return { key: "uncontested", colorHex: "#000000" };
  return { key: "no_election", colorHex: "#ffffff" };
}

function hasPrimaryMarket(raw: string | undefined): boolean {
  const parsed = parseJsonObject<Record<string, unknown>>(raw);
  if (!parsed) return false;
  return Object.keys(parsed).length > 0;
}

export function getPrimaryKalshiMarketKey(generalRow: GeneralRow): "both" | "dem" | "rep" | "none" {
  const dem = hasPrimaryMarket((generalRow as GeneralRow & { kalshi_primary_d?: string }).kalshi_primary_d);
  const rep = hasPrimaryMarket((generalRow as GeneralRow & { kalshi_primary_r?: string }).kalshi_primary_r);
  if (dem && rep) return "both";
  if (dem) return "dem";
  if (rep) return "rep";
  return "none";
}

export function computeMarketCompetitiveness(rawOddsMap: string): number | null {
  const map = parseJsonObject<Record<string, number>>(rawOddsMap);
  if (!map) return null;
  const values = Object.values(map)
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => b - a);
  if (values.length < 2) return null;
  const spread = Math.abs(values[0] - values[1]);
  const score = Math.max(0, 100 - spread);
  return Math.round(score * 100) / 100;
}

export function computeTargetingScore(targetingKey: "both" | "dccc" | "nrcc" | "none" | "n_a"): number | null {
  if (targetingKey === "n_a") return null;
  if (targetingKey === "both") return 100;
  if (targetingKey === "dccc" || targetingKey === "nrcc") return 70;
  return 20;
}

export function scoreBand(score: number | null): ScoreBand {
  if (score === null) return "Unknown";
  if (score < 35) return "Safe";
  if (score < 55) return "Lean";
  if (score < 75) return "Competitive";
  return "Toss-up";
}

function isMarketConsistentWithUncontested(rawOddsMap: string): boolean {
  const map = parseJsonObject<Record<string, number>>(rawOddsMap);
  if (!map || Object.keys(map).length === 0) return true;
  const values = Object.values(map).map(Number).filter(Number.isFinite);
  if (values.length === 0) return true;
  return Math.max(...values) >= 95;
}

export function computeWeightedCompetitiveness(generalRow: GeneralRow, office?: string): {
  score: number | null;
  band: ScoreBand;
  reason: string;
  breakdown: {
    market: { score: number | null; weight: number };
    pollingProxy: { score: number | null; weight: number };
    targeting: { score: number | null; weight: number };
  };
} {
  const composite = computeWeightedCompetitivenessWithWeights(generalRow, {}, office);

  const uncontested =
    generalRow.general_contention === "uncontested" &&
    isMarketConsistentWithUncontested(generalRow.kalshi_general_odds_map);

  return {
    score: uncontested ? null : composite.score,
    band: uncontested ? "Uncontested" : composite.band,
    reason: uncontested
      ? "This seat has no meaningful opposition in the general election."
      : composite.reason,
    breakdown: {
      market:       { score: composite.breakdown.market.score,    weight: composite.breakdown.market.weight },
      pollingProxy: { score: composite.breakdown.polling.score,   weight: composite.breakdown.polling.weight },
      targeting:    { score: composite.breakdown.targeting.score, weight: composite.breakdown.targeting.weight },
    },
  };
}

/**
 * Weight-aware variant that returns the full CompositeScore (including
 * incumbency, effectiveWeights, and confidence values).
 *
 * Pass a partial weights object to override individual dimension weights;
 * omitted keys fall back to DEFAULT_WEIGHTS.
 *
 * Pass office to correctly exclude targeting for offices where no data exists.
 */
export function computeWeightedCompetitivenessWithWeights(
  generalRow: GeneralRow,
  weights: Partial<ScoreWeights>,
  office?: string,
): CompositeScore {
  const senate = generalRow as GeneralRow & { dscc_target?: string; nrsc_target?: string };
  return computeCompositeScore(
    {
      incumbency: scoreIncumbency({
        incumbentName:   generalRow.incumbent_name,
        incumbentStatus: generalRow.incumbent_status,
        incumbentParty:  generalRow.incumbent_party,
      }),
      market: scoreMarket({
        kalshiGeneralOddsMap: generalRow.kalshi_general_odds_map,
      }),
      polling: scorePolling({
        generalElectionRaceRatings: generalRow.general_election_race_ratings,
      }),
      targeting: scoreTargeting({
        dcccTarget: generalRow.dccc_target,
        nrccTarget: generalRow.nrcc_target,
        dsccTarget: senate.dscc_target,
        nrscTarget: senate.nrsc_target,
        dataAvailable: office !== undefined ? targetingDataAvailable(office) : undefined,
      }),
    },
    weights,
  );
}

export function candidateCountFromGeneralRow(generalRow: GeneralRow): number {
  const nominees = [
    generalRow.nominee_d,
    generalRow.nominee_r,
    generalRow.nominee_green,
    generalRow.nominee_libertarian,
  ].filter((value) => String(value || "").trim().length > 0);
  return nominees.length;
}

export function mapColorForGeneralMode(args: {
  colorMode: "contention" | "incumbent" | "market_favorite" | "polling_proxy" | "targeting";
  generalRow: GeneralRow;
  incumbentParty: PartyCode | null;
  openSeat: boolean;
  marketParty: PartyCode | null;
  pollingParty: PartyCode | null;
  targetingKey: "both" | "dccc" | "nrcc" | "none" | "n_a";
}): { key: string; colorHex: string } {
  const { colorMode, generalRow, incumbentParty, openSeat, marketParty, pollingParty, targetingKey } = args;

  if (colorMode === "contention") {
    return mapColorForContention(generalRow.general_contention);
  }

  if (colorMode === "incumbent") {
    if (incumbentParty === "DEM" && !openSeat) return { key: "incumbent_dem",      colorHex: "#1d4ed8" };
    if (incumbentParty === "DEM" &&  openSeat) return { key: "incumbent_dem_open", colorHex: "#93c5fd" };
    if (incumbentParty === "REP" && !openSeat) return { key: "incumbent_rep",      colorHex: "#b91c1c" };
    if (incumbentParty === "REP" &&  openSeat) return { key: "incumbent_rep_open", colorHex: "#fca5a5" };
    return { key: "incumbent_other", colorHex: "#78716c" };
  }

  if (colorMode === "market_favorite") {
    if (marketParty === "DEM") return { key: "market_dem", colorHex: "#2563eb" };
    if (marketParty === "REP") return { key: "market_rep", colorHex: "#dc2626" };
    return { key: "market_unknown", colorHex: "#9ca3af" };
  }

  if (colorMode === "polling_proxy") {
    const key = getPollingProxyMapKey(generalRow.general_election_race_ratings, pollingParty);
    if (key === "poll_dem") return { key, colorHex: "#3b82f6" };
    if (key === "poll_rep") return { key, colorHex: "#ef4444" };
    if (key === "poll_tossup") return { key, colorHex: "#111827" };
    return { key: "poll_unknown", colorHex: "#a8a29e" };
  }

  if (targetingKey === "both") return { key: "target_both", colorHex: "#111827" };
  if (targetingKey === "dccc") return { key: "target_dccc", colorHex: "#1e40af" };
  if (targetingKey === "nrcc") return { key: "target_nrcc", colorHex: "#991b1b" };
  if (targetingKey === "n_a") return { key: "target_na", colorHex: "#e5e7eb" };
  return { key: "target_none", colorHex: "#d4d4d8" };
}

export function mapColorForPowervoteBand(band: ScoreBand): { key: string; colorHex: string } {
  if (band === "Toss-up")     return { key: "pv_tossup",       colorHex: "#c0392b" };
  if (band === "Competitive") return { key: "pv_competitive",  colorHex: "#e67e22" };
  if (band === "Lean")        return { key: "pv_lean",         colorHex: "#ca8a04" };
  if (band === "Safe")        return { key: "pv_safe",         colorHex: "#94a3b8" };
  if (band === "Uncontested") return { key: "pv_uncontested",  colorHex: "#ffffff" };
  return { key: "pv_unknown", colorHex: "#d1d5db" };
}

export function mapColorForPartyPrimaryContention(status: string, candidateCount?: number): { key: string; colorHex: string } {
  if (status === "upcoming") {
    if (candidateCount !== undefined && candidateCount > 2) return { key: "crowded", colorHex: "#7c3aed" };
    return { key: "contested", colorHex: "#0f766e" };
  }
  if (status === "runoff")   return { key: "runoff",      colorHex: "#f59e0b" };
  if (status === "complete") return { key: "complete",    colorHex: "#10b981" };
  return { key: "no_election", colorHex: "#ffffff" };
}

export function mapColorForPrimaryState(primaryState: PrimaryState): { key: string; colorHex: string } {
  if (primaryState === "ongoing_primary") return { key: "ongoing_primary", colorHex: "#f59e0b" };
  if (primaryState === "ongoing_runoff") return { key: "ongoing_runoff", colorHex: "#ef4444" };
  if (primaryState === "complete") return { key: "complete", colorHex: "#10b981" };
  return { key: "none", colorHex: "#9ca3af" };
}

export function mapColorForPrimaryKalshi(key: "both" | "dem" | "rep" | "none"): { key: string; colorHex: string } {
  if (key === "both") return { key: "primary_market_both", colorHex: "#111827" };
  if (key === "dem") return { key: "primary_market_dem", colorHex: "#1e40af" };
  if (key === "rep") return { key: "primary_market_rep", colorHex: "#991b1b" };
  return { key: "primary_market_none", colorHex: "#d4d4d8" };
}

export function mapColorForKalshiIntegrity(row: {
  kalshi_integrity_passed?: string;
  kalshi_integrity_issue_missing_sum_status?: string;
  kalshi_integrity_issue_sum_status_mismatch?: string;
  kalshi_integrity_issue_odds_map_sum_out_of_band?: string;
  kalshi_integrity_issue_missing_odds_map_with_markets?: string;
}): { key: string; colorHex: string } {
  if (parseBooleanText(row.kalshi_integrity_passed ?? "True")) {
    return { key: "integrity_pass", colorHex: "#10b981" };
  }

  const issues = [
    parseBooleanText(row.kalshi_integrity_issue_missing_odds_map_with_markets ?? "False") && "missing_odds_map",
    parseBooleanText(row.kalshi_integrity_issue_odds_map_sum_out_of_band ?? "False") && "out_of_band",
    parseBooleanText(row.kalshi_integrity_issue_sum_status_mismatch ?? "False") && "sum_mismatch",
    parseBooleanText(row.kalshi_integrity_issue_missing_sum_status ?? "False") && "missing_sum_status",
  ].filter(Boolean);

  if (issues.length === 0) return { key: "integrity_no_data", colorHex: "#d1d5db" };
  if (issues.length > 1) return { key: "integrity_multiple", colorHex: "#9f1239" };

  if (issues[0] === "out_of_band") return { key: "integrity_out_of_band", colorHex: "#ef4444" };
  if (issues[0] === "sum_mismatch") return { key: "integrity_sum_mismatch", colorHex: "#f97316" };
  if (issues[0] === "missing_sum_status") return { key: "integrity_missing_sum_status", colorHex: "#eab308" };
  return { key: "integrity_missing_odds_map", colorHex: "#8b5cf6" };
}

export function parseIncumbentParty(raw: string): PartyCode | null {
  return normalizePartyCode(raw);
}

export function parseCandidateOdds(raw: string | undefined): number | null {
  return parseNullableNumber(raw);
}
