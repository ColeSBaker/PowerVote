"use client";

import { useCallback, useEffect, useState } from "react";
import {
  SAVED_LOCATIONS_KEY,
  MAX_SAVED,
  SavedLocationEntry,
  createSavedEntry,
  parseSavedLocations,
} from "./saved-locations";

export function useSavedLocations() {
  const [savedLocations, setSavedLocations] = useState<SavedLocationEntry[]>([]);

  // Hydrate from localStorage on mount
  useEffect(() => {
    setSavedLocations(parseSavedLocations(localStorage.getItem(SAVED_LOCATIONS_KEY)));
  }, []);

  // Cross-tab sync
  useEffect(() => {
    function handleStorage(event: StorageEvent) {
      if (event.key !== SAVED_LOCATIONS_KEY) return;
      setSavedLocations(parseSavedLocations(event.newValue));
    }
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const saveLocation = useCallback(
    (label: string, query: string, queryType: "address" | "zipcode"): string | null => {
      if (savedLocations.length >= MAX_SAVED) {
        return `Limit reached (${MAX_SAVED}). Remove a saved location to add more.`;
      }
      if (savedLocations.some((e) => e.query === query)) {
        return null; // already saved
      }
      const next = [...savedLocations, createSavedEntry(label, query, queryType)];
      try {
        localStorage.setItem(SAVED_LOCATIONS_KEY, JSON.stringify(next));
      } catch {
        return "Failed to save location. Storage may be full.";
      }
      setSavedLocations(next);
      return null;
    },
    [savedLocations],
  );

  const removeLocation = useCallback((id: string) => {
    setSavedLocations((prev) => {
      const next = prev.filter((e) => e.id !== id);
      try {
        localStorage.setItem(SAVED_LOCATIONS_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const isSaved = useCallback(
    (query: string): boolean => savedLocations.some((e) => e.query === query),
    [savedLocations],
  );

  return { savedLocations, saveLocation, removeLocation, isSaved };
}
