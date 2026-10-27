"use client";

import { useState } from "react";
import type { PowerVoteAllResponse } from "@/lib/domain/schemas";
import { PowerVoteView } from "@/components/powervote-view";
import { SavedLocationsSidebar } from "@/components/saved-locations-sidebar";

type Location = PowerVoteAllResponse["locations"][number];

export function PowerVoteLayout({ initialAddress, initialZipcode }: { initialAddress?: string; initialZipcode?: string } = {}) {
  const [locations, setLocations] = useState<Location[]>([]);

  function handleLoad(loc: Location) {
    setLocations((prev) => (prev.length < 2 ? [...prev, loc] : prev));
  }

  return (
    <div className="pv-powervote-layout">
      <PowerVoteView
        locations={locations}
        setLocations={setLocations}
        initialAddress={initialAddress}
        initialZipcode={initialZipcode}
      />
      <SavedLocationsSidebar onLoad={handleLoad} isAtCapacity={locations.length >= 2} />
    </div>
  );
}
