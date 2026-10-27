import {
  colorModeSchema,
  districtDetailResponseSchema,
  electionViewSchema,
  mapDistrictsResponseSchema,
  officeSchema,
  powerVoteAllResponseSchema,
  powerVoteCompareResponseSchema,
  powerVoteSeatOptionsResponseSchema,
  powerVoteResponseSchema,
} from "@/lib/domain/schemas";
import { isAttorneyGeneralSeatId, isGovernorSeatId, isHouseSeatId, isLtGovernorSeatId, isSenateSeatId, parseBooleanText, parseJsonObject } from "@/lib/server/csv";
import { ClientInputError } from "@/lib/server/errors";
import {
  loadCanonicalDataBundleByOffice,
  loadCanonicalDataBundleForMapByOffice,
  type CanonicalDataBundle,
} from "@/lib/server/data-source";
import { asFeatureCollection, featureSeatId, findSeatByPoint, type GeoFeature } from "@/lib/server/geo";
import { geocodeAddressWithCensus, type CensusGeocodeResult } from "@/lib/server/geocoder";
import { normalizeAddressForGeocoder } from "@/lib/server/address-normalization";
import {
  candidateCountFromGeneralRow,
  computeWeightedCompetitiveness,
  getPrimaryKalshiMarketKey,
  getPollingProxyPartyAndScore,
  getPrimaryState,
  getTargetingKey,
  mapColorForGeneralMode,
  mapColorForKalshiIntegrity,
  mapColorForPowervoteBand,
  mapColorForContention,
  mapColorForPartyPrimaryContention,
  mapColorForPrimaryKalshi,
  parseCandidateOdds,
  parseIncumbentParty,
  scoreBand,
  targetingDataAvailable,
} from "@/lib/server/metrics";
import { buildDetailEntities, inferOpenSeat, resolveMarketFavoriteParty } from "@/lib/server/district-detail";
import { buildStateSeatOptions, normalizeRequestedSeatId } from "@/lib/server/powervote-seat-options";
import { buildPowerVoteDescriptiveContext } from "@/lib/server/powervote-descriptive";
import type { Office } from "@/lib/domain/schemas";
import { getPowerVoteEditionProfile } from "@/lib/server/powervote-editions";
import { lookupZipcode } from "@/lib/server/zipcode-lookup";

type OfficeInput = string | undefined;
type ElectionViewInput = string | undefined;
type ColorModeInput = string | undefined;
type MapDistrictsTimingCollector = (timing: {
  loadMs: number;
  transformMs: number;
  schemaMs: number;
  totalMs: number;
  cacheHit: boolean;
}) => void;
type PowerVoteTimingCollector = (timing: {
  loadMs: number;
  resolveMs: number;
  buildMs: number;
  schemaMs: number;
  totalMs: number;
}) => void;
type MapResponseCacheEntry = {
  revision: string;
  payload: ReturnType<typeof mapDistrictsResponseSchema.parse>;
  expiresAt: number;
};

const mapDistrictsResponseCache = new Map<string, MapResponseCacheEntry>();
const MAP_DISTRICTS_CACHE_TTL_MS = 30_000;

export function resetMapDistrictsResponseCacheForTesting() {
  mapDistrictsResponseCache.clear();
}

function normalizeOffice(input: OfficeInput) {
  return officeSchema.parse(input ?? "us_house");
}

function normalizeElectionView(input: ElectionViewInput) {
  return electionViewSchema.parse(input ?? "general");
}

function normalizeColorMode(input: ColorModeInput, electionView: "general" | "primary") {
  const fallback = electionView === "primary" ? "primary_status" : "incumbent";
  const parsed = colorModeSchema.parse(input ?? fallback);
  if (electionView === "primary") {
    const primaryModes = [
      "primary_status", "primary_kalshi",
      "primary_contention_dem", "primary_contention_rep", "primary_contention_np",
      "primary_kalshi_dem", "primary_kalshi_rep", "primary_kalshi_np",
      "kalshi_integrity_primary",
      "kalshi_integrity_primary_dem", "kalshi_integrity_primary_rep", "kalshi_integrity_primary_np",
    ] as const;
    return primaryModes.includes(parsed as (typeof primaryModes)[number]) ? parsed : "primary_status";
  }
  if (parsed === "primary_status" || parsed === "primary_kalshi" || parsed === "kalshi_integrity_primary") {
    return "incumbent";
  }
  return parsed;
}

