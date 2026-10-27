import { NextResponse } from "next/server";

import { buildPowerVoteAllResponse } from "@/lib/server/api-service";
import { errorResponse } from "@/lib/server/errors";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const seatId = searchParams.get("seat_id") ?? undefined;
  const address = searchParams.get("address") ?? undefined;
  const zipcode = searchParams.get("zipcode") ?? undefined;
  const compareSeatId = searchParams.get("compare_seat_id") ?? undefined;
  const compareAddress = searchParams.get("compare_address") ?? undefined;
  const compareZipcode = searchParams.get("compare_zipcode") ?? undefined;

  if (!seatId && !address && !zipcode) {
    return NextResponse.json(
      { error: "Missing required query parameter: seat_id or address or zipcode" },
      { status: 400 },
    );
  }

  try {
    const payload = await buildPowerVoteAllResponse({
      seatId,
      address,
      zipcode,
      compareSeatId,
      compareAddress,
      compareZipcode,
    });
    return NextResponse.json(payload, { status: 200 });
  } catch (error) {
    return errorResponse(error);
  }
}
