import { z } from "zod";

export const officeSchema = z.enum(["us_house", "us_senate", "us_governor", "us_lieutenant_governor", "us_attorney_general"]);
export type Office = z.infer<typeof officeSchema>;
export const mapModeSchema = z.enum(["district", "statewide"]);
export type MapMode = z.infer<typeof mapModeSchema>;

export const electionViewSchema = z.enum(["general", "primary"]);
export type ElectionView = z.infer<typeof electionViewSchema>;

export const colorModeSchema = z.enum([
  "contention",
  "incumbent",
  "market_favorite",
  "polling_proxy",
  "targeting",
  "powervote",
  "primary_status",
  "primary_kalshi",
  "primary_contention_dem",
  "primary_contention_rep",
  "primary_contention_np",
  "primary_kalshi_dem",
  "primary_kalshi_rep",
  "primary_kalshi_np",
  "kalshi_integrity_general",
  "kalshi_integrity_primary",
  "kalshi_integrity_primary_dem",
  "kalshi_integrity_primary_rep",
  "kalshi_integrity_primary_np",
]);
export type ColorMode = z.infer<typeof colorModeSchema>;

export const partyCodeSchema = z.enum(["DEM", "REP", "IND", "LIB", "GRE", "OTH", "NP"]);
export type PartyCode = z.infer<typeof partyCodeSchema>;

export const mapDistrictSchema = z.object({
  seatId: z.string(),
  districtLabel: z.string(),
  state: z.string(),
  colorKey: z.string(),
  colorHex: z.string(),
  contentionKey: z.string().nullable(),
  incumbentParty: partyCodeSchema.nullable(),
  marketFavoriteParty: partyCodeSchema.nullable(),
  pollingProxyParty: partyCodeSchema.nullable(),
  targetingKey: z.enum(["both", "dccc", "nrcc", "none", "n_a"]),
  primaryState: z.enum(["ongoing_primary", "ongoing_runoff", "complete", "none"]),
  dcccTarget: z.boolean(),
  nrccTarget: z.boolean(),
  dsccTarget: z.boolean().optional().default(false),
  nrscTarget: z.boolean().optional().default(false),
  candidateCount: z.number().int().nonnegative(),
});

export const mapDistrictsResponseSchema = z.object({
  office: officeSchema,
  mapMode: mapModeSchema,
  electionView: electionViewSchema,
  colorMode: colorModeSchema,
  snapshotDate: z.string(),
  updatedAt: z.string(),
  sourceAttribution: z.array(z.string()),
  legend: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      colorHex: z.string(),
    }),
  ),
  districts: z.array(mapDistrictSchema),
  featureCollection: z.object({
    type: z.literal("FeatureCollection"),
    features: z.array(z.object({ type: z.literal("Feature"), properties: z.record(z.string(), z.any()), geometry: z.any() })),
  }),
});
export type MapDistrictsResponse = z.infer<typeof mapDistrictsResponseSchema>;

export const districtCandidateSchema = z.object({
  ballotpediaName: z.string(),
  party: partyCodeSchema.nullable(),
  status: z.string(),
  primaryId: z.string().nullable(),
  runoffId: z.string().nullable(),
  financeReceipts: z.number().nullable(),
  financeCashOnHand: z.number().nullable(),
  bestGeneralOdds: z.number().nullable(),
});

const generalPartyLaneSchema = z.object({
  party: partyCodeSchema,
  hasNominee: z.boolean(),
  nomineeName: z.string().nullable(),
  primaryOngoing: z.boolean(),
  primaryDate: z.string().nullable(),
  primaryCandidates: z.array(z.string()),
  runoffOngoing: z.boolean(),
  runoffDate: z.string().nullable(),
  runoffCandidates: z.array(z.string()),
  visibleCandidates: z.array(
    z.object({
      name: z.string(),
      context: z.enum(["general", "runoff"]),
      odds: z.number().nullable(),
      eliminated: z.boolean().default(false),
    }),
  ),
});

const unifiedCandidateSchema = z.object({
  name: z.string(),
  stage: z.enum(["nominee", "runoff", "candidate", "general"]),
  primaryOdds: z.number().nullable(),
  generalOdds: z.number().nullable(),
  eliminated: z.boolean().default(false),
  nameUnmatched: z.boolean().default(false),
  partyAffiliation: z.string().nullable().optional(),
});

