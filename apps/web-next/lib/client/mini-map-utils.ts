import type { StyleSpecification } from "maplibre-gl";

export function mapBackgroundColor(theme: "dark" | "light") {
  return theme === "light" ? "#dbe9f7" : "#0f1724";
}

export function buildMapStyle(theme: "dark" | "light"): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": mapBackgroundColor(theme) },
      },
    ],
  };
}

export function addDistrictLayers(map: import("maplibre-gl").Map) {
  map.addLayer({
    id: "district-fill-dim",
    type: "fill",
    source: "districts",
    paint: {
      "fill-color": ["coalesce", ["get", "fillColor"], "#9ca3af"],
      "fill-opacity": 0.18,
    },
  });
  map.addLayer({
    id: "district-fill-active",
    type: "fill",
    source: "districts",
    paint: {
      "fill-color": ["coalesce", ["get", "fillColor"], "#9ca3af"],
      "fill-opacity": 0.78,
    },
  });
  map.addLayer({
    id: "district-line",
    type: "line",
    source: "districts",
    paint: {
      "line-color": "#111827",
      "line-width": 0.35,
      "line-opacity": 0.5,
    },
  });
  map.addLayer({
    id: "district-highlight",
    type: "line",
    source: "districts",
    paint: {
      "line-color": "#f8fafc",
      "line-width": 1.8,
      "line-opacity": 0.95,
    },
  });
  map.addLayer({
    id: "district-hit",
    type: "fill",
    source: "districts",
    paint: {
      "fill-color": "#000000",
      "fill-opacity": 0.001,
    },
  });
}
