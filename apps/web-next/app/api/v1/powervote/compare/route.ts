import { NextResponse } from "next/server";
import { z } from "zod";

import { buildPowerVoteCompareResponse } from "@/lib/server/api-service";
import { errorResponse } from "@/lib/server/errors";

const compareBodySchema = z.object({
  addresses: z.array(z.string()).optional(),
  seatIds: z.array(z.string()).optional(),
  office: z.string().optional(),
});

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be valid JSON." }, { status: 400 });
  }

  const parsed = compareBodySchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? "Invalid request body." }, { status: 400 });
  }

  try {
    const payload = await buildPowerVoteCompareResponse(parsed.data);
    return NextResponse.json(payload, { status: 200 });
  } catch (error) {
    return errorResponse(error);
  }
}
