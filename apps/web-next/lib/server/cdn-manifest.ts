import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { resolveStaticArtifactsDirectory } from "./paths";

interface CdnManifest {
  generatedAt: string;
  cdnBaseUrl: string;
  assets: Record<string, string>;
}

// Module-level cache: undefined = not yet loaded, null = no manifest available
let cachedManifest: CdnManifest | null | undefined = undefined;

function loadCdnManifest(): CdnManifest | null {
  if (cachedManifest !== undefined) return cachedManifest;

  const staticDir = resolveStaticArtifactsDirectory();
  if (!staticDir) {
    cachedManifest = null;
    return null;
  }

  const manifestPath = path.join(staticDir, "cdn-manifest.json");
  if (!existsSync(manifestPath)) {
    cachedManifest = null;
    return null;
  }

  try {
    cachedManifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as CdnManifest;
  } catch {
    cachedManifest = null;
  }
  return cachedManifest;
}

/**
 * Returns the CDN URL for a named static artifact, or null if no CDN manifest
 * is present. The filename should be the logical artifact name without a path,
 * e.g. "map-districts--us_house--general--incumbent.json".
 *
 * When a CDN URL is returned, callers should issue a 302 redirect so the client
 * downloads the asset directly from R2 (immutable, ~400KB Brotli-compressed)
 * instead of streaming it through the Next.js server (~3MB uncompressed).
 */
export function resolveCdnUrl(filename: string): string | null {
  const manifest = loadCdnManifest();
  if (!manifest) return null;
  return manifest.assets[filename] ?? null;
}
