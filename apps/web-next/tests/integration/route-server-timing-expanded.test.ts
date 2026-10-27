import { describe, expect, test, vi } from "vitest";

// Force dynamic path so Server-Timing headers are emitted.
// Static artifact serving (tested separately in static-vs-dynamic.test.ts) bypasses
// the timing instrumentation that these tests verify.
vi.mock("@/lib/server/paths", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server/paths")>();
  return { ...actual, resolveStaticArtifactsDirectory: () => null };
});

import { GET as getPowerVote } from "@/app/api/v1/powervote/route";
import { GET as getMobileBootstrap } from "@/app/api/v1/mobile/bootstrap/route";
import { resetMapDistrictsResponseCacheForTesting } from "@/lib/server/api-service";
import { resetCanonicalDataBundleCacheForTesting } from "@/lib/server/data-source";

describe("additional route server timing", () => {
  test("powervote route returns stage-level Server-Timing", async () => {
    resetMapDistrictsResponseCacheForTesting();
    resetCanonicalDataBundleCacheForTesting();

    const response = await getPowerVote(
      new Request("http://localhost/api/v1/powervote?seat_id=CA-01&office=us_house", {
        headers: { "x-request-id": "powervote-test-request" },
      }),
    );

    expect(response.status).toBe(200);
    const header = response.headers.get("Server-Timing") ?? "";
    expect(header).toContain("load;dur=");
    expect(header).toContain("resolve;dur=");
    expect(header).toContain("build;dur=");
    expect(header).toContain("schema;dur=");
    expect(header).toContain("total;dur=");
    expect(response.headers.get("X-Request-Id")).toBe("powervote-test-request");
    expect(response.headers.get("Timing-Allow-Origin")).toBe("*");
  });

  test("mobile bootstrap route returns stage-level Server-Timing", async () => {
    resetCanonicalDataBundleCacheForTesting();

    const response = await getMobileBootstrap(
      new Request("http://localhost/api/v1/mobile/bootstrap", {
        headers: { "x-request-id": "mobile-test-request" },
      }),
    );

    expect(response.status).toBe(200);
    const header = response.headers.get("Server-Timing") ?? "";
    expect(header).toContain("load;dur=");
    expect(header).toContain("build;dur=");
    expect(header).toContain("schema;dur=");
    expect(header).toContain("total;dur=");
    expect(response.headers.get("X-Request-Id")).toBe("mobile-test-request");
    expect(response.headers.get("Timing-Allow-Origin")).toBe("*");
  });
});
