import { NextResponse } from "next/server";

import { officeSchema } from "@/lib/domain/schemas";
import { buildMobileCacheHeaders, buildMobileSeatResponse } from "@/lib/server/mobile-api";
import { errorResponse } from "@/lib/server/errors";

export async function GET(request: Request, context: { params: Promise<{ seatId: string }> }) {
  try {
    const { seatId } = await context.params;
    const { searchParams } = new URL(request.url);
    const officeRaw = searchParams.get("office");
    const office = officeRaw ? officeSchema.parse(officeRaw) : undefined;
    const payload = await buildMobileSeatResponse(seatId, office);
    return NextResponse.json(payload, { status: 200, headers: buildMobileCacheHeaders(payload) });
  } catch (error) {
    return errorResponse(error, 404);
  }
}
