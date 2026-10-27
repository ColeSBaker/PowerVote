import path from "path";
import type { NextConfig } from "next";

// CSP notes:
//   - script-src 'unsafe-inline': required for Next.js SSR hydration scripts
//   - script-src 'unsafe-eval': required in dev mode for Next.js eval-source-map devtool
//   - style-src 'unsafe-inline': required for MapLibre GL inline style mutations
//   - img-src data: blob:: MapLibre GL uses data URIs for icons and blob for canvas export
//   - worker-src 'self': MapLibre GL v6 loads its worker as a bundled same-origin asset
//   - font-src 'self': next/font/google self-hosts fonts at build time (no googleapis.com needed)
//   - connect-src 'self': all API calls are same-origin; Census geocoding is server-side only
const isDev = process.env.NODE_ENV === "development";

const csp = [
  "default-src 'self'",
  isDev ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "worker-src 'self'",
  "frame-ancestors 'self'",
].join("; ");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-XSS-Protection", value: "1; mode=block" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(self)",
  },
  { key: "Content-Security-Policy", value: csp },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  webpack(config, { nextRuntime }) {
    if (nextRuntime === "edge") {
      // data-source-warmup.ts is imported by instrumentation.ts but only executed in
      // Node.js (guarded by NEXT_RUNTIME check). Alias it to false (empty module) so
      // webpack never traces its node: imports when compiling the Edge bundle.
      config.resolve.alias = {
        ...config.resolve.alias,
        [path.resolve("./lib/server/data-source-warmup")]: false,
      };
    }
    return config;
  },
};

export default nextConfig;
