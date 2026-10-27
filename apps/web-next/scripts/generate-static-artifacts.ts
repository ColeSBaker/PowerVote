#!/usr/bin/env node
/**
 * Pre-renders the two most expensive API endpoints as static JSON files.
 *
 * Output: apps/web-next/public/data/
 *   - mobile-bootstrap.json
 *   - map-districts--{office}--{electionView}--{colorMode}.json  (50 files)
 *
 * Run via: npm run generate:static  (from apps/web-next/)
 * CI step: npm --prefix apps/web-next run generate:static
 */

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { buildMapDistrictsResponse } from "@/lib/server/api-service";
import { buildMobileBootstrapResponse } from "@/lib/server/mobile-api";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = path.resolve(__dirname, "../public/data");

const GENERAL_COLOR_MODES = [
  "contention",
  "incumbent",
  "market_favorite",
  "polling_proxy",
  "targeting",
  "powervote",
  "kalshi_integrity_general",
] as const;

const PRIMARY_COLOR_MODES = [
  "primary_status",
  "primary_kalshi",
  "primary_contention_dem",
  "primary_contention_rep",
  "primary_contention_np",
  "primary_kalshi_dem",
  "primary_kalshi_rep",
  "primary_kalshi_np",
  "kalshi_integrity_primary",
  "kalshi_integrity_primary_dem",
  "kalshi_integrity_primary_rep",
  "kalshi_integrity_primary_np",
] as const;

const OFFICES = [
  "us_house",
  "us_senate",
  "us_governor",
  "us_lieutenant_governor",
  "us_attorney_general",
] as const;

function mapDistrictsFilename(office: string, electionView: string, colorMode: string): string {
  return `map-districts--${office}--${electionView}--${colorMode}.json`;
}

async function main() {
  await mkdir(OUTPUT_DIR, { recursive: true });

  let generated = 0;
  let errors = 0;

  // Mobile bootstrap (no params — always generates for us_house + us_senate)
  try {
    const payload = await buildMobileBootstrapResponse();
    await writeFile(path.join(OUTPUT_DIR, "mobile-bootstrap.json"), JSON.stringify(payload));
    console.log("  ✓ mobile-bootstrap.json");
    generated++;
  } catch (err) {
    console.error(`  ✗ mobile-bootstrap.json: ${err instanceof Error ? err.message : err}`);
    errors++;
  }

  // Map districts — general election (7 color modes × 5 offices = 35 files)
  for (const office of OFFICES) {
    for (const colorMode of GENERAL_COLOR_MODES) {
      const filename = mapDistrictsFilename(office, "general", colorMode);
      try {
        const payload = await buildMapDistrictsResponse({ office, electionView: "general", colorMode });
        await writeFile(path.join(OUTPUT_DIR, filename), JSON.stringify(payload));
        console.log(`  ✓ ${filename}`);
        generated++;
      } catch (err) {
        console.error(`  ✗ ${filename}: ${err instanceof Error ? err.message : err}`);
        errors++;
      }
    }
  }

  // Map districts — primary election (3 color modes × 5 offices = 15 files)
  for (const office of OFFICES) {
    for (const colorMode of PRIMARY_COLOR_MODES) {
      const filename = mapDistrictsFilename(office, "primary", colorMode);
      try {
        const payload = await buildMapDistrictsResponse({ office, electionView: "primary", colorMode });
        await writeFile(path.join(OUTPUT_DIR, filename), JSON.stringify(payload));
        console.log(`  ✓ ${filename}`);
        generated++;
      } catch (err) {
        console.error(`  ✗ ${filename}: ${err instanceof Error ? err.message : err}`);
        errors++;
      }
    }
  }

  console.log(`\nGenerated ${generated} artifacts, ${errors} errors → ${OUTPUT_DIR}`);
  if (errors > 0) process.exit(1);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
