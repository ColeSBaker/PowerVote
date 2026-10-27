import { describe, expect, test } from "vitest";

import { formatServerTiming } from "@/lib/server/server-timing";

describe("formatServerTiming", () => {
  test("formats duration and description metrics", () => {
    const header = formatServerTiming([
      { name: "load", dur: 12.3456 },
      { name: "cache", desc: "hit" },
    ]);

    expect(header).toBe('load;dur=12.35, cache;desc="hit"');
  });

  test("sanitizes invalid tokens and desc quotes", () => {
    const header = formatServerTiming([
      { name: "load stage", dur: 1 },
      { name: "cache", desc: 'status "ok"' },
    ]);

    expect(header).toBe('load_stage;dur=1.00, cache;desc="status \'ok\'"');
  });
});
