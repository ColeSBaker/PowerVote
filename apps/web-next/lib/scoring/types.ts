import { z } from "zod";

/**
 * The output of a single scoring dimension.
 *
 * score  — 0–100 where higher means MORE competitive (toss-up). null means
 *          insufficient data to produce a score; the composite will exclude
 *          this dimension and proportionally reweight the others.
 *
 * confidence — 0.0–1.0 advisory value indicating data completeness. Used
 *              only for display (e.g. dimming a low-confidence score in the
 *              UI). The composite uses the null check, not confidence, for
 *              reweighting decisions.
 *
 * detail — raw inputs / intermediate values for transparency / debugging.
 */
export interface SubScore {
  score: number | null;
  confidence: number;
  detail: Record<string, unknown>;
}

/**
 * Relative weights for the four scoring dimensions.
 * Values need not sum to 1 — the composite normalises them.
 * This lets users set sliders independently without enforcing a constraint.
 */
export interface ScoreWeights {
  incumbency: number;
  market: number;
  polling: number;
  targeting: number;
}

export const DEFAULT_WEIGHTS: ScoreWeights = {
  incumbency: 0.00,
  market: 0.60,
  polling: 0.25,
  targeting: 0.15,
};

export type ScoreBand = "Safe" | "Lean" | "Competitive" | "Toss-up" | "Unknown" | "Uncontested";

/** Full output of the composite scorer. */
export interface CompositeScore {
  score: number | null;
  band: ScoreBand;
  reason: string;
  breakdown: {
    incumbency: { score: number | null; weight: number; confidence: number };
    market: { score: number | null; weight: number; confidence: number };
    polling: { score: number | null; weight: number; confidence: number };
    targeting: { score: number | null; weight: number; confidence: number };
  };
  /** The raw weights as supplied by the caller (before null-reweighting). */
  weightsUsed: ScoreWeights;
  /** Effective weights after proportional reweighting for null-score dimensions. */
  effectiveWeights: ScoreWeights;
}

/**
 * Zod schema for weight query params.
 * Accepts a partial object — omitted keys fall back to DEFAULT_WEIGHTS.
 * Values must be in [0, 1].
 */
export const scoreWeightsSchema = z
  .object({
    incumbency: z.number().min(0).max(1),
    market: z.number().min(0).max(1),
    polling: z.number().min(0).max(1),
    targeting: z.number().min(0).max(1),
  })
  .partial()
  .transform((partial): ScoreWeights => ({ ...DEFAULT_WEIGHTS, ...partial }));
