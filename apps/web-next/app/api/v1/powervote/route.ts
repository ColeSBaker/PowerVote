import { NextResponse } from "next/server";

import { buildPowerVoteResponse } from "@/lib/server/api-service";
import { buildDiagnosticsHeaders } from "@/lib/server/response-diagnostics";
import { formatServerTiming } from "@/lib/server/server-timing";
import { errorResponse } from "@/lib/server/errors";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const seatId = searchParams.get("seat_id");
  const address = searchParams.get("address");
  if (!seatId && !address) {
    return NextResponse.json({ error: "Missing required query parameter: seat_id or address" }, { status: 400 });
  }
  try {
    let serverTimingHeader = "";
    const payload = await buildPowerVoteResponse({
      seatId: seatId ?? undefined,
      address: address ?? undefined,
      office: searchParams.get("office") ?? undefined,
      onTiming: (timing) => {
        serverTimingHeader = formatServerTiming([
          { name: "load", dur: timing.loadMs },
          { name: "resolve", dur: timing.resolveMs },
          { name: "build", dur: timing.buildMs },
          { name: "schema", dur: timing.schemaMs },
          { name: "total", dur: timing.totalMs },
        ]);
      },
    });
    return NextResponse.json(payload, {
      status: 200,
      headers: {
        "Cache-Control": "public, max-age=300, stale-while-revalidate=600",
        ...buildDiagnosticsHeaders(serverTimingHeader, request),
      },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
