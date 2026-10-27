import type { SubScore } from "./types";

export interface TargetingScorerInput {
  /** Raw "True"/"False" strings from CSV. */
  dcccTarget: string;
  nrccTarget: string;
  /** Optional — present for Senate races. */
  dsccTarget?: string;
  nrscTarget?: string;
  /**
   * Whether targeting data is available for this office.
   * When false, returns a null score so the composite scorer excludes this
   * dimension entirely and reweights the remaining dimensions.
   * Defaults to true for backwards compatibility.
   */
  dataAvailable?: boolean;
}

function parseFlag(raw: string | undefined): boolean {
  return /^true$/i.test(String(raw ?? "").trim());
}

/**
 * Score the targeting dimension using DCCC/NRCC (and DSCC/NRSC for Senate)
 * committee targeting flags.
 *
 * Both sides targeting: 100 — both parties consider this a priority race.
 * One side targeting:    70 — one party sees opportunity.
 * Neither targeting:     20 — safe seat, no national committee investment.
 *
 * When dataAvailable is false (e.g. Governor, Lt. Governor, Attorney General,
 * Senate — offices where national committees don't publish targeting lists),
 * returns score: null so the composite scorer excludes this dimension.
 */
export function scoreTargeting(input: TargetingScorerInput): SubScore {
  if (input.dataAvailable === false) {
    return { score: null, confidence: 0, detail: { key: "n_a" } };
  }

  const dem = parseFlag(input.dcccTarget) || parseFlag(input.dsccTarget);
  const rep = parseFlag(input.nrccTarget) || parseFlag(input.nrscTarget);

  let key: "both" | "dccc" | "nrcc" | "none";
  let score: number;

  if (dem && rep) {
    key = "both";
    score = 100;
  } else if (dem) {
    key = "dccc";
    score = 70;
  } else if (rep) {
    key = "nrcc";
    score = 70;
  } else {
    key = "none";
    score = 20;
  }

  return {
    score,
    confidence: 1.0,
    detail: { key, demTarget: dem, repTarget: rep },
  };
}