function buildLegend(colorMode: string, electionView: "general" | "primary", office: Office) {
  const demCommitteeLabel = office === "us_senate" ? "DSCC" : office === "us_governor" || office === "us_lieutenant_governor" || office === "us_attorney_general" ? "DGA" : "DCCC";
  const repCommitteeLabel = office === "us_senate" ? "NRSC" : office === "us_governor" || office === "us_lieutenant_governor" || office === "us_attorney_general" ? "RGA" : "NRCC";
  
  let legend: Array<{ key: string; label: string; colorHex: string }>;
  
  if (electionView === "primary") {
    if (colorMode === "primary_kalshi") {
      legend = [
        { key: "primary_market_both", label: "Primary markets for both DEM and REP", colorHex: "#111827" },
        { key: "primary_market_dem", label: "Primary market for DEM lane", colorHex: "#1e40af" },
        { key: "primary_market_rep", label: "Primary market for REP lane", colorHex: "#991b1b" },
        { key: "primary_market_none", label: "No DEM/REP primary market", colorHex: "#d4d4d8" },
      ];
    } else if (colorMode === "kalshi_integrity_primary" || colorMode === "kalshi_integrity_primary_dem" || colorMode === "kalshi_integrity_primary_rep" || colorMode === "kalshi_integrity_primary_np") {
      legend = [
        { key: "integrity_pass",               colorHex: "#10b981", label: "No Kalshi Error" },
        { key: "integrity_out_of_band",        colorHex: "#ef4444", label: "Kalshi Error (Sum out of Band)" },
        { key: "integrity_sum_mismatch",       colorHex: "#f97316", label: "Kalshi Error (Sum Status Mismatch)" },
        { key: "integrity_missing_sum_status", colorHex: "#eab308", label: "Kalshi Error (Missing Sum Status)" },
        { key: "integrity_missing_odds_map",   colorHex: "#8b5cf6", label: "Kalshi Error (Markets but No Odds Map)" },
        { key: "integrity_multiple",           colorHex: "#9f1239", label: "Multiple Kalshi Errors" },
        { key: "integrity_no_data",            colorHex: "#d1d5db", label: "No Kalshi Market" },
      ];
    } else if (colorMode === "primary_kalshi_dem") {
      legend = [
        { key: "primary_market_dem",  label: "DEM primary market", colorHex: "#1e40af" },
        { key: "primary_market_none", label: "No DEM primary market", colorHex: "#d4d4d8" },
      ];
    } else if (colorMode === "primary_kalshi_rep") {
      legend = [
        { key: "primary_market_rep",  label: "REP primary market", colorHex: "#991b1b" },
        { key: "primary_market_none", label: "No REP primary market", colorHex: "#d4d4d8" },
      ];
    } else if (colorMode === "primary_kalshi_np") {
      legend = [
        { key: "primary_market_np",   label: "NP primary market",  colorHex: "#7c3aed" },
        { key: "primary_market_none", label: "No NP primary market", colorHex: "#d4d4d8" },
      ];
    } else if (colorMode === "primary_contention_dem" || colorMode === "primary_contention_rep" || colorMode === "primary_contention_np") {
      const party = colorMode === "primary_contention_dem" ? "DEM" : colorMode === "primary_contention_rep" ? "REP" : "NP";
      legend = [
        { key: "crowded",     label: `${party} crowded primary (3+ candidates)`, colorHex: "#7c3aed" },
        { key: "contested",   label: `${party} contested primary`,               colorHex: "#0f766e" },
        { key: "runoff",      label: `${party} primary in runoff`,               colorHex: "#f59e0b" },
        { key: "complete",    label: `${party} primary complete`,                colorHex: "#10b981" },
        { key: "no_election", label: `No ${party} primary`,                      colorHex: "#ffffff" },
      ];
    } else {
      legend = [
        { key: "contested",   label: "Contested primary",   colorHex: "#0f766e" },
        { key: "uncontested", label: "Uncontested primary", colorHex: "#000000" },
        { key: "no_election", label: "No primary",          colorHex: "#ffffff" },
      ];
    }
  } else if (colorMode === "incumbent") {
    legend = [
      { key: "incumbent_dem",      label: "Dem Control",             colorHex: "#1d4ed8" },
      { key: "incumbent_dem_open", label: "Dem Control (Open Seat)", colorHex: "#93c5fd" },
      { key: "incumbent_rep",      label: "Rep Control",             colorHex: "#b91c1c" },
      { key: "incumbent_rep_open", label: "Rep Control (Open Seat)", colorHex: "#fca5a5" },
      { key: "incumbent_other",    label: "Unknown Party Control",   colorHex: "#78716c" },
    ];
  } else if (colorMode === "market_favorite") {
    legend = [
      { key: "market_dem", label: "Market favorite: DEM", colorHex: "#2563eb" },
      { key: "market_rep", label: "Market favorite: REP", colorHex: "#dc2626" },
      { key: "market_unknown", label: "No clear market favorite", colorHex: "#9ca3af" },
    ];
  } else if (colorMode === "polling_proxy") {
    legend = [
      { key: "poll_dem", label: "Polling proxy: DEM", colorHex: "#3b82f6" },
      { key: "poll_rep", label: "Polling proxy: REP", colorHex: "#ef4444" },
      { key: "poll_tossup", label: "Polling proxy: Toss-up", colorHex: "#111827" },
      { key: "poll_unknown", label: "No polling proxy", colorHex: "#a8a29e" },
    ];
  } else if (colorMode === "targeting") {
    legend = [
      { key: "target_both", label: "Both committees targeting", colorHex: "#111827" },
      { key: "target_dccc", label: `${demCommitteeLabel} target`, colorHex: "#1e40af" },
      { key: "target_nrcc", label: `${repCommitteeLabel} target`, colorHex: "#991b1b" },
      { key: "target_none", label: "No national targeting flag", colorHex: "#d4d4d8" },
    ];
  } else if (colorMode === "powervote") {
    legend = [
      { key: "pv_tossup",      label: "Toss-up",     colorHex: "#c0392b" },
      { key: "pv_competitive", label: "Competitive",  colorHex: "#e67e22" },
      { key: "pv_lean",        label: "Lean",         colorHex: "#ca8a04" },
      { key: "pv_safe",        label: "Safe",         colorHex: "#94a3b8" },
      { key: "pv_uncontested", label: "Uncontested",  colorHex: "#ffffff" },
      { key: "pv_unknown",     label: "Unknown",      colorHex: "#d1d5db" },
    ];
  } else if (colorMode === "kalshi_integrity_general" || colorMode === "kalshi_integrity_primary") {
    legend = [
      { key: "integrity_pass",              colorHex: "#10b981", label: "No Kalshi Error" },
      { key: "integrity_out_of_band",       colorHex: "#ef4444", label: "Kalshi Error (Sum out of Band)" },
      { key: "integrity_sum_mismatch",      colorHex: "#f97316", label: "Kalshi Error (Sum Status Mismatch)" },
      { key: "integrity_missing_sum_status",colorHex: "#eab308", label: "Kalshi Error (Missing Sum Status)" },
      { key: "integrity_missing_odds_map",  colorHex: "#8b5cf6", label: "Kalshi Error (Markets but No Odds Map)" },
      { key: "integrity_multiple",          colorHex: "#9f1239", label: "Multiple Kalshi Errors" },
      { key: "integrity_no_data",           colorHex: "#d1d5db", label: "No Kalshi Market" },
    ];
  } else {
    legend = [
      { key: "contested",   label: "Contested",   colorHex: "#0f766e" },
      { key: "uncontested", label: "Uncontested", colorHex: "#000000" },
      { key: "no_election", label: "No election", colorHex: "#ffffff" },
    ];
  }

  // For statewide maps, add entry for states without races in this cycle
  if (office === "us_senate") {
    legend.push({ key: "no_data", label: "No 2026 Senate race", colorHex: "#ffffff" });
  } else if (office === "us_governor") {
    legend.push({ key: "no_data", label: "No 2026 Governor race", colorHex: "#ffffff" });
  } else if (office === "us_lieutenant_governor") {
    legend.push({ key: "no_data", label: "No 2026 Lt. Governor race", colorHex: "#ffffff" });
  } else if (office === "us_attorney_general") {
    legend.push({ key: "no_data", label: "No 2026 Attorney General race", colorHex: "#ffffff" });
  }

  return legend;
}

function targetingFlagsForOffice(generalRow: Record<string, string>, office: Office) {
  if (office === "us_senate") {
    return {
      dcccTarget: parseBooleanText(generalRow.dscc_target),
      nrccTarget: parseBooleanText(generalRow.nrsc_target),
      dsccTarget: parseBooleanText(generalRow.dscc_target),
      nrscTarget: parseBooleanText(generalRow.nrsc_target),
    };
  }
  return {
    dcccTarget: parseBooleanText(generalRow.dccc_target),
    nrccTarget: parseBooleanText(generalRow.nrcc_target),
    dsccTarget: false,
    nrscTarget: false,
  };
}

