import { loadCanonicalDataBundleByOffice } from "@/lib/server/data-source";
import { asFeatureCollection, findSeatByPoint } from "@/lib/server/geo";
import { ClientInputError } from "@/lib/server/errors";
import { getZipcodeCentroid } from "@/lib/server/zipcode-centroids-generated";

export type ZipcodeResult = {
  zipcode: string;
  state: string | null;
  houseDistrict: string | null;
  senateSeats: string[];
  normalizedAddress: string | null;
  latitude: number | null;
  longitude: number | null;
};

/**
 * Validates zipcode format (5 digits, optionally +4)
 * Examples: "90210", "90210-1234"
 */
export function validateZipcodeFormat(zipcode: string): boolean {
  const trimmed = zipcode.trim();
  return /^\d{5}(-\d{4})?$/.test(trimmed);
}

/**
 * Looks up a US zipcode to find congressional district and senate seats.
 * Uses the pre-built centroid database (~33k zipcodes from Census ZCTA data)
 * and point-in-polygon to map to elections.
 */
export async function lookupZipcode(zipcode: string): Promise<ZipcodeResult> {
  if (!validateZipcodeFormat(zipcode)) {
    throw new ClientInputError(`Invalid zipcode format: "${zipcode}". Expected format: 12345 or 12345-6789`);
  }

  // Look up centroid directly from our database
  const centroid = getZipcodeCentroid(zipcode);
  if (!centroid) {
    throw new ClientInputError(
      `Cannot determine location for zipcode ${zipcode}. Zipcode not found in centroid database.`
    );
  }
  const { latitude, longitude } = centroid;

  // Point-in-polygon to find congressional district
  let houseDistrict: string | null = null;
  try {
    const bundle = await loadCanonicalDataBundleByOffice("us_house");
    const collection = asFeatureCollection(bundle.geometryGeoJson);
    houseDistrict = findSeatByPoint(collection, longitude, latitude);
  } catch (error) {
    throw new Error(
      `Failed to determine congressional district: ${error instanceof Error ? error.message : String(error)}`
    );
  }

  if (!houseDistrict) {
    throw new ClientInputError(
      `Zipcode ${zipcode} at coordinates (${latitude}, ${longitude}) does not fall within any congressional district.`
    );
  }

  // Extract state from district ID (e.g. "CA-35" → "CA")
  const stateCode = houseDistrict.split("-")[0];

  // Find Senate seats for the state
  let senateSeats: string[] = [];
  try {
    const bundle = await loadCanonicalDataBundleByOffice("us_senate");
    senateSeats = bundle.generalRows
      .filter((row) => row.seat.startsWith(`${stateCode}-SEN-`))
      .map((row) => row.seat)
      .sort();
  } catch (error) {
    throw new Error(
      `Failed to load Senate data for state ${stateCode}: ${error instanceof Error ? error.message : String(error)}`
    );
  }

  return {
    zipcode: zipcode.trim(),
    state: stateCode,
    houseDistrict,
    senateSeats,
    normalizedAddress: null,
    latitude,
    longitude,
  };
}
