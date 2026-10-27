import type * as MapLibre from "maplibre-gl";

let workerConfigured = false;

/**
 * Lazily loads MapLibre in the browser and points it at the bundled worker.
 *
 * MapLibre v6 is ESM-only (no default export) and, under a bundler, needs an
 * explicit worker URL; webpack emits the worker as a same-origin asset from
 * the `new URL(..., import.meta.url)` pattern.
 */
export async function loadMapLibre(): Promise<typeof MapLibre> {
  const maplibregl = await import("maplibre-gl");
  if (!workerConfigured) {
    maplibregl.setWorkerUrl(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());
    workerConfigured = true;
  }
  return maplibregl;
}