function isStatewideOffice(office: Office): boolean {
  return office === "us_senate" || office === "us_governor" || office === "us_lieutenant_governor" || office === "us_attorney_general";
}

function cloneFeatureWithSeat(feature: GeoFeature, seatId: string, fillColor: string, colorKey: string) {
  const state = seatId.split("-")[0];
  return {
    ...feature,
    properties: {
      ...(feature.properties || {}),
      seatId,
      state,
      fillColor,
      colorKey,
    },
  };
}

function buildOfficeFeatureCollection(args: {
  office: Office;
  geometryGeoJson: Record<string, unknown>;
  districtBySeat: Map<string, { seatId: string; state: string; colorHex: string; colorKey: string }>;
}) {
  const geo = asFeatureCollection(args.geometryGeoJson);
  if (!isStatewideOffice(args.office)) {
    return geo.features
      .map((feature) => {
        const seatId = featureSeatId(feature);
        if (!seatId) return null;
        const metric = args.districtBySeat.get(seatId);
        if (!metric) return null;
        return cloneFeatureWithSeat(feature, seatId, metric.colorHex, metric.colorKey);
      })
      .filter(Boolean);
  }

  // For Senate using districts: group by state and color all districts in the state uniformly
  const stateMetrics = new Map<string, { seatId: string; colorHex: string; colorKey: string }>();
  for (const metric of args.districtBySeat.values()) {
    // For Senate, all districts in a state get the same color based on state-level race
    if (!stateMetrics.has(metric.state)) {
      stateMetrics.set(metric.state, { seatId: metric.seatId, colorHex: metric.colorHex, colorKey: metric.colorKey });
    }
  }

  const features: GeoFeature[] = [];
  for (const feature of geo.features) {
    const state = String(feature.properties?.STATE_ABBR ?? feature.properties?.STUSPS ?? "").trim().toUpperCase();
    if (!state) continue;
    
    const metric = stateMetrics.get(state);
    if (metric) {
      // State has Senate race data - use state-level styling for all its districts
      features.push(cloneFeatureWithSeat(feature, metric.seatId, metric.colorHex, metric.colorKey));
    } else {
      // State has no Senate race data - show with yellow styling
      features.push(cloneFeatureWithSeat(feature, state, "#ffffff", "no_data"));
    }
  }
  return features;
}

