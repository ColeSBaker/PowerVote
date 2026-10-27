import { describe, expect, test } from "vitest";

import { isTheme, THEME_INIT_SCRIPT, THEME_STORAGE_KEY } from "@/lib/client/theme";

describe("theme helpers", () => {
  test("accepts only supported theme values", () => {
    expect(isTheme("dark")).toBe(true);
    expect(isTheme("light")).toBe(true);
    expect(isTheme("system")).toBe(false);
    expect(isTheme(null)).toBe(false);
  });

  test("includes storage key in init script", () => {
    expect(THEME_INIT_SCRIPT).toContain(THEME_STORAGE_KEY);
  });
});
