import { NextResponse, type NextRequest } from "next/server";

import { clientIp, createRateLimiter } from "@/lib/server/rate-limit";

// Routes that call paid or third-party upstreams (Mapbox, US Census geocoder)
// or write to the geocode cache. Static map/detail routes are CDN-cached and
// not limited here.
const WINDOW_MS = 60_000;
const addressSuggestLimiter = createRateLimiter({ limit: 60, windowMs: WINDOW_MS });
const lookupLimiter = createRateLimiter({ limit: 30, windowMs: WINDOW_MS });

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const limiter = pathname.startsWith("/api/v1/address-suggest") ? addressSuggestLimiter : lookupLimiter;
  const result = limiter(clientIp(request.headers));

  if (!result.allowed) {
    const retryAfterSec = Math.max(1, Math.ceil((result.resetAt - Date.now()) / 1000));
    return NextResponse.json(
      { error: "Too many requests. Please try again shortly." },
      { status: 429, headers: { "Retry-After": String(retryAfterSec) } },
    );
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/api/v1/address-suggest",
    "/api/v1/powervote",
    "/api/v1/powervote/all",
    "/api/v1/powervote/compare",
    "/api/v1/zipcode-lookup",
  ],
};
