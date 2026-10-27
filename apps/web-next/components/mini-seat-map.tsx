"use client";

import { useEffect, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import type { Map as MapLibreMap } from "maplibre-gl";

import {
  buildFocusFilters,
  buildSeatBoundsLookup,
  getStateCodeFromSeatId,
} from "@/lib/client/map-view-focus";
import type { MapDistrictsResponse } from "@/lib/domain/schemas";
import { addDistrictLayers, buildMapStyle, mapBackgroundColor } from "@/lib/client/mini-map-utils";
import { loadMapLibre } from "@/lib/client/maplibre";

interface MiniSeatMapProps {
  seatId: string;
  office?: "us_house" | "us_senate" | "us_governor" | "us_lieutenant_governor" | "us_attorney_general";
}

export function MiniSeatMap({ seatId, office = "us_house" }: MiniSeatMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [payload, setPayload] = useState<MapDistrictsResponse | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [ready, setReady] = useState(false);

  // Track theme changes
  useEffect(() => {
    const resolve = () =>
      document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    setTheme(resolve());
    const observer = new MutationObserver(() => setTheme(resolve()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  // Fetch map data once
  useEffect(() => {
    const params = new URLSearchParams({ office, election_view: "general", color_mode: "contention" });
    fetch(`/api/v1/map/districts?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => setPayload(data as MapDistrictsResponse))
      .catch(() => {/* silently degrade */});
  }, [office]);

  // Initialize map
  useEffect(() => {
    if (!payload || !containerRef.current || mapRef.current) return;
    let disposed = false;

    (async () => {
      const maplibregl = await loadMapLibre();
      if (disposed || !containerRef.current) return;

      const map = new maplibregl.Map({
        container: containerRef.current,
        style: buildMapStyle(theme),
        center: [-96, 38],
        zoom: 2.8,
        attributionControl: false,
        interactive: false,
      });

      mapRef.current = map;

      // Ensure MapLibre reads the container's actual rendered dimensions
      requestAnimationFrame(() => { if (!disposed) map.resize(); });

      map.on("load", () => {
        map.addSource("districts", {
          type: "geojson",
          data: payload.featureCollection as unknown as FeatureCollection,
        });
        addDistrictLayers(map);

        // Zoom to this seat
        const boundsLookup = buildSeatBoundsLookup(payload.featureCollection.features);
        const bounds = boundsLookup.get(seatId) ?? null;
        if (bounds) {
          map.fitBounds(bounds, { padding: 24, duration: 0, maxZoom: 7.25 });
        }

        // Highlight this seat, dim others
        const stateCode = getStateCodeFromSeatId(seatId) ?? "";
        const region = stateCode === "AK" ? "alaska" : stateCode === "HI" ? "hawaii" : "contiguous";
        const { activeFilter, dimFilter, highlightFilter } = buildFocusFilters(region, { kind: "seat", seatId, stateCode });
        map.setFilter("district-fill-active", activeFilter);
        map.setFilter("district-fill-dim", dimFilter);
        map.setFilter("district-highlight", highlightFilter);

        setReady(true);
      });
    })();

    return () => {
      disposed = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload]);

  // Sync background color when theme changes (after map is ready)
  useEffect(() => {
    if (!mapRef.current) return;
    try {
      mapRef.current.setPaintProperty("background", "background-color", mapBackgroundColor(theme));
    } catch {
      // Map may not be fully loaded yet
    }
  }, [theme]);

  return (
    <div className={`mini-seat-map${ready ? " mini-seat-map--ready" : ""}`}>
      <div ref={containerRef} className="mini-seat-map__canvas" />
      {!ready && <div className="mini-seat-map__skeleton" />}
      <a
        href={`/map?seat=${encodeURIComponent(seatId)}`}
        className="mini-seat-map__expand"
        title="Explore on the full map"
      >
        Explore on map ↗
      </a>
    </div>
  );
}