export async function buildMapDistrictsResponse(args: {
  office?: OfficeInput;
  electionView?: ElectionViewInput;
  colorMode?: ColorModeInput;
  onTiming?: MapDistrictsTimingCollector;
}) {
  const totalStart = process.hrtime.bigint();
  let loadMs = 0;
  let transformMs = 0;
  let schemaMs = 0;
  const office = normalizeOffice(args.office);
  const electionView = normalizeElectionView(args.electionView);
  const colorMode = normalizeColorMode(args.colorMode, electionView);
  const cacheKey = `${office}:${electionView}:${colorMode}`;
  const now = Date.now();
  const cached = mapDistrictsResponseCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    args.onTiming?.({
      loadMs,
      transformMs,
      schemaMs,
      totalMs: Number(process.hrtime.bigint() - totalStart) / 1_000_000,
      cacheHit: true,
    });
    return cached.payload;
  }

  const loadStart = process.hrtime.bigint();
  const bundle = await loadCanonicalDataBundleForMapByOffice(office);
  loadMs = Number(process.hrtime.bigint() - loadStart) / 1_000_000;
  const revision = `${bundle.updatedAt}:${bundle.snapshotDate}`;
  if (cached && cached.revision === revision) {
    cached.expiresAt = now + MAP_DISTRICTS_CACHE_TTL_MS;
    args.onTiming?.({
      loadMs,
      transformMs,
      schemaMs,
      totalMs: Number(process.hrtime.bigint() - totalStart) / 1_000_000,
      cacheHit: true,
    });
    return cached.payload;
  }

  const transformStart = process.hrtime.bigint();
  const primaryBySeat = new Map<string, typeof bundle.primaryRows>();
  const runoffBySeat = new Map<string, typeof bundle.runoffRows>();
  const candidatesBySeat = new Map<string, typeof bundle.candidateRows>();

  for (const row of bundle.primaryRows) {
    const bucket = primaryBySeat.get(row.seat);
    if (bucket) { bucket.push(row); } else { primaryBySeat.set(row.seat, [row]); }
  }
  for (const row of bundle.runoffRows) {
    const bucket = runoffBySeat.get(row.seat);
    if (bucket) { bucket.push(row); } else { runoffBySeat.set(row.seat, [row]); }
  }
  for (const row of bundle.candidateRows) {
    const seat = row["2026 Seat"];
    const bucket = candidatesBySeat.get(seat);
    if (bucket) { bucket.push(row); } else { candidatesBySeat.set(seat, [row]); }
  }

  const districts = bundle.generalRows.map((generalRow) => {
    const incumbentParty = parseIncumbentParty(generalRow.incumbent_party);
    const openSeat = inferOpenSeat(generalRow);
    const marketFavoriteParty = resolveMarketFavoriteParty(generalRow.kalshi_general_odds_map, generalRow);
    const polling = getPollingProxyPartyAndScore(generalRow.general_election_race_ratings);
    const targetingKey = getTargetingKey(generalRow, office);
    const primaryRowsForSeat = primaryBySeat.get(generalRow.seat) ?? [];
    const primaryState = getPrimaryState(primaryRowsForSeat, runoffBySeat.get(generalRow.seat) ?? []);
    const targetingFlags = targetingFlagsForOffice(generalRow, office);

    const color =
      electionView === "primary"
        ? colorMode === "primary_kalshi"
          ? mapColorForPrimaryKalshi(getPrimaryKalshiMarketKey(generalRow))
          : colorMode === "primary_kalshi_dem"
            ? mapColorForPrimaryKalshi(
                (generalRow as typeof generalRow & { kalshi_primary_d?: string }).kalshi_primary_d
                  ? (() => { const m = parseJsonObject<Record<string, unknown>>((generalRow as typeof generalRow & { kalshi_primary_d?: string }).kalshi_primary_d); return m && Object.keys(m).length > 0 ? "dem" : "none"; })()
                  : "none"
              )
            : colorMode === "primary_kalshi_rep"
              ? mapColorForPrimaryKalshi(
                  (generalRow as typeof generalRow & { kalshi_primary_r?: string }).kalshi_primary_r
                    ? (() => { const m = parseJsonObject<Record<string, unknown>>((generalRow as typeof generalRow & { kalshi_primary_r?: string }).kalshi_primary_r); return m && Object.keys(m).length > 0 ? "rep" : "none"; })()
                    : "none"
                )
              : colorMode === "primary_contention_dem"
                ? (() => {
                    const status = (generalRow as typeof generalRow & { primary_status_d?: string }).primary_status_d ?? "none";
                    const count = (candidatesBySeat.get(generalRow.seat) ?? []).filter((r) => r.Party.toUpperCase() === "DEM").length;
                    return mapColorForPartyPrimaryContention(status, count);
                  })()
                : colorMode === "primary_contention_rep"
                  ? (() => {
                      const status = (generalRow as typeof generalRow & { primary_status_r?: string }).primary_status_r ?? "none";
                      const count = (candidatesBySeat.get(generalRow.seat) ?? []).filter((r) => r.Party.toUpperCase() === "REP").length;
                      return mapColorForPartyPrimaryContention(status, count);
                    })()
                  : colorMode === "primary_contention_np"
                    ? (() => {
                        const status = (generalRow as typeof generalRow & { primary_status_np?: string }).primary_status_np ?? "none";
                        const count = (candidatesBySeat.get(generalRow.seat) ?? []).filter((r) => r.Party.toUpperCase() === "NP").length;
                        return mapColorForPartyPrimaryContention(status, count);
                      })()
                    : colorMode === "primary_kalshi_np"
                      ? (() => {
                          const npRows = primaryRowsForSeat.filter((r) => r.party.toUpperCase() === "NP");
                          const hasMarket = npRows.some((r) => { const m = parseJsonObject<Record<string, unknown>>(r.kalshi_primary_odds_map); return !!m && Object.keys(m).length > 0; });
                          return hasMarket ? { key: "primary_market_np", colorHex: "#7c3aed" } : { key: "primary_market_none", colorHex: "#d4d4d8" };
                        })()
                      : colorMode === "kalshi_integrity_primary_dem"
                        ? (() => {
                            const demRows = primaryRowsForSeat.filter((r) => r.party.toUpperCase() === "DEM");
                            const failRow = demRows.find((r) => r.kalshi_integrity_passed === "False");
                            return mapColorForKalshiIntegrity(failRow ?? demRows[0] ?? {});
                          })()
                        : colorMode === "kalshi_integrity_primary_rep"
                          ? (() => {
                              const repRows = primaryRowsForSeat.filter((r) => r.party.toUpperCase() === "REP");
                              const failRow = repRows.find((r) => r.kalshi_integrity_passed === "False");
                              return mapColorForKalshiIntegrity(failRow ?? repRows[0] ?? {});
                            })()
                          : colorMode === "kalshi_integrity_primary_np"
                            ? (() => {
                                const npRows = primaryRowsForSeat.filter((r) => r.party.toUpperCase() === "NP");
                                const failRow = npRows.find((r) => r.kalshi_integrity_passed === "False");
                                return mapColorForKalshiIntegrity(failRow ?? npRows[0] ?? {});
                              })()
                      : colorMode === "kalshi_integrity_primary"
                        ? (() => {
                            const failRow = primaryRowsForSeat.find((r) => r.kalshi_integrity_passed === "False");
                            return mapColorForKalshiIntegrity(failRow ?? primaryRowsForSeat[0] ?? {});
                          })()
                        : mapColorForContention(generalRow.primary_contention)
        : colorMode === "powervote"
          ? mapColorForPowervoteBand(computeWeightedCompetitiveness(generalRow, office).band)
          : colorMode === "kalshi_integrity_general"
            ? mapColorForKalshiIntegrity(generalRow)
            : mapColorForGeneralMode({
                colorMode:
                  colorMode === "primary_status"
                    ? "contention"
                    : (colorMode as "contention" | "incumbent" | "market_favorite" | "polling_proxy" | "targeting"),
                generalRow,
                incumbentParty,
                openSeat,
                marketParty: marketFavoriteParty,
                pollingParty: polling.party,
              targetingKey,
            });

    const candidateCount = candidatesBySeat.get(generalRow.seat)?.length ?? candidateCountFromGeneralRow(generalRow);
    return {
      seatId: generalRow.seat,
      districtLabel: generalRow.district || generalRow.seat,
      state: generalRow.seat.split("-")[0],
      colorKey: color.key,
      colorHex: color.colorHex,
      contentionKey: generalRow.general_status || null,
      incumbentParty,
      marketFavoriteParty,
      pollingProxyParty: polling.party,
      targetingKey,
      primaryState,
      dcccTarget: targetingFlags.dcccTarget,
      nrccTarget: targetingFlags.nrccTarget,
      dsccTarget: targetingFlags.dsccTarget,
      nrscTarget: targetingFlags.nrscTarget,
      candidateCount,
    };
  });

  const districtBySeat = new Map(districts.map((district) => [district.seatId, district]));
  const features = buildOfficeFeatureCollection({
    office,
    geometryGeoJson: bundle.geometryGeoJson,
    districtBySeat,
  });

  const payload = {
    office,
    mapMode: bundle.mapMode,
    electionView,
    colorMode,
    snapshotDate: bundle.snapshotDate,
    updatedAt: bundle.updatedAt,
    sourceAttribution: bundle.sourceAttribution,
    legend: buildLegend(colorMode, electionView, office),
    districts: districts.sort((left, right) => left.seatId.localeCompare(right.seatId)),
    featureCollection: {
      type: "FeatureCollection" as const,
      features,
    },
  };
  transformMs = Number(process.hrtime.bigint() - transformStart) / 1_000_000;

  const schemaStart = process.hrtime.bigint();
  const parsed = mapDistrictsResponseSchema.parse(payload);
  schemaMs = Number(process.hrtime.bigint() - schemaStart) / 1_000_000;
  mapDistrictsResponseCache.set(cacheKey, {
    revision,
    payload: parsed,
    expiresAt: Date.now() + MAP_DISTRICTS_CACHE_TTL_MS,
  });
  args.onTiming?.({
    loadMs,
    transformMs,
    schemaMs,
    totalMs: Number(process.hrtime.bigint() - totalStart) / 1_000_000,
    cacheHit: false,
  });
  return parsed;
}

