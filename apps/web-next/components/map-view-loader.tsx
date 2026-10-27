"use client";

import { useSearchParams } from "next/navigation";
import { MapView } from "@/components/map-view";

export function MapViewLoader() {
  const searchParams = useSearchParams();
  const initialSeat = searchParams.get("seat") ?? undefined;
  return <MapView initialSeat={initialSeat} />;
}
