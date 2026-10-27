import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

const root = fileURLToPath(new URL("./", import.meta.url));
const fixtureDataDir = fileURLToPath(new URL("./tests/fixtures/data", import.meta.url));

export default defineConfig({
  // tsconfig.json sets "jsx": "preserve" for Next.js; Vite 8's transformer would
  // honor that and leave JSX uncompiled, so compile it explicitly for tests.
  oxc: {
    jsx: { runtime: "automatic" },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    globals: true,
    env: {
      // Point integration tests at frozen fixture snapshots so daily pipeline
      // refreshes to apps/web/data/ never break regression/contract tests.
      DATA_DIR: fixtureDataDir,
    },
    coverage: {
      provider: "v8",
      include: ["lib/**/*.{ts,tsx}", "app/**/*.{ts,tsx}"],
      exclude: ["app/api/**", "**/*.d.ts"],
      thresholds: {
        lines: 70,
        functions: 70,
        branches: 60,
        statements: 70,
      },
      reporter: ["text", "html"],
    },
  },
  resolve: {
    alias: {
      "@": root,
    },
  },
});