export const unifiedPartyLaneSchema = z.object({
  party: partyCodeSchema,
  hasNominee: z.boolean(),
  nomineeName: z.string().nullable(),
  primaryOngoing: z.boolean(),
  runoffOngoing: z.boolean(),
  primaryDate: z.string().nullable(),
  runoffDate: z.string().nullable(),
  partyGeneralOdds: z.number().nullable(),
  candidates: z.array(unifiedCandidateSchema),
});
export type UnifiedPartyLane = z.infer<typeof unifiedPartyLaneSchema>;

export const districtDetailResponseSchema = z.object({
  office: officeSchema,
  seatId: z.string(),
  electionView: electionViewSchema,
  snapshotDate: z.string(),
  updatedAt: z.string(),
  sourceAttribution: z.array(z.string()),
  districtLabel: z.string(),
  ballotpediaUrl: z.string().optional(),
  generalElection: z.object({
    partyLanes: z.array(generalPartyLaneSchema),
    kalshiOnlyCandidates: z.array(z.object({ name: z.string(), odds: z.number().nullable() })).default([]),
  }),
  incumbencyAndControl: z.object({
    controllingParty: partyCodeSchema.nullable(),
    incumbentIndividual: z.string(),
    openSeat: z.boolean(),
    departureReason: z.string(),
    departedIncumbentParty: partyCodeSchema.nullable(),
  }),
  competitiveness: z.object({
    pollingStatus: z.object({
      summary: z.string(),
      latestDate: z.string().nullable(),
      sourceCount: z.number().int().nonnegative(),
      leadingParty: partyCodeSchema.nullable(),
      sources: z.array(
        z.object({
          outlet: z.string(),
          rating: z.string(),
          date: z.string().nullable(),
        }),
      ),
    }),
    kalshiGeneralOdds: z.object({
      favoriteParty: partyCodeSchema.nullable(),
      favoriteLabel: z.string().nullable(),
      favoriteOdds: z.number().nullable(),
      oddsMap: z.record(z.string(), z.number()),
    }),
    targeting: z.object({
      key: z.enum(["both", "dccc", "nrcc", "none", "n_a"]),
      dcccTarget: z.boolean(),
      nrccTarget: z.boolean(),
      dsccTarget: z.boolean().optional().default(false),
      nrscTarget: z.boolean().optional().default(false),
    }),
  }),
  primaryElection: z.object({
    primaryState: z.enum(["ongoing_primary", "ongoing_runoff", "complete", "none"]),
    primaryType: z.enum(["partisan_binary", "top_two", "top_four", "jungle"]).default("partisan_binary"),
    advanceCount: z.number().int().min(1).default(1),
    kalshiOnlyPrimaryCandidates: z.array(z.object({ name: z.string(), odds: z.number() })).default([]),
    parties: z.array(
      z.object({
        party: partyCodeSchema,
        hasPrimaryMarket: z.boolean(),
        candidates: z.array(
          z.object({
            name: z.string(),
            status: z.string(),
            stage: z.enum(["runoff", "nominee", "candidate", "general"]),
            odds: z.number().nullable(),
            eliminated: z.boolean(),
            kalshiMarketUrl: z.string().nullable(),
          }),
        ),
      }),
    ),
  }),
  unifiedElection: z
    .object({
      parties: z.array(unifiedPartyLaneSchema),
      kalshiOnlyCandidates: z
        .array(
          z.object({
            name: z.string(),
            primaryOdds: z.number().nullable(),
            generalOdds: z.number().nullable(),
          }),
        )
        .default([]),
    })
    .optional(),
  // Deprecated v1 fields kept temporarily for additive backwards compatibility.
  electionStatus: z.object({
    generalStatus: z.string(),
    primaryState: z.enum(["ongoing_primary", "ongoing_runoff", "complete", "none"]),
    primaryStatusD: z.string().nullable(),
    primaryStatusR: z.string().nullable(),
    primaryStatusNP: z.string().nullable(),
    runoffCount: z.number().int().nonnegative(),
  }),
  mapSignals: z.object({
    contentionKey: z.string().nullable(),
    incumbentParty: partyCodeSchema.nullable(),
    marketFavoriteParty: partyCodeSchema.nullable(),
    pollingProxyParty: partyCodeSchema.nullable(),
    dcccTarget: z.boolean(),
    nrccTarget: z.boolean(),
    dsccTarget: z.boolean().optional().default(false),
    nrscTarget: z.boolean().optional().default(false),
  }),
  candidates: z.object({
    all: z.array(districtCandidateSchema),
    general: z.array(districtCandidateSchema),
    primary: z.array(districtCandidateSchema),
    runoff: z.array(districtCandidateSchema),
  }),
});
export type DistrictDetailResponse = z.infer<typeof districtDetailResponseSchema>;