export async function buildDistrictDetailResponse(args: {
  seatId: string;
  office?: OfficeInput;
  electionView?: ElectionViewInput;
  detailVersion?: "v1" | "v2";
}) {
  const office = normalizeOffice(args.office);
  const electionView = normalizeElectionView(args.electionView);
  const seatId = args.seatId.toUpperCase();
  const bundle = await loadCanonicalDataBundleByOffice(office);
  const generalRow = bundle.generalRows.find((row) => row.seat === seatId);
  if (!generalRow) {
    throw new ClientInputError(`No district record found for seat ${seatId}.`);
  }
  const primaryRows = bundle.primaryRows.filter((row) => row.seat === seatId);
  const runoffRows = bundle.runoffRows.filter((row) => row.seat === seatId);
  const departureRow = bundle.departureRows.find((row) => row.seat === seatId) ?? null;
  const candidates = bundle.candidateRows
    .filter((row) => row["2026 Seat"] === seatId)
    .map((row) => ({
      ballotpediaName: row.BallotpediaName,
      party: parseIncumbentParty(row.Party),
      status: row.Status,
      primaryId: row["Primary ID"] || null,
      runoffId: row.RunoffID || null,
      financeReceipts: parseCandidateOdds(row["Finance (Receipts)"]),
      financeCashOnHand: parseCandidateOdds(row["Finance (Cash in hand)"]),
      bestPrimaryOdds: parseCandidateOdds(row.KalshiBestPrimaryOdds),
      bestGeneralOdds: parseCandidateOdds(row.KalshiBestGeneralOdds),
    }));

  const polling = getPollingProxyPartyAndScore(generalRow.general_election_race_ratings);
  const primaryState = getPrimaryState(primaryRows, runoffRows);
  const targetingFlags = targetingFlagsForOffice(generalRow, office);
  const detailEntities = buildDetailEntities({
    seatId,
    generalRow,
    primaryRows,
    runoffRows,
    candidateRows: bundle.candidateRows.filter((row) => row["2026 Seat"] === seatId),
    departureRow,
    office,
  });
  const payload = {
    office,
    seatId,
    electionView,
    snapshotDate: bundle.snapshotDate,
    updatedAt: bundle.updatedAt,
    sourceAttribution: bundle.sourceAttribution,
    districtLabel: generalRow.district || seatId,
    ballotpediaUrl: generalRow.source_url || undefined,
    generalElection: detailEntities.generalElection,
    incumbencyAndControl: detailEntities.incumbencyAndControl,
    competitiveness: detailEntities.competitiveness,
    primaryElection: detailEntities.primaryElection,
    unifiedElection: detailEntities.unifiedElection,
    electionStatus: {
      generalStatus: generalRow.general_status,
      primaryState,
      primaryStatusD: generalRow.primary_status_d || null,
      primaryStatusR: generalRow.primary_status_r || null,
      primaryStatusNP: generalRow.primary_status_np || null,
      runoffCount: runoffRows.length,
    },
    mapSignals: {
      contentionKey: generalRow.general_status || null,
      incumbentParty: parseIncumbentParty(generalRow.incumbent_party),
      marketFavoriteParty: resolveMarketFavoriteParty(generalRow.kalshi_general_odds_map, generalRow),
      pollingProxyParty: polling.party,
      dcccTarget: targetingFlags.dcccTarget,
      nrccTarget: targetingFlags.nrccTarget,
      dsccTarget: targetingFlags.dsccTarget,
      nrscTarget: targetingFlags.nrscTarget,
    },
    candidates: {
      all: candidates,
      general: candidates.filter((candidate) => candidate.status.toLowerCase().startsWith("general")),
      primary: candidates.filter((candidate) => candidate.primaryId !== null),
      runoff: candidates.filter((candidate) => candidate.runoffId !== null),
    },
  };

  return districtDetailResponseSchema.parse(payload);
}

async function buildPowerVoteFromSeat(args: {
  seatId: string;
  office: Office;
  addressInput: string;
  normalizedAddress: string | null;
  latitude: number | null;
  longitude: number | null;
  bundle: CanonicalDataBundle;
}) {
  const { bundle } = args;
  const generalRow = bundle.generalRows.find((row) => row.seat === args.seatId);
  if (!generalRow) {
    return {
      office: args.office,
      snapshotDate: bundle.snapshotDate,
      updatedAt: bundle.updatedAt,
      sourceAttribution: bundle.sourceAttribution,
      address: {
        input: args.addressInput,
        normalized: args.normalizedAddress,
        latitude: args.latitude,
        longitude: args.longitude,
        seatId: args.seatId,
      },
      elections: [],
    };
  }

  const primaryRows = bundle.primaryRows.filter((row) => row.seat === args.seatId);
  const runoffRows = bundle.runoffRows.filter((row) => row.seat === args.seatId);
  const polling = getPollingProxyPartyAndScore(generalRow.general_election_race_ratings);
  const marketFavoriteParty = resolveMarketFavoriteParty(generalRow.kalshi_general_odds_map, generalRow);
  const primaryState = getPrimaryState(primaryRows, runoffRows);
  const targetingFlags = targetingFlagsForOffice(generalRow, args.office);
  const edition = getPowerVoteEditionProfile(args.office);
  const competitiveness = computeWeightedCompetitiveness(generalRow, args.office);
  const primaryScore =
    primaryState === "ongoing_primary"
      ? edition.primaryActiveScore
      : primaryState === "complete"
        ? edition.primaryCompleteScore
        : null;
  const runoffScore = primaryState === "ongoing_runoff" ? edition.runoffActiveScore : runoffRows.length ? edition.runoffKnownScore : null;
  const descriptive = buildPowerVoteDescriptiveContext({
    generalRow,
    primaryRows,
    runoffRows,
    candidateRows: bundle.candidateRows.filter((row) => row["2026 Seat"] === args.seatId),
    departureRow: bundle.departureRows.find((row) => row.seat === args.seatId) ?? null,
    office: args.office,
  });

  return {
    office: args.office,
    snapshotDate: bundle.snapshotDate,
    updatedAt: bundle.updatedAt,
    sourceAttribution: bundle.sourceAttribution,
    address: {
      input: args.addressInput,
      normalized: args.normalizedAddress,
      latitude: args.latitude,
      longitude: args.longitude,
      seatId: args.seatId,
    },
    generalOverview: descriptive.generalOverview,
    primaries: descriptive.primaries,
    elections: [
      {
        seatId: args.seatId,
        electionKind: "general" as const,
        office: args.office,
        score: competitiveness.score,
        band: competitiveness.band,
        reason: competitiveness.reason,
        ballotpediaUrl: generalRow.source_url || undefined,
        breakdown: competitiveness.breakdown,
        mapSignals: {
          marketFavoriteParty,
          pollingProxyParty: polling.party,
          dcccTarget: targetingFlags.dcccTarget,
          nrccTarget: targetingFlags.nrccTarget,
          dsccTarget: targetingFlags.dsccTarget,
          nrscTarget: targetingFlags.nrscTarget,
          primaryState,
        },
      },
      {
        seatId: args.seatId,
        electionKind: "primary" as const,
        office: args.office,
        score: primaryScore,
        band: scoreBand(primaryScore),
        reason:
          primaryState === "ongoing_primary"
            ? "Primary elections are active in this district."
            : primaryState === "complete"
              ? "Primary elections are complete in this district."
              : "No active primary election context in canonical rollups.",
        breakdown: {
          market: { score: null, weight: 0.6 },
          pollingProxy: { score: null, weight: 0.25 },
          targeting: { score: targetingDataAvailable(args.office) ? (targetingFlags.dcccTarget || targetingFlags.nrccTarget ? 70 : 20) : null, weight: 0.15 },
        },
        mapSignals: {
          marketFavoriteParty,
          pollingProxyParty: polling.party,
          dcccTarget: targetingFlags.dcccTarget,
          nrccTarget: targetingFlags.nrccTarget,
          dsccTarget: targetingFlags.dsccTarget,
          nrscTarget: targetingFlags.nrscTarget,
          primaryState,
        },
      },
      {
        seatId: args.seatId,
        electionKind: "runoff" as const,
        office: args.office,
        score: runoffScore,
        band: scoreBand(runoffScore),
        reason:
          primaryState === "ongoing_runoff"
            ? "Runoff election is active in this district."
            : runoffRows.length
              ? "Runoff record exists but is not active."
              : "No runoff election is currently indexed for this district.",
        breakdown: {
          market: { score: null, weight: 0.6 },
          pollingProxy: { score: null, weight: 0.25 },
          targeting: { score: targetingDataAvailable(args.office) ? (targetingFlags.dcccTarget || targetingFlags.nrccTarget ? 70 : 20) : null, weight: 0.15 },
        },
        mapSignals: {
          marketFavoriteParty,
          pollingProxyParty: polling.party,
          dcccTarget: targetingFlags.dcccTarget,
          nrccTarget: targetingFlags.nrccTarget,
          dsccTarget: targetingFlags.dsccTarget,
          nrscTarget: targetingFlags.nrscTarget,
          primaryState,
        },
      },
    ],
  };
}

