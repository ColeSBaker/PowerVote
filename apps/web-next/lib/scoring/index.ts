export type { SubScore, ScoreWeights, CompositeScore, ScoreBand } from "./types";
export { DEFAULT_WEIGHTS, scoreWeightsSchema } from "./types";

export type { IncumbencyScorerInput } from "./incumbency-scorer";
export { scoreIncumbency } from "./incumbency-scorer";

export type { MarketScorerInput } from "./market-scorer";
export { scoreMarket } from "./market-scorer";

export type { PollingScorerInput, RatingBreakdownEntry } from "./polling-scorer";
export { scorePolling } from "./polling-scorer";

export type { TargetingScorerInput } from "./targeting-scorer";
export { scoreTargeting } from "./targeting-scorer";

export type { CompositeInput } from "./composite";
export { computeCompositeScore } from "./composite";
