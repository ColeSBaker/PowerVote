import type { FilterSpecification } from "maplibre-gl";
export type DistrictOption = {
  seatId: string;
  state: string;
  districtLabel: string;
};

export type FocusTarget =
  | { kind: "all" }
  | { kind: "state"; stateCode: string }
  | { kind: "seat"; seatId: string; stateCode: string };

export type MapRegion = "contiguous" | "alaska" | "hawaii";
export type LngLatBoundsTuple = [[number, number], [number, number]];

type GeoFeatureLike = {
  properties?: Record<string, unknown>;
  geometry?: {
    type?: string;
    coordinates?: unknown;
  };
};

const EMPTY_FILTER: FilterSpecification = ["==", ["get", "seatId"], "__PV_NO_MATCH__"];

function compareSeatIds(leftSeatId: string, rightSeatId: string): number {
  const [leftState = ""] = leftSeatId.split("-");
  const [rightState = ""] = rightSeatId.split("-");
  const leftDistrict = leftSeatId.startsWith(`${leftState}-SEN-`) ? leftSeatId.replace(`${leftState}-SEN-`, "") : leftSeatId.split("-")[1] || "";
  const rightDistrict = rightSeatId.startsWith(`${rightState}-SEN-`) ? rightSeatId.replace(`${rightState}-SEN-`, "") : rightSeatId.split("-")[1] || "";
  if (leftState !== rightState) {
    return leftState.localeCompare(rightState);
  }
  if (leftDistrict.startsWith("C") || rightDistrict.startsWith("C")) {
    const leftClass = Number.parseInt(leftDistrict.replace("-SPL", "").slice(1), 10);
    const rightClass = Number.parseInt(rightDistrict.replace("-SPL", "").slice(1), 10);
    if (!Number.isNaN(leftClass) && !Number.isNaN(rightClass) && leftClass !== rightClass) {
      return leftClass - rightClass;
    }
    if (leftDistrict.endsWith("-SPL") && !rightDistrict.endsWith("-SPL")) return 1;
    if (rightDistrict.endsWith("-SPL") && !leftDistrict.endsWith("-SPL")) return -1;
    return leftDistrict.localeCompare(rightDistrict);
  }
  if (leftDistrict === "AL" && rightDistrict !== "AL") return -1;
  if (rightDistrict === "AL" && leftDistrict !== "AL") return 1;
  const leftNumber = Number.parseInt(leftDistrict, 10);
  const rightNumber = Number.parseInt(rightDistrict, 10);
  if (!Number.isNaN(leftNumber) && !Number.isNaN(rightNumber)) {
    return leftNumber - rightNumber;
  }
  return leftDistrict.localeCompare(rightDistrict);
}

export function getStateCodeFromSeatId(seatId: string | null | undefined): string | null {
  if (!seatId) return null;
  const [stateCode] = String(seatId).trim().toUpperCase().split("-");
  return stateCode || null;
}

export function getMapRegionForStateCode(stateCode: string | null | undefined): MapRegion {
  if (stateCode === "AK") return "alaska";
  if (stateCode === "HI") return "hawaii";
  return "contiguous";
}

export function deriveStateOptions(districts: DistrictOption[]): string[] {
  return [...new Set(districts.map((district) => district.state).filter(Boolean))].sort((left, right) =>
    left.localeCompare(right),
  );
}

export function deriveSeatOptions(districts: DistrictOption[], stateCode: string | null = null): Array<{ seatId: string; label: string }> {
  const normalizedStateCode = stateCode ? stateCode.toUpperCase() : null;
  return districts
    .filter((district) => !normalizedStateCode || district.state === normalizedStateCode)
    .slice()
    .sort((left, right) => compareSeatIds(left.seatId, right.seatId))
    .map((district) => ({
      seatId: district.seatId,
      label: district.seatId,
    }));
}

export function resolveFocusTarget(args: {
  selectedState: string | null;
  selectedSeat: string | null;
  districts: DistrictOption[];
}): FocusTarget {
  const { selectedState, selectedSeat, districts } = args;
  const districtBySeatId = new Map(districts.map((district) => [district.seatId, district]));

  if (selectedSeat) {
    const selectedDistrict = districtBySeatId.get(selectedSeat);
    const stateCode = selectedDistrict?.state || getStateCodeFromSeatId(selectedSeat);
    if (stateCode) {
      return { kind: "seat", seatId: selectedSeat, stateCode };
    }
  }

  if (selectedState) {
    return { kind: "state", stateCode: selectedState };
  }

  return { kind: "all" };
}

export function buildRegionFilter(region: MapRegion): FilterSpecification {
  if (region === "alaska") {
    return ["==", ["get", "state"], "AK"];
  }
  if (region === "hawaii") {
    return ["==", ["get", "state"], "HI"];
  }
  return ["all", ["!=", ["get", "state"], "AK"], ["!=", ["get", "state"], "HI"]];
}

export function buildFocusFilters(region: MapRegion, focus: FocusTarget): { activeFilter: FilterSpecification; dimFilter: FilterSpecification; highlightFilter: FilterSpecification } {
  const regionFilter = buildRegionFilter(region);
  if (focus.kind === "all") {
    return {
      activeFilter: regionFilter,
      dimFilter: regionFilter,
      highlightFilter: EMPTY_FILTER,
    };
  }

  if (focus.kind === "seat") {
    return {
      activeFilter: ["all", regionFilter, ["==", ["get", "seatId"], focus.seatId]] as FilterSpecification,
      dimFilter: ["all", regionFilter, ["!=", ["get", "seatId"], focus.seatId]] as FilterSpecification,
      highlightFilter: ["all", regionFilter, ["==", ["get", "seatId"], focus.seatId]] as FilterSpecification,
    };
  }

  return {
    activeFilter: ["all", regionFilter, ["==", ["get", "state"], focus.stateCode]] as FilterSpecification,
    dimFilter: ["all", regionFilter, ["!=", ["get", "state"], focus.stateCode]] as FilterSpecification,
    highlightFilter: EMPTY_FILTER,
  };
}

