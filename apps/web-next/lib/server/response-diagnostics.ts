import { randomUUID } from "node:crypto";

export function buildDiagnosticsHeaders(serverTiming: string, request?: Request): Record<string, string> {
  const incomingRequestId = request?.headers.get("x-request-id")?.trim();
  const requestId = incomingRequestId && incomingRequestId.length > 0 ? incomingRequestId : randomUUID();
  return {
    "X-Request-Id": requestId,
    "Server-Timing": serverTiming,
    "Timing-Allow-Origin": "*",
  };
}
