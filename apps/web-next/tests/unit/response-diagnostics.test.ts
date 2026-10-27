import { describe, expect, test } from "vitest";

import { buildDiagnosticsHeaders } from "@/lib/server/response-diagnostics";

describe("buildDiagnosticsHeaders", () => {
  test("adds Server-Timing and request id", () => {
    const headers = buildDiagnosticsHeaders("load;dur=1.00");
    expect(headers["Server-Timing"]).toBe("load;dur=1.00");
    expect(headers["X-Request-Id"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(headers["Timing-Allow-Origin"]).toBe("*");
  });

  test("generates unique request ids", () => {
    const first = buildDiagnosticsHeaders("load;dur=1.00");
    const second = buildDiagnosticsHeaders("load;dur=1.00");
    expect(first["X-Request-Id"]).not.toBe(second["X-Request-Id"]);
  });

  test("reuses inbound x-request-id when present", () => {
    const request = new Request("http://localhost/example", {
      headers: { "x-request-id": "req-12345" },
    });
    const headers = buildDiagnosticsHeaders("load;dur=1.00", request);
    expect(headers["X-Request-Id"]).toBe("req-12345");
  });
});
