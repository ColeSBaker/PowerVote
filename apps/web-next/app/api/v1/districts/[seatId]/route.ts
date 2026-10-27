import { NextResponse } from "next/server";

import { buildDistrictDetailResponse } from "@/lib/server/api-service";
import { errorResponse } from "@/lib/server/errors";

type RouteContext = { params: Promise<{ seatId: string }> };

export async function GET(request: Request, context: RouteContext) {
  const { seatId } = await context.params;
  const { searchParams } = new URL(request.url);
  try {
    const payload = await buildDistrictDetailResponse({
      seatId,
      office: searchParams.get("office") ?? undefined,
      electionView: searchParams.get("election_view") ?? undefined,
      detailVersion: (searchParams.get("detail_version") as "v1" | "v2" | null) ?? undefined,
    });
    return NextResponse.json(payload, {
      status: 200,
      headers: { "Cache-Control": "public, max-age=300, stale-while-revalidate=600" },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
