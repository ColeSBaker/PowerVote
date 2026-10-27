import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("@/lib/server/api-service", () => ({
  buildPowerVoteAllResponse: vi.fn(),
}));

import { GET } from "@/app/api/v1/powervote/all/route";
import { buildPowerVoteAllResponse } from "@/lib/server/api-service";

describe("GET /api/v1/powervote/all", () => {
  beforeEach(() => {
    vi.mocked(buildPowerVoteAllResponse).mockReset();
  });

  it("returns 400 when no primary input is provided", async () => {
    const response = await GET(new Request("http://localhost:3000/api/v1/powervote/all"));
    expect(response.status).toBe(400);
  });

  it("returns payload for seat input", async () => {
    vi.mocked(buildPowerVoteAllResponse).mockResolvedValueOnce({
      snapshotDate: "2026-04-02",
      updatedAt: "2026-04-02T00:00:00Z",
      sourceAttribution: [],
      locations: [],
    } as any);

    const response = await GET(new Request("http://localhost:3000/api/v1/powervote/all?seat_id=CA-01"));
    expect(response.status).toBe(200);
    expect(buildPowerVoteAllResponse).toHaveBeenCalledWith(
      expect.objectContaining({ seatId: "CA-01" }),
    );
  });
});
