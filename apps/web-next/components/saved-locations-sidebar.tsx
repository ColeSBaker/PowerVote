"use client";

import { useState } from "react";
import type { PowerVoteAllResponse } from "@/lib/domain/schemas";
import { useSavedLocations } from "@/lib/client/use-saved-locations";
import type { SavedLocationEntry } from "@/lib/client/saved-locations";

type Location = PowerVoteAllResponse["locations"][number];

interface Props {
  onLoad: (loc: Location) => void;
  isAtCapacity: boolean;
}

function formatDate(ts: number): string {
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function PinIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2L8 8H2l5 5-2 9 7-4 7 4-2-9 5-5h-6z"/>
    </svg>
  );
}

function LoadIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true" className="pv-pin-spinner">
      <path d="M12 2a10 10 0 0 1 10 10"/>
    </svg>
  );
}

function SavedEntryRow({
  entry,
  onLoad,
  onRemove,
  isAtCapacity,
}: {
  entry: SavedLocationEntry;
  onLoad: (loc: Location) => void;
  onRemove: () => void;
  isAtCapacity: boolean;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function handleLoad() {
    if (loading || isAtCapacity) return;
    setLoading(true);
    setError(false);
    try {
      const params = new URLSearchParams();
      params.set(entry.queryType, entry.query);
      const response = await fetch(`/api/v1/powervote/all?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error();
      const locs = (data as PowerVoteAllResponse).locations;
      if (locs.length > 0) onLoad(locs[0]);
    } catch {
      setError(true);
      setTimeout(() => setError(false), 2500);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className={`pv-pin-row${error ? " pv-pin-row--error" : ""}${isAtCapacity ? " pv-pin-row--capped" : ""}`}
      title={isAtCapacity ? "Clear a location to load" : entry.label}
    >
      <button
        type="button"
        className="pv-pin-row__body"
        onClick={handleLoad}
        disabled={loading || isAtCapacity}
        aria-label={`Load ${entry.label}`}
      >
        <span className="pv-pin-row__accent" />
        <span className="pv-pin-row__label">{entry.label}</span>
        <span className="pv-pin-row__date">{formatDate(entry.savedAt)}</span>
        <span className="pv-pin-row__arrow">
          {loading ? <SpinnerIcon /> : error ? "!" : <LoadIcon />}
        </span>
      </button>
      <button
        type="button"
        className="pv-pin-row__remove"
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        aria-label="Remove saved location"
        tabIndex={-1}
      >
        ×
      </button>
    </div>
  );
}

export function SavedLocationsSidebar({ onLoad, isAtCapacity }: Props) {
  const { savedLocations, removeLocation } = useSavedLocations();
  const count = savedLocations.length;

  return (
    <aside className="pv-pin-rail">
      <div className="pv-pin-rail__head">
        <span className="pv-pin-rail__title">
          <PinIcon />
          Saved
        </span>
        {count > 0 && <span className="pv-pin-rail__count">{count}</span>}
      </div>

      {count === 0 ? (
        <div className="pv-pin-rail__empty">
          <span>Save locations for quick access</span>
        </div>
      ) : (
        <div className="pv-pin-rail__list">
          {savedLocations.map((entry) => (
            <SavedEntryRow
              key={entry.id}
              entry={entry}
              onLoad={onLoad}
              onRemove={() => removeLocation(entry.id)}
              isAtCapacity={isAtCapacity}
            />
          ))}
        </div>
      )}
    </aside>
  );
}
