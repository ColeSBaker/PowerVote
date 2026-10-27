import { describe, expect, test } from "vitest";

import { mobileBootstrapResponseSchema, mobileDeltaResponseSchema, mobileSeatResponseSchema } from "@/lib/domain/schemas";
import { GET as bootstrapGET } from "@/app/api/v1/mobile/bootstrap/route";
import { GET as deltaGET } from "@/app/api/v1/mobile/delta/route";
import { GET as seatGET } from "@/app/api/v1/mobile/seat/[seatId]/route";
import { buildMobileBootstrapResponse, buildMobileDeltaResponse, buildMobileSeatResponse } from "@/lib/server/mobile-api";

describe("mobile api integration", () => {
  test("bootstrap payload matches schema", async () => {
    const payload = await buildMobileBootstrapResponse();
    expect(() => mobileBootstrapResponseSchema.parse(payload)).not.toThrow();
    expect(payload.data.us_house.seatSummaries.length).toBeGreaterThan(400);
  });

  test("delta payload returns no changes when since equals snapshot", async () => {
    const bootstrap = await buildMobileBootstrapResponse();
    const payload = await buildMobileDeltaResponse(bootstrap.snapshotId);
    expect(() => mobileDeltaResponseSchema.parse(payload)).not.toThrow();
    expect(payload.hasChanges).toBe(false);
    expect(payload.changes.us_house.seatSummaries.length).toBe(0);
  });

  test("seat payload matches schema for known seat", async () => {
    const payload = await buildMobileSeatResponse("AL-01", "us_house");
    expect(() => mobileSeatResponseSchema.parse(payload)).not.toThrow();
    expect(payload.data.seat.seatId).toBe("AL-01");
  });

  test("bootstrap route returns cache headers", async () => {
    const request = new Request("http://localhost:3000/api/v1/mobile/bootstrap");
    const response = await bootstrapGET(request);
    expect(response.status).toBe(200);
    expect(response.headers.get("ETag")).toBeTruthy();
    expect(response.headers.get("X-Snapshot-Id")).toBeTruthy();
  });

  test("delta route works with since param", async () => {
    const bootstrap = await buildMobileBootstrapResponse();
    const request = new Request(`http://localhost:3000/api/v1/mobile/delta?since=${encodeURIComponent(bootstrap.snapshotId)}`);
    const response = await deltaGET(request);
    expect(response.status).toBe(200);
    const json = await response.json();
    expect(json.hasChanges).toBe(false);
  });

  test("seat route returns 404 for unknown seat", async () => {
    const request = new Request("http://localhost:3000/api/v1/mobile/seat/ZZ-99?office=us_house");
    const response = await seatGET(request, { params: Promise.resolve({ seatId: "ZZ-99" }) });
    expect(response.status).toBe(404);
  });
});
