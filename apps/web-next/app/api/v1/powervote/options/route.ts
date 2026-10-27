import { NextResponse } from "next/server";

import { buildPowerVoteSeatOptionsResponse } from "@/lib/server/api-service";
import { errorResponse } from "@/lib/server/errors";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  try {
    const payload = await buildPowerVoteSeatOptionsResponse({
      office: searchParams.get("office") ?? undefined,
    });
    return NextResponse.json(payload, { status: 200 });
  } catch (error) {
    return errorResponse(error);
  }
}