const breakdownEntrySchema = z.object({
  score: z.number().nullable(),
  weight: z.number(),
  confidence: z.number().optional(),
});

export const competitivenessBreakdownSchema = z.object({
  market: breakdownEntrySchema,
  pollingProxy: breakdownEntrySchema,
  targeting: breakdownEntrySchema,
  /** New — incumbency subscore. Optional for backwards-compat with existing serialised responses. */
  incumbency: breakdownEntrySchema.optional(),
});

/** Extended schema for endpoints that expose the full four-dimension breakdown. */
export const competitivenessBreakdownExtendedSchema = competitivenessBreakdownSchema.extend({
  incumbency: breakdownEntrySchema,
  effectiveWeights: z
    .object({
      incumbency: z.number(),
      market: z.number(),
      polling: z.number(),
      targeting: z.number(),
    })
    .optional(),
});

export const powerVoteElectionSchema = z.object({
  seatId: z.string(),
  electionKind: z.enum(["general", "primary", "runoff"]),
  office: officeSchema,
  score: z.number().nullable(),
  band: z.enum(["Safe", "Lean", "Competitive", "Toss-up", "Unknown", "Uncontested"]),
  reason: z.string(),
  ballotpediaUrl: z.string().optional(),
  breakdown: competitivenessBreakdownSchema,
  mapSignals: z.object({
    marketFavoriteParty: partyCodeSchema.nullable(),
    pollingProxyParty: partyCodeSchema.nullable(),
    dcccTarget: z.boolean(),
    nrccTarget: z.boolean(),
    dsccTarget: z.boolean().optional().default(false),
    nrscTarget: z.boolean().optional().default(false),
    primaryState: z.enum(["ongoing_primary", "ongoing_runoff", "complete", "none"]),
  }),
});

export const powerVoteGeneralOverviewSchema = z.object({
  controllingParty: partyCodeSchema.nullable(),
  incumbentIndividual: z.string(),
  isOpen: z.boolean(),
  departureReason: z.string(),
  kalshiGeneral: z.object({
    hasMarket: z.boolean(),
    favoriteParty: partyCodeSchema.nullable(),
    favoriteLabel: z.string().nullable(),
    oddsMap: z.record(z.string(), z.number()),
  }),
  pollingProxy: z.object({
    summary: z.string(),
    latestDate: z.string().nullable(),
    leadingParty: partyCodeSchema.nullable(),
    sources: z.array(
      z.object({
        outlet: z.string(),
        rating: z.string(),
        date: z.string().nullable(),
      }),
    ),
  }),
  targeting: z.object({
    key: z.enum(["both", "dccc", "nrcc", "none", "n_a"]),
    label: z.enum(["Both", "DCCC", "NRCC", "None", "N/A"]),
    dcccTarget: z.boolean(),
    nrccTarget: z.boolean(),
    dsccTarget: z.boolean().optional().default(false),
    nrscTarget: z.boolean().optional().default(false),
  }),
});

export const powerVotePrimarySummarySchema = z.object({
  party: partyCodeSchema,
  status: z.enum(["No Primary", "Upcoming", "In Progress", "Runoff Active", "Complete", "Unknown"]),
  kalshiPrimary: z.object({
    hasMarket: z.boolean(),
    marketCount: z.number().int().nonnegative(),
    marketTickers: z.array(z.string()),
    oddsMap: z.record(z.string(), z.number()),
  }),
  winner: z.string().nullable(),
  details: z.object({
    primaryDate: z.string().nullable(),
    runoffDate: z.string().nullable(),
    runoffCandidates: z.array(z.string()),
    primaryCandidates: z.array(z.string()),
    rawStatuses: z.array(z.string()),
  }),
});