type GeocodeFn = (address: string) => Promise<CensusGeocodeResult>;

async function geocodeWithNormalizationFallback(geocode: GeocodeFn, rawAddress: string): Promise<CensusGeocodeResult> {
  const first = await geocode(rawAddress);
  if (first.normalizedAddress || first.seatId || first.stateCode || (first.latitude !== null && first.longitude !== null)) {
    return first;
  }
  const normalized = normalizeAddressForGeocoder(rawAddress);
  if (!normalized.changed) return first;
  return geocode(normalized.normalizedForGeocoder);
}

function seatBelongsToOffice(seatId: string, office: Office): boolean {
  if (office === "us_senate") return isSenateSeatId(seatId);
  if (office === "us_governor") return isGovernorSeatId(seatId);
  if (office === "us_lieutenant_governor") return isLtGovernorSeatId(seatId);
  if (office === "us_attorney_general") return isAttorneyGeneralSeatId(seatId);
  return isHouseSeatId(seatId);
}

export async function buildPowerVoteResponse(args: {
  address?: string;
  seatId?: string;
  office?: OfficeInput;
  geocode?: GeocodeFn;
  onTiming?: PowerVoteTimingCollector;
}) {
  const totalStart = process.hrtime.bigint();
  const office = normalizeOffice(args.office);
  const loadStart = process.hrtime.bigint();
  const bundle = await loadCanonicalDataBundleByOffice(office);
  const loadMs = Number(process.hrtime.bigint() - loadStart) / 1_000_000;
  const resolveStart = process.hrtime.bigint();
  let resolvedSeatId: string | null = null;
  let normalizedAddress: string | null = null;
  let latitude: number | null = null;
  let longitude: number | null = null;
  let addressInput = "";

  if (args.seatId) {
    const normalizedSeatId = normalizeRequestedSeatId(args.seatId);
    if (!seatBelongsToOffice(normalizedSeatId, office)) {
      throw new ClientInputError(`seat_id ${normalizedSeatId} does not belong to office ${office}.`);
    }
    const hasSeat = bundle.generalRows.some((row) => row.seat === normalizedSeatId);
    if (!hasSeat) {
      throw new ClientInputError(`No district record found for seat ${normalizedSeatId}.`);
    }
    resolvedSeatId = normalizedSeatId;
    addressInput = normalizedSeatId;
    normalizedAddress = normalizedSeatId;
  } else if (args.address) {
    const geocode = args.geocode ?? geocodeAddressWithCensus;
    const geocoded = await geocodeWithNormalizationFallback(geocode, args.address);
    resolvedSeatId = office === "us_house" ? geocoded.seatId : null;
    normalizedAddress = geocoded.normalizedAddress;
    latitude = geocoded.latitude;
    longitude = geocoded.longitude;
    addressInput = args.address;

    if (office === "us_senate") {
      const stateCode = (geocoded.stateCode || geocoded.seatId?.split("-")[0] || "").toUpperCase();
      if (!stateCode) {
        throw new ClientInputError("Unable to determine state for Senate address lookup; provide seat_id.");
      }
      if (!geocoded.seatId) {
        throw new ClientInputError(`Multiple Senate contests found for state ${stateCode}; include seat_id.`);
      }
      const senateSeats = bundle.generalRows.filter((row) => row.seat.startsWith(`${stateCode}-SEN-`)).map((row) => row.seat);
      if (!senateSeats.length) {
        throw new ClientInputError(`No Senate contests found for state ${stateCode}.`);
      }
      if (senateSeats.length > 1) {
        throw new ClientInputError(`Multiple Senate contests found for state ${stateCode}; include seat_id.`);
      }
      resolvedSeatId = senateSeats[0];
    }

    if (office === "us_governor") {
      const stateCode = (geocoded.stateCode || geocoded.seatId?.split("-")[0] || "").toUpperCase();
      if (!stateCode) {
        throw new ClientInputError("Unable to determine state for Governor address lookup; provide seat_id.");
      }
      const govSeat = `${stateCode}-GOV`;
      if (!bundle.generalRows.some((row) => row.seat === govSeat)) {
        throw new ClientInputError(`No Governor race found for state ${stateCode} in 2026.`);
      }
      resolvedSeatId = govSeat;
    }

    if (office === "us_lieutenant_governor") {
      const stateCode = (geocoded.stateCode || geocoded.seatId?.split("-")[0] || "").toUpperCase();
      if (!stateCode) {
        throw new ClientInputError("Unable to determine state for Lieutenant Governor address lookup; provide seat_id.");
      }
      const ltGovSeat = `${stateCode}-LTGOV`;
      if (!bundle.generalRows.some((row) => row.seat === ltGovSeat)) {
        throw new ClientInputError(`No Lieutenant Governor race found for state ${stateCode} in 2026.`);
      }
      resolvedSeatId = ltGovSeat;
    }

    if (office === "us_house" && !resolvedSeatId && geocoded.latitude !== null && geocoded.longitude !== null) {
      const collection = asFeatureCollection(bundle.geometryGeoJson);
      resolvedSeatId = findSeatByPoint(collection, geocoded.longitude, geocoded.latitude);
    }
  } else {
    throw new ClientInputError("Missing required query parameter: seat_id or address");
  }
  const resolveMs = Number(process.hrtime.bigint() - resolveStart) / 1_000_000;

  const buildStart = process.hrtime.bigint();
  const payload = resolvedSeatId
    ? await buildPowerVoteFromSeat({
        seatId: resolvedSeatId,
        office,
        addressInput,
        normalizedAddress,
        latitude,
        longitude,
        bundle,
      })
    : {
        office,
        snapshotDate: bundle.snapshotDate,
        updatedAt: bundle.updatedAt,
        sourceAttribution: bundle.sourceAttribution,
        address: {
          input: addressInput,
          normalized: normalizedAddress,
          latitude,
          longitude,
          seatId: null,
        },
        elections: [],
      };
  const buildMs = Number(process.hrtime.bigint() - buildStart) / 1_000_000;

  const schemaStart = process.hrtime.bigint();
  const parsed = powerVoteResponseSchema.parse(payload);
  const schemaMs = Number(process.hrtime.bigint() - schemaStart) / 1_000_000;
  args.onTiming?.({
    loadMs,
    resolveMs,
    buildMs,
    schemaMs,
    totalMs: Number(process.hrtime.bigint() - totalStart) / 1_000_000,
  });
  return parsed;
}

