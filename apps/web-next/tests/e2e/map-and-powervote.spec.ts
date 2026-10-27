import { test } from "@playwright/test";

test.describe("Map and PowerVote flows", () => {
  test.skip("map mode switching and district click-through", async () => {
    // Implement in CI once the Next.js app is started in playwright webServer mode.
  });

  test.skip("address lookup to election cards", async () => {
    // Implement in CI once stable geocoder mocking is available.
  });

  test.skip("stale/failure UI state rendering", async () => {
    // Implement in CI once fault-injection routes are wired.
  });
});

