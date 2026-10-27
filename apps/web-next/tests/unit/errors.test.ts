import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ClientInputError, errorResponse } from "@/lib/server/errors";

describe("errorResponse", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("passes ClientInputError messages through with the client status", async () => {
    const response = errorResponse(new ClientInputError("No district record found for seat ZZ-99."), 404);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "No district record found for seat ZZ-99." });
  });

  it("maps ZodError to a generic 400", async () => {
    const result = z.enum(["a"]).safeParse("b");
    const response = errorResponse(result.error);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "Invalid request parameters." });
  });

  it("hides internal error details behind a 500", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const response = errorResponse(new Error("DATA_DIR is set but does not exist: /srv/secret/path"));
    expect(response.status).toBe(500);
    const body = await response.json();
    expect(body).toEqual({ error: "Internal server error." });
    expect(JSON.stringify(body)).not.toContain("/srv/secret/path");
    expect(spy).toHaveBeenCalled();
  });
});