export async function buildPowerVoteSeatOptionsResponse(args: { office?: OfficeInput }) {
  const office = normalizeOffice(args.office);
  const bundle = await loadCanonicalDataBundleByOffice(office);
  return powerVoteSeatOptionsResponseSchema.parse({
    office,
    snapshotDate: bundle.snapshotDate,
    updatedAt: bundle.updatedAt,
    states: buildStateSeatOptions(bundle.generalRows),
  });
}

export async function buildPowerVoteCompareResponse(args: {
  addresses?: string[];
  seatIds?: string[];
  office?: OfficeInput;
  geocode?: GeocodeFn;
}) {
  const office = normalizeOffice(args.office);
  const seatIds = Array.isArray(args.seatIds) ? args.seatIds.map((seatId) => normalizeRequestedSeatId(seatId)) : [];
  const addresses = Array.isArray(args.addresses) ? args.addresses.map((address) => address.trim()).filter(Boolean) : [];
  const usingSeatIds = seatIds.length > 0;
  const inputs = usingSeatIds ? seatIds : addresses;

  if (!inputs.length) {
    throw new ClientInputError("Request must include 2-3 seatIds or addresses.");
  }
  if (inputs.length < 2 || inputs.length > 3) {
    throw new ClientInputError("Side-by-side comparison supports 2-3 selections.");
  }
  if (new Set(inputs).size !== inputs.length) {
    throw new ClientInputError("Duplicate selections are not allowed.");
  }

  const results = usingSeatIds
    ? await Promise.all(seatIds.map((seatId) => buildPowerVoteResponse({ seatId, office })))
    : await Promise.all(addresses.map((address) => buildPowerVoteResponse({ address, office, geocode: args.geocode })));
  const bundle = await loadCanonicalDataBundleByOffice(office);
  return powerVoteCompareResponseSchema.parse({
    office,
    snapshotDate: bundle.snapshotDate,
    updatedAt: bundle.updatedAt,
    sourceAttribution: bundle.sourceAttribution,
    results,
  });
}

type LocationContext = {
  label: string;
  stateCode: string;
  houseSeatId: string;
  senateSeatIds: string[];
  governorSeatIds: string[];
  lieutenantGovernorSeatIds: string[];
  attorneyGeneralSeatIds: string[];
};

async function loadGovernorSeatsForState(stateCode: string): Promise<string[]> {
  const govBundle = await loadCanonicalDataBundleByOffice("us_governor");
  return govBundle.generalRows.filter((row) => row.seat === `${stateCode}-GOV`).map((row) => row.seat);
}

async function loadLtGovernorSeatsForState(stateCode: string): Promise<string[]> {
  const ltGovBundle = await loadCanonicalDataBundleByOffice("us_lieutenant_governor");
  return ltGovBundle.generalRows.filter((row) => row.seat === `${stateCode}-LTGOV`).map((row) => row.seat);
}

async function loadAttorneyGeneralSeatsForState(stateCode: string): Promise<string[]> {
  const bundle = await loadCanonicalDataBundleByOffice("us_attorney_general");
  return bundle.generalRows.filter((row) => row.seat === `${stateCode}-AG`).map((row) => row.seat);
}

