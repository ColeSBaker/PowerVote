import type { SubScore, ScoreWeights, CompositeScore, ScoreBand } from "./types";
import { DEFAULT_WEIGHTS } from "./types";

export interface CompositeInput {
  incumbency: SubScore;
  market: SubScore;
  polling: SubScore;
  targeting: SubScore;
}

const DIMENSION_KEYS = ["incumbency", "market", "polling", "targeting"] as const;

function deriveBand(score: number | null): ScoreBand {
  if (score === null) return "Unknown";
  if (score < 35) return "Safe";
  if (score < 55) return "Lean";
  if (score < 75) return "Competitive";
  return "Toss-up";
}

/**
 * Combine four subscores into a single composite competitiveness score.
 *
 * Null-score dimensions are excluded and the remaining weights are
 * renormalised proportionally so they always sum to 1.0.
 *
 * @param subscores  Output from the four individual scorers.
 * @param weights    Partial weight overrides; merged with DEFAULT_WEIGHTS.
 *                   Values need not sum to 1 — they are normalised internally.
 */
export function computeCompositeScore(
  subscores: CompositeInput,
  weights: Partial<ScoreWeights> = {},
): CompositeScore {
  const w: ScoreWeights = { ...DEFAULT_WEIGHTS, ...weights };

  // Collect only dimensions that have a non-null score
  type ActiveComponent = { key: (typeof DIMENSION_KEYS)[number]; score: number; weight: number; confidence: number };
  const active: ActiveComponent[] = [];
  for (const key of DIMENSION_KEYS) {
    const sub = subscores[key];
    if (sub.score !== null) {
      active.push({ key, score: sub.score, weight: w[key], confidence: sub.confidence });
    }
  }

  const totalWeight = active.reduce((s, c) => s + c.weight, 0);

  const compositeScore =
    totalWeight > 0
      ? Math.round((active.reduce((s, c) => s + c.score * (c.weight / totalWeight), 0)) * 100) / 100
      : null;

  const band = deriveBand(compositeScore);

  // Effective weights (post-renormalisation)
  const effectiveWeights: ScoreWeights = { incumbency: 0, market: 0, polling: 0, targeting: 0 };
  for (const c of active) {
    effectiveWeights[c.key] = totalWeight > 0 ? c.weight / totalWeight : 0;
  }

  // Human-readable reason string
  const reasonParts = active.map(
    (c) => `${c.key.charAt(0).toUpperCase() + c.key.slice(1)} ${subscores[c.key].score!.toFixed(1)}`,
  );

  return {
    score: compositeScore,
    band,
    reason: reasonParts.join(" | ") || "No data available",
    breakdown: {
      incumbency: { score: subscores.incumbency.score, weight: w.incumbency, confidence: subscores.incumbency.confidence },
      market:     { score: subscores.market.score,     weight: w.market,     confidence: subscores.market.confidence },
      polling:    { score: subscores.polling.score,    weight: w.polling,    confidence: subscores.polling.confidence },
      targeting:  { score: subscores.targeting.score,  weight: w.targeting,  confidence: subscores.targeting.confidence },
    },
    weightsUsed: w,
    effectiveWeights,
  };
}
