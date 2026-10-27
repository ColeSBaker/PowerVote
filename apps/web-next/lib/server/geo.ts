import { normalizeSeatId } from "@/lib/server/csv";

export type GeoFeature = {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: number[][][] | number[][][][];
  };
};

type FeatureCollection = {
  type: "FeatureCollection";
  features: GeoFeature[];
};

export function asFeatureCollection(raw: Record<string, unknown>): FeatureCollection {
  if (raw.type !== "FeatureCollection" || !Array.isArray(raw.features)) {
    throw new Error("District GeoJSON must be a FeatureCollection.");
  }
  return raw as unknown as FeatureCollection;
}

export function featureSeatId(feature: GeoFeature): string | null {
  const explicitSeat = String(feature.properties.seatId ?? "").trim().toUpperCase();
  if (explicitSeat) {
    return normalizeSeatId(explicitSeat);
  }
  const state =
    String(feature.properties.STATE_ABBR ?? feature.properties.STUSPS ?? feature.properties.stateCode ?? "").trim().toUpperCase();
  const districtRaw = String(feature.properties.DISTRICT ?? feature.properties.CDFP ?? feature.properties.districtCode ?? "").trim();
  if (!state || !districtRaw) return null;
  const district = districtRaw.toUpperCase() === "AL" ? "AL" : String(Number.parseInt(districtRaw, 10)).padStart(2, "0");
  if (!district || district === "NAN") return null;
  return normalizeSeatId(`${state}-${district}`);
}

function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersect = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi + Number.EPSILON) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function pointInPolygon(lon: number, lat: number, polygon: number[][][]): boolean {
  if (!polygon.length) return false;
  const inOuter = pointInRing(lon, lat, polygon[0]);
  if (!inOuter) return false;
  for (let i = 1; i < polygon.length; i += 1) {
    if (pointInRing(lon, lat, polygon[i])) return false;
  }
  return true;
}

export function findSeatByPoint(collection: FeatureCollection, lon: number, lat: number): string | null {
  for (const feature of collection.features) {
    const seatId = featureSeatId(feature);
    if (!seatId) continue;
    if (feature.geometry.type === "Polygon") {
      if (pointInPolygon(lon, lat, feature.geometry.coordinates as number[][][])) return seatId;
      continue;
    }
    for (const polygon of feature.geometry.coordinates as number[][][][]) {
      if (pointInPolygon(lon, lat, polygon)) return seatId;
    }
  }
  return null;
}
