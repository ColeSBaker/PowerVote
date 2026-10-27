import { existsSync } from "node:fs";
import path from "node:path";

/**
 * Resolves the canonical rollup data directory.
 * Checks DATA_DIR env var first, then falls back to probing known
 * relative paths to support running from the Next.js app root or monorepo root.
 */
export function resolveDataDirectory(): string {
  const envOverride = process.env.DATA_DIR;
  if (envOverride) {
    const resolved = path.resolve(envOverride);
    if (!existsSync(resolved)) {
      throw new Error(`DATA_DIR is set but does not exist: ${resolved}`);
    }
    return resolved;
  }

  const cwd = process.cwd();
  const candidates = [
    path.resolve(cwd, "data"),
    path.resolve(cwd, "apps", "web-next", "data"),
    path.resolve(cwd, "apps", "web", "data"),
    path.resolve(cwd, "..", "web", "data"),
    path.resolve(cwd, "..", "..", "apps", "web", "data"),
  ];

  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error(
      `Unable to locate canonical rollup data directory from ${cwd}. Tried:\n` +
        candidates.map((c) => `  ${c}`).join("\n") +
        "\nSet the DATA_DIR environment variable to specify an explicit path.",
    );
  }
  return found;
}

/**
 * Resolves the pre-computed static artifacts directory (apps/web-next/public/data/).
 * Returns null if the directory does not exist — callers should fall back to dynamic generation.
 */
export function resolveStaticArtifactsDirectory(): string | null {
  const cwd = process.cwd();
  const candidates = [
    path.resolve(cwd, "public", "data"),
    path.resolve(cwd, "apps", "web-next", "public", "data"),
  ];
  return candidates.find((c) => existsSync(c)) ?? null;
}
