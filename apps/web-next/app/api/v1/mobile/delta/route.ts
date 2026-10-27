import { NextResponse } from "next/server";

import { buildMobileCacheHeaders, buildMobileDeltaResponse } from "@/lib/server/mobile-api";
import { errorResponse } from "@/lib/server/errors";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const since = searchParams.get("since");
    const payload = await buildMobileDeltaResponse(since);
    return NextResponse.json(payload, { status: 200, headers: buildMobileCacheHeaders(payload) });
  } catch (error) {
    return errorResponse(error);
  }
}
