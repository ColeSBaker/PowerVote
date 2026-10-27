import { NextRequest, NextResponse } from "next/server";

const MAPBOX_BASE = "https://api.mapbox.com/geocoding/v5/mapbox.places";

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  if (!q || q.length < 3) {
    return NextResponse.json({ suggestions: [] });
  }

  const token = process.env.MAPBOX_ACCESS_TOKEN;
  if (!token) {
    return NextResponse.json({ error: "Geocoding not configured" }, { status: 503 });
  }

  const params = new URLSearchParams({
    country: "us",
    types: "address",
    autocomplete: "true",
    limit: "5",
    access_token: token,
  });

  const url = `${MAPBOX_BASE}/${encodeURIComponent(q)}.json?${params.toString()}`;

  let upstream: Response;
  try {
    upstream = await fetch(url, { next: { revalidate: 0 } });
  } catch {
    return NextResponse.json({ error: "Geocoding service unavailable" }, { status: 502 });
  }

  if (!upstream.ok) {
    return NextResponse.json({ error: "Geocoding request failed" }, { status: upstream.status });
  }

  const data = (await upstream.json()) as {
    features?: Array<{
      place_name: string;
      context?: Array<{ id: string; text: string }>;
    }>;
  };

  const suggestions = (data.features ?? []).map((feature) => {
    const postalCtx = feature.context?.find((c) => c.id.startsWith("postcode."));
    return {
      label: feature.place_name,
      zipcode: postalCtx?.text ?? "",
    };
  });

  return NextResponse.json({ suggestions });
}