async function resolveLocationContext(args: {
  seatId?: string;
  address?: string;
  zipcode?: string;
}): Promise<LocationContext> {
  if (args.address) {
    const geocoded = await geocodeWithNormalizationFallback(geocodeAddressWithCensus, args.address);
    const stateCode = (geocoded.stateCode || geocoded.seatId?.split("-")[0] || "").toUpperCase();
    if (!stateCode) {
      throw new ClientInputError("Unable to determine state for address lookup.");
    }
    const houseBundle = await loadCanonicalDataBundleByOffice("us_house");
    const collection = asFeatureCollection(houseBundle.geometryGeoJson);
    const houseSeatId =
      geocoded.seatId ||
      (geocoded.latitude !== null && geocoded.longitude !== null
        ? findSeatByPoint(collection, geocoded.longitude, geocoded.latitude)
        : null);
    if (!houseSeatId) {
      throw new ClientInputError(`Unable to resolve House seat for address ${args.address}.`);
    }
    const [senateBundle, governorSeatIds, lieutenantGovernorSeatIds, attorneyGeneralSeatIds] = await Promise.all([
      loadCanonicalDataBundleByOffice("us_senate"),
      loadGovernorSeatsForState(stateCode),
      loadLtGovernorSeatsForState(stateCode),
      loadAttorneyGeneralSeatsForState(stateCode),
    ]);
    const senateSeatIds = senateBundle.generalRows
      .filter((row) => row.seat.startsWith(`${stateCode}-SEN-`))
      .map((row) => row.seat)
      .sort();
    return {
      label: geocoded.normalizedAddress || args.address,
      stateCode,
      houseSeatId,
      senateSeatIds,
      governorSeatIds,
      lieutenantGovernorSeatIds,
      attorneyGeneralSeatIds,
    };
  }

  if (args.zipcode) {
    const zip = await lookupZipcode(args.zipcode);
    if (!zip.state || !zip.houseDistrict) {
      throw new ClientInputError(`Unable to resolve location from zipcode ${args.zipcode}.`);
    }
    const [governorSeatIds, lieutenantGovernorSeatIds, attorneyGeneralSeatIds] = await Promise.all([
      loadGovernorSeatsForState(zip.state),
      loadLtGovernorSeatsForState(zip.state),
      loadAttorneyGeneralSeatsForState(zip.state),
    ]);
    return {
      label: args.zipcode,
      stateCode: zip.state,
      houseSeatId: zip.houseDistrict,
      senateSeatIds: zip.senateSeats,
      governorSeatIds,
      lieutenantGovernorSeatIds,
      attorneyGeneralSeatIds,
    };
  }

  if (args.seatId) {
    const normalizedSeatId = normalizeRequestedSeatId(args.seatId);
    const stateCode = normalizedSeatId.split("-")[0];
    const [houseBundle, senateBundle, governorSeatIds, lieutenantGovernorSeatIds, attorneyGeneralSeatIds] = await Promise.all([
      loadCanonicalDataBundleByOffice("us_house"),
      loadCanonicalDataBundleByOffice("us_senate"),
      loadGovernorSeatsForState(stateCode),
      loadLtGovernorSeatsForState(stateCode),
      loadAttorneyGeneralSeatsForState(stateCode),
    ]);
    const senateSeatIds = senateBundle.generalRows
      .filter((row) => row.seat.startsWith(`${stateCode}-SEN-`))
      .map((row) => row.seat)
      .sort();

    if (isSenateSeatId(normalizedSeatId) || isGovernorSeatId(normalizedSeatId) || isLtGovernorSeatId(normalizedSeatId) || isAttorneyGeneralSeatId(normalizedSeatId)) {
      const houseSeatId = houseBundle.generalRows.find((row) => row.seat.startsWith(`${stateCode}-`))?.seat;
      if (!houseSeatId) {
        throw new ClientInputError(`No House seat found for state ${stateCode}.`);
      }
      return {
        label: normalizedSeatId,
        stateCode,
        houseSeatId,
        senateSeatIds,
        governorSeatIds,
        lieutenantGovernorSeatIds,
        attorneyGeneralSeatIds,
      };
    }

    return {
      label: normalizedSeatId,
      stateCode,
      houseSeatId: normalizedSeatId,
      senateSeatIds,
      governorSeatIds,
      lieutenantGovernorSeatIds,
      attorneyGeneralSeatIds,
    };
  }

  throw new ClientInputError("Missing required query parameter: seat_id or address or zipcode");
}

function sortElections(
  elections: Array<{
    seatId: string;
    electionKind: "general" | "primary" | "runoff";
    office: Office;
  }>,
) {
  const officeRank: Record<Office, number> = { us_house: 0, us_senate: 1, us_governor: 2, us_lieutenant_governor: 3, us_attorney_general: 4 };
  const kindRank: Record<"general" | "primary" | "runoff", number> = { general: 0, primary: 1, runoff: 2 };
  return [...elections].sort((a, b) => {
    if (officeRank[a.office] !== officeRank[b.office]) return officeRank[a.office] - officeRank[b.office];
    if (kindRank[a.electionKind] !== kindRank[b.electionKind]) return kindRank[a.electionKind] - kindRank[b.electionKind];
    return a.seatId.localeCompare(b.seatId);
  });
}

async function buildCrossOfficeLocation(args: { seatId?: string; address?: string; zipcode?: string }) {
  const resolved = await resolveLocationContext(args);
  const [house, senate, governor, lieutenantGovernor, attorneyGeneral] = await Promise.all([
    buildPowerVoteResponse({ office: "us_house", seatId: resolved.houseSeatId }),
    Promise.all(resolved.senateSeatIds.map((seatId) => buildPowerVoteResponse({ office: "us_senate", seatId }))),
    Promise.all(resolved.governorSeatIds.map((seatId) => buildPowerVoteResponse({ office: "us_governor", seatId }))),
    Promise.all(resolved.lieutenantGovernorSeatIds.map((seatId) => buildPowerVoteResponse({ office: "us_lieutenant_governor", seatId }))),
    Promise.all(resolved.attorneyGeneralSeatIds.map((seatId) => buildPowerVoteResponse({ office: "us_attorney_general", seatId }))),
  ]);
  const elections = sortElections([
    ...house.elections,
    ...senate.flatMap((payload) => payload.elections),
    ...governor.flatMap((payload) => payload.elections),
    ...lieutenantGovernor.flatMap((payload) => payload.elections),
    ...attorneyGeneral.flatMap((payload) => payload.elections),
  ]);
  return {
    label: resolved.label,
    resolvedContext: {
      stateCode: resolved.stateCode,
      houseSeatId: resolved.houseSeatId,
      senateSeatIds: resolved.senateSeatIds,
      governorSeatIds: resolved.governorSeatIds,
      lieutenantGovernorSeatIds: resolved.lieutenantGovernorSeatIds,
      attorneyGeneralSeatIds: resolved.attorneyGeneralSeatIds,
    },
    house,
    senate,
    governor,
    lieutenantGovernor,
    attorneyGeneral,
    elections,
  };
}

export async function buildPowerVoteAllResponse(args: {
  seatId?: string;
  address?: string;
  zipcode?: string;
  compareSeatId?: string;
  compareAddress?: string;
  compareZipcode?: string;
}) {
  const primary = await buildCrossOfficeLocation({
    seatId: args.seatId,
    address: args.address,
    zipcode: args.zipcode,
  });
  const locations = [primary];

  if (args.compareSeatId || args.compareAddress || args.compareZipcode) {
    const compare = await buildCrossOfficeLocation({
      seatId: args.compareSeatId,
      address: args.compareAddress,
      zipcode: args.compareZipcode,
    });
    locations.push(compare);
  }

  const snapshotDate = locations[0].house.snapshotDate;
  const updatedAt = locations[0].house.updatedAt;
  const sourceAttribution = Array.from(
    new Set(
      locations.flatMap((loc) => [
        ...loc.house.sourceAttribution,
        ...loc.senate.flatMap((sen) => sen.sourceAttribution),
        ...loc.governor.flatMap((gov) => gov.sourceAttribution),
        ...loc.lieutenantGovernor.flatMap((ltGov) => ltGov.sourceAttribution),
        ...loc.attorneyGeneral.flatMap((ag) => ag.sourceAttribution),
      ]),
    ),
  );

  return powerVoteAllResponseSchema.parse({
    snapshotDate,
    updatedAt,
    sourceAttribution,
    locations,
  });
}
