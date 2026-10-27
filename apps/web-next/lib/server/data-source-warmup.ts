// Node.js-only module — never executed in Edge runtime.
// Imported by instrumentation.ts via a dynamic import guarded by NEXT_RUNTIME.
// next.config.ts aliases this file to false (empty module) in the Edge webpack bundle
// so webpack never traces its node: imports when compiling for Edge.
import { loadCanonicalDataBundleForMapByOffice, loadCanonicalDataBundleByOffice } from "@/lib/server/data-source";

export async function warmupDataBundles() {
  await Promise.all([
    loadCanonicalDataBundleForMapByOffice("us_house"),
    loadCanonicalDataBundleByOffice("us_house"),
    loadCanonicalDataBundleByOffice("us_senate"),
  ]);
}
