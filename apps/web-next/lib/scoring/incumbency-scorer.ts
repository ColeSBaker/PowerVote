import type { SubScore } from "./types";

export interface IncumbencyScorerInput {
  incumbentName: string;
  incumbentStatus: string;
  incumbentParty: string;
}

/**
 * Keywords in incumbent_status that indicate the seat is effectively open —
 * the incumbent is not running for re-election.
 */
const OPEN_SEAT_KEYWORDS = ["retir", "not seeking", "defeated", "term limit", "resign", "vacancy"];

/**
 * Score the incumbency dimension.
 *
 * Open seats score 65 (Competitive band) — they are historically ~8 pts
 * closer in margin than incumbent-contested seats.
 *
 * Incumbent-running seats score 30 (Lean band) — incumbents win ~85–90 % of
 * re-election races, so this is a mildly safe-leaning prior. Market and
 * polling weights will dominate whenever real data is present.
 *
 * This scorer never returns null — even the absence of an incumbent name is
 * itself a signal (open seat). It acts as a structural prior when all other
 * scorers lack data.
 */
export function scoreIncumbency(input: IncumbencyScorerInput): SubScore {
  const name = (input.incumbentName ?? "").trim();
  const status = (input.incumbentStatus ?? "").trim().toLowerCase();

  const isOpenSeat =
    !name || OPEN_SEAT_KEYWORDS.some((kw) => status.includes(kw));

  if (isOpenSeat) {
    return {
      score: 65,
      confidence: 0.6,
      detail: {
        signal: "open_seat",
        incumbentName: name || null,
        incumbentStatus: input.incumbentStatus,
      },
    };
  }

  return {
    score: 30,
    confidence: 0.5,
    detail: {
      signal: "incumbent_running",
      incumbentName: name,
      incumbentStatus: input.incumbentStatus,
      incumbentParty: input.incumbentParty,
    },
  };
}