function eachCoordinate(feature: GeoFeatureLike, callback: (lon: number, lat: number) => void): void {
  const geometry = feature.geometry;
  if (!geometry?.type || !geometry.coordinates) return;

  if (geometry.type === "Polygon") {
    (geometry.coordinates as number[][][]).forEach((ring) => {
      ring.forEach(([lon, lat]) => callback(lon, lat));
    });
    return;
  }

  if (geometry.type === "MultiPolygon") {
    (geometry.coordinates as number[][][][]).forEach((polygon) => {
      polygon.forEach((ring) => {
        ring.forEach(([lon, lat]) => callback(lon, lat));
      });
    });
  }
}

function featureStateCode(feature: GeoFeatureLike): string | null {
  const properties = feature.properties || {};
  const direct = properties.state || properties.STATE_ABBR || properties.STUSPS || properties.stateCode;
  if (direct) return String(direct).trim().toUpperCase();
  const seatId = properties.seatId;
  return getStateCodeFromSeatId(typeof seatId === "string" ? seatId : null);
}

export function featureSeatId(feature: GeoFeatureLike): string | null {
  const properties = feature.properties || {};
  if (properties.seatId) return String(properties.seatId);
  const stateCode = featureStateCode(feature);
  const districtRaw = String(properties.DISTRICT || properties.CDFP || properties.districtCode || "").trim().toUpperCase();
  if (!stateCode || !districtRaw) return null;
  const districtCode = districtRaw === "AL" || districtRaw === "00" || districtRaw === "0" ? "AL" : String(Number.parseInt(districtRaw, 10)).padStart(2, "0");
  return `${stateCode}-${districtCode}`;
}

export function computeFeatureBounds(feature: GeoFeatureLike): [number, number, number, number] | null {
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  eachCoordinate(feature, (lon, lat) => {
    minLon = Math.min(minLon, lon);
    minLat = Math.min(minLat, lat);
    maxLon = Math.max(maxLon, lon);
    maxLat = Math.max(maxLat, lat);
  });
  if (!Number.isFinite(minLon)) return null;
  return [minLon, minLat, maxLon, maxLat];
}

export function mergeBounds(bounds: Array<[number, number, number, number]>): [number, number, number, number] | null {
  if (!bounds.length) return null;
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  bounds.forEach(([leftLon, leftLat, rightLon, rightLat]) => {
    minLon = Math.min(minLon, leftLon);
    minLat = Math.min(minLat, leftLat);
    maxLon = Math.max(maxLon, rightLon);
    maxLat = Math.max(maxLat, rightLat);
  });
  if (!Number.isFinite(minLon)) return null;
  return [minLon, minLat, maxLon, maxLat];
}

export function toLngLatBoundsTuple(bounds: [number, number, number, number] | null): LngLatBoundsTuple | null {
  if (!bounds) return null;
  return [
    [bounds[0], bounds[1]],
    [bounds[2], bounds[3]],
  ];
}

export function buildSeatBoundsLookup(features: GeoFeatureLike[]): Map<string, LngLatBoundsTuple> {
  const lookup = new Map<string, LngLatBoundsTuple>();
  features.forEach((feature) => {
    const seatId = featureSeatId(feature);
    if (!seatId) return;
    const bounds = toLngLatBoundsTuple(computeFeatureBounds(feature));
    if (bounds) lookup.set(seatId, bounds);
  });
  return lookup;
}

export function buildStateBoundsLookup(features: GeoFeatureLike[]): Map<string, LngLatBoundsTuple> {
  const perStateBounds = new Map<string, Array<[number, number, number, number]>>();
  features.forEach((feature) => {
    const stateCode = featureStateCode(feature);
    const bounds = computeFeatureBounds(feature);
    if (!stateCode || !bounds) return;
    const list = perStateBounds.get(stateCode) || [];
    list.push(bounds);
    perStateBounds.set(stateCode, list);
  });

  const lookup = new Map<string, LngLatBoundsTuple>();
  perStateBounds.forEach((bounds, stateCode) => {
    const merged = mergeBounds(bounds);
    const tuple = toLngLatBoundsTuple(merged);
    if (tuple) lookup.set(stateCode, tuple);
  });
  return lookup;
}

export function buildRegionBoundsLookup(features: GeoFeatureLike[]): Map<MapRegion, LngLatBoundsTuple> {
  const byRegion = new Map<MapRegion, Array<[number, number, number, number]>>([
    ["contiguous", []],
    ["alaska", []],
    ["hawaii", []],
  ]);
  features.forEach((feature) => {
    const stateCode = featureStateCode(feature);
    const bounds = computeFeatureBounds(feature);
    if (!stateCode || !bounds) return;
    byRegion.get(getMapRegionForStateCode(stateCode))?.push(bounds);
  });

  const lookup = new Map<MapRegion, LngLatBoundsTuple>();
  byRegion.forEach((bounds, region) => {
    const merged = mergeBounds(bounds);
    const tuple = toLngLatBoundsTuple(merged);
    if (tuple) lookup.set(region, tuple);
  });
  return lookup;
}
