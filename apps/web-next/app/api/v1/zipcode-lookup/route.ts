import { NextResponse } from "next/server";
import { lookupZipcode } from "@/lib/server/zipcode-lookup";
import { errorResponse } from "@/lib/server/errors";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const zipcode = searchParams.get("zipcode");

  if (!zipcode) {
    return NextResponse.json(
      { error: 'Missing required query parameter: "zipcode"' },
      { status: 400 }
    );
  }

  try {
    const result = await lookupZipcode(zipcode);
    return NextResponse.json(result, { status: 200 });
  } catch (error) {
    return errorResponse(error);
  }
}
