import type { SubScore } from "./types";

export interface PollingScorerInput {
  /** Raw JSON string from general_election_race_ratings CSV field. */
  generalElectionRaceRatings: string;
}

export interface RatingBreakdownEntry {
  outlet: string;
  rating: string;
  score: number | null;
}

/** The four well-known race-rating outlets tracked by the pipeline. */
const KNOWN_OUTLET_COUNT = 4;

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
 * Maps a race rating label to a 0–100 competitiveness score.
 * Returns null for unrecognised or "Pending" ratings (excluded from average).
 */
function ratingToScore(rating: string): number | null {
  const norm = rating.toLowerCase();
  if (/(toss|tilt)/.test(norm)) return 90;
  if (/lean/.test(norm)) return 70;
  if (/likely/.test(norm)) return 45;
  if (/(safe|solid)/.test(norm)) return 20;
  return null;
}

/**
 * Score the polling dimension using race ratings from Cook, DDHQ/The Hill,
 * Inside Elections, and Sabato's Crystal Ball.
 *
 * The score is the mean of individual outlet scores.
 * Confidence = recognised_outlets / KNOWN_OUTLET_COUNT (max 1.0).
 * Returns null when no recognised ratings exist.
 */
export function scorePolling(input: PollingScorerInput): SubScore {
  const parsed = safeParseObject<{ outlet_ratings?: Array<{ outlet?: string; rating?: string }> }>(
    input.generalElectionRaceRatings,
  );
  const outletRatings = parsed?.outlet_ratings ?? [];

  const breakdown: RatingBreakdownEntry[] = [];
  const scores: number[] = [];

  for (const entry of outletRatings) {
    const outlet = String(entry?.outlet ?? "").trim();
    const rating = String(entry?.rating ?? "").trim();
    if (!rating) continue;
    const score = ratingToScore(rating);
    breakdown.push({ outlet, rating, score });
    if (score !== null) scores.push(score);
  }

  if (!scores.length) {
    return {
      score: null,
      confidence: 0,
      detail: { reason: "no_recognized_ratings", breakdown },
    };
  }

  const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
  const score = Math.round(avg);
  const confidence = Math.min(1, scores.length / KNOWN_OUTLET_COUNT);

  return {
    score,
    confidence,
    detail: { outletCount: outletRatings.length, recognizedCount: scores.length, breakdown },
  };
}
