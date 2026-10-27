import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { MapViewLoader } from "@/components/map-view-loader";

export default function MapPage() {
  return (
    <AppShell>
      <Suspense fallback={null}>
        <MapViewLoader />
      </Suspense>
    </AppShell>
  );
}

