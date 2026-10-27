import type { SubScore } from "./types";

export interface MarketScorerInput {
  /** Raw JSON string from kalshi_general_odds_map CSV field. */
  kalshiGeneralOddsMap: string;
}

function safeParseObject<T extends Record<string, unknown>>(raw: string | undefined): T | null {
  if (!raw?.trim()) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as T;
    return null;
  } catch {
    return null;
  }
}

/**
 * Score the market dimension using Kalshi prediction market odds.
 *
 * Competitiveness = 100 − |top_odds_1 − top_odds_2|
 * A race where the leading side has 99 % odds → spread 98 → score 2 (Safe).
 * A 50/50 race → spread 0 → score 100 (Toss-up).
 *
 * Returns null when no valid market data is available.
 */
export function scoreMarket(input: MarketScorerInput): SubScore {
  const map = safeParseObject<Record<string, number>>(input.kalshiGeneralOddsMap);
  if (!map) {
    return { score: null, confidence: 0, detail: { reason: "no_market_data" } };
  }

  const values = Object.values(map)
    .map(Number)
    .filter(Number.isFinite)
    .sort((a, b) => b - a);

  if (values.length < 2) {
    return { score: null, confidence: 0, detail: { reason: "insufficient_candidates", candidateCount: values.length } };
  }

  const spread = Math.abs(values[0] - values[1]);
  const score = Math.round(Math.max(0, 100 - spread) * 100) / 100;
  const confidence = Math.min(1, values.length / 2);

  return {
    score,
    confidence,
    detail: { spread, candidateCount: values.length, topOdds: values.slice(0, 2) },
  };
}
