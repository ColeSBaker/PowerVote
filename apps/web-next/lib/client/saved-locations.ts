export const SAVED_LOCATIONS_KEY = "pv-saved-locations";
export const MAX_SAVED = 15;

export interface SavedLocationEntry {
  id: string;
  savedAt: number;
  label: string;
  query: string;
  queryType: "address" | "zipcode";
}

export function isSavedLocationEntry(value: unknown): value is SavedLocationEntry {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "string" &&
    typeof v.savedAt === "number" &&
    typeof v.label === "string" &&
    typeof v.query === "string" &&
    (v.queryType === "address" || v.queryType === "zipcode")
  );
}

export function parseSavedLocations(raw: string | null): SavedLocationEntry[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isSavedLocationEntry);
  } catch {
    return [];
  }
}

export function createSavedEntry(
  label: string,
  query: string,
  queryType: "address" | "zipcode",
): SavedLocationEntry {
  return {
    id: crypto.randomUUID(),
    savedAt: Date.now(),
    label,
    query,
    queryType,
  };
}
