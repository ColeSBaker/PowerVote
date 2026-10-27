/**
 * Fixed-window, in-memory rate limiter.
 *
 * State lives in the module scope of each server instance, so limits are
 * per-instance rather than global. That is enough to stop a single client from
 * burning the Mapbox quota or flooding the geocode cache; put a platform-level
 * limit (Vercel firewall, Cloudflare) in front for stronger guarantees.
 */

export type RateLimitRule = {
  /** Requests allowed per window. */
  limit: number;
  windowMs: number;
};

export type RateLimitResult = {
  allowed: boolean;
  remaining: number;
  /** Epoch ms when the current window resets. */
  resetAt: number;
};

const MAX_TRACKED_KEYS = 10_000;

export function createRateLimiter(rule: RateLimitRule) {
  const windows = new Map<string, { count: number; resetAt: number }>();

  return function check(key: string, now = Date.now()): RateLimitResult {
    let entry = windows.get(key);
    if (!entry || entry.resetAt <= now) {
      if (windows.size >= MAX_TRACKED_KEYS) {
        for (const [k, v] of windows) {
          if (v.resetAt <= now) windows.delete(k);
        }
        // Still full of live windows: drop the oldest-inserted keys.
        while (windows.size >= MAX_TRACKED_KEYS) {
          const oldest = windows.keys().next().value;
          if (oldest === undefined) break;
          windows.delete(oldest);
        }
      }
      entry = { count: 0, resetAt: now + rule.windowMs };
      windows.set(key, entry);
    }
    entry.count += 1;
    return {
      allowed: entry.count <= rule.limit,
      remaining: Math.max(0, rule.limit - entry.count),
      resetAt: entry.resetAt,
    };
  };
}

/** Best-effort client IP from proxy headers (set by Vercel/Cloudflare). */
export function clientIp(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return headers.get("x-real-ip")?.trim() || "unknown";
}
