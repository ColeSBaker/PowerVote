import { describe, expect, test, vi } from "vitest";

// Force dynamic path so Server-Timing headers are emitted.
// Static artifact serving (tested separately in static-vs-dynamic.test.ts) bypasses
// the timing instrumentation that these tests verify.
vi.mock("@/lib/server/paths", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server/paths")>();
  return { ...actual, resolveStaticArtifactsDirectory: () => null };
});

import { GET } from "@/app/api/v1/map/districts/route";
import { resetMapDistrictsResponseCacheForTesting } from "@/lib/server/api-service";
import { resetCanonicalDataBundleCacheForTesting } from "@/lib/server/data-source";

describe("map districts route server timing", () => {
  test("returns stage-level Server-Timing metrics", async () => {
    resetMapDistrictsResponseCacheForTesting();
    resetCanonicalDataBundleCacheForTesting();

    const response = await GET(
      new Request("http://localhost/api/v1/map/districts?office=us_house&election_view=general&color_mode=contention", {
        headers: { "x-request-id": "map-test-request" },
      }),
    );

    expect(response.status).toBe(200);
    const header = response.headers.get("Server-Timing") ?? "";
    expect(header).toContain("load;dur=");
    expect(header).toContain("transform;dur=");
    expect(header).toContain("schema;dur=");
    expect(header).toContain("total;dur=");
    expect(header).toContain('cache;desc="miss"');
    expect(response.headers.get("X-Request-Id")).toBe("map-test-request");
    expect(response.headers.get("Timing-Allow-Origin")).toBe("*");
  });

  test("reports cache hit in Server-Timing for warm requests", async () => {
    resetMapDistrictsResponseCacheForTesting();
    resetCanonicalDataBundleCacheForTesting();

    await GET(new Request("http://localhost/api/v1/map/districts?office=us_house&election_view=general&color_mode=contention"));
    const warmResponse = await GET(new Request("http://localhost/api/v1/map/districts?office=us_house&election_view=general&color_mode=contention"));

    expect(warmResponse.status).toBe(200);
    const header = warmResponse.headers.get("Server-Timing") ?? "";
    expect(header).toContain('cache;desc="hit"');
    expect(warmResponse.headers.get("X-Request-Id")).toMatch(/^[0-9a-f-]{36}$/i);
    expect(warmResponse.headers.get("Timing-Allow-Origin")).toBe("*");
  });
});