export const powerVoteResponseSchema = z.object({
  office: officeSchema,
  snapshotDate: z.string(),
  updatedAt: z.string(),
  sourceAttribution: z.array(z.string()),
  address: z.object({
    input: z.string(),
    normalized: z.string().nullable(),
    latitude: z.number().nullable(),
    longitude: z.number().nullable(),
    seatId: z.string().nullable(),
  }),
  elections: z.array(powerVoteElectionSchema),
  generalOverview: powerVoteGeneralOverviewSchema.optional(),
  primaries: z.array(powerVotePrimarySummarySchema).optional(),
});
export type PowerVoteResponse = z.infer<typeof powerVoteResponseSchema>;

export const powerVoteSeatOptionsResponseSchema = z.object({
  office: officeSchema,
  snapshotDate: z.string(),
  updatedAt: z.string(),
  states: z.array(
    z.object({
      stateCode: z.string().length(2),
      seats: z.array(
        z.object({
          seatId: z.string(),
          seatLabel: z.string(),
        }),
      ),
    }),
  ),
});
export type PowerVoteSeatOptionsResponse = z.infer<typeof powerVoteSeatOptionsResponseSchema>;

export const powerVoteCompareResponseSchema = z.object({
  office: officeSchema,
  snapshotDate: z.string(),
  updatedAt: z.string(),
  sourceAttribution: z.array(z.string()),
  results: z.array(powerVoteResponseSchema),
});
export type PowerVoteCompareResponse = z.infer<typeof powerVoteCompareResponseSchema>;

export const powerVoteAllLocationSchema = z.object({
  label: z.string(),
  resolvedContext: z.object({
    stateCode: z.string().length(2),
    houseSeatId: z.string(),
    senateSeatIds: z.array(z.string()),
    governorSeatIds: z.array(z.string()),
    lieutenantGovernorSeatIds: z.array(z.string()),
    attorneyGeneralSeatIds: z.array(z.string()),
  }),
  house: powerVoteResponseSchema,
  senate: z.array(powerVoteResponseSchema),
  governor: z.array(powerVoteResponseSchema),
  lieutenantGovernor: z.array(powerVoteResponseSchema),
  attorneyGeneral: z.array(powerVoteResponseSchema),
  elections: z.array(powerVoteElectionSchema),
});

export const powerVoteAllResponseSchema = z.object({
  snapshotDate: z.string(),
  updatedAt: z.string(),
  sourceAttribution: z.array(z.string()),
  locations: z.array(powerVoteAllLocationSchema),
});
export type PowerVoteAllResponse = z.infer<typeof powerVoteAllResponseSchema>;

const mobileSeatSummarySchema = z.object({
  seatId: z.string(),
  state: z.string().length(2),
  generalStatus: z.string(),
  incumbentParty: z.string().nullable(),
  primaryStatusD: z.string().nullable(),
  primaryStatusR: z.string().nullable(),
  primaryStatusNP: z.string().nullable(),
  kalshiGeneralOddsMap: z.string(),
});

const mobileCandidateOddsSchema = z.object({
  seatId: z.string(),
  ballotpediaName: z.string(),
  party: z.string(),
  bestPrimaryOdds: z.number().nullable(),
  bestGeneralOdds: z.number().nullable(),
});

const mobileOfficeDataSchema = z.object({
  seatSummaries: z.array(mobileSeatSummarySchema),
  candidateOdds: z.array(mobileCandidateOddsSchema),
});

export const mobileBootstrapResponseSchema = z.object({
  snapshotId: z.string(),
  snapshotDate: z.string(),
  schemaVersion: z.string(),
  etag: z.string(),
  generatedAt: z.string(),
  data: z.object({
    us_house: mobileOfficeDataSchema,
    us_senate: mobileOfficeDataSchema,
  }),
});

export const mobileDeltaResponseSchema = z.object({
  snapshotId: z.string(),
  snapshotDate: z.string(),
  schemaVersion: z.string(),
  etag: z.string(),
  generatedAt: z.string(),
  since: z.string().nullable(),
  hasChanges: z.boolean(),
  changes: z.object({
    us_house: mobileOfficeDataSchema,
    us_senate: mobileOfficeDataSchema,
  }),
});

export const mobileSeatResponseSchema = z.object({
  snapshotId: z.string(),
  snapshotDate: z.string(),
  schemaVersion: z.string(),
  etag: z.string(),
  generatedAt: z.string(),
  data: z.object({
    office: officeSchema,
    seat: mobileSeatSummarySchema,
    candidates: z.array(mobileCandidateOddsSchema),
  }),
});
