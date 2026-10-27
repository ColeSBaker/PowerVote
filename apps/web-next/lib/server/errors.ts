import { NextResponse } from "next/server";
import { ZodError } from "zod";

/**
 * An error caused by the caller's input (unknown seat, bad zipcode, ambiguous
 * lookup). Its message is safe to return to the client verbatim.
 */
export class ClientInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ClientInputError";
  }
}

/**
 * Maps a caught error to a JSON error response without leaking internals.
 *
 * - ClientInputError → its message, with `clientStatus` (400 by default)
 * - ZodError (bad query/body params) → generic validation message, 400
 * - anything else → logged server-side, generic 500
 */
export function errorResponse(error: unknown, clientStatus = 400): NextResponse {
  if (error instanceof ClientInputError) {
    return NextResponse.json({ error: error.message }, { status: clientStatus });
  }
  if (error instanceof ZodError) {
    return NextResponse.json({ error: "Invalid request parameters." }, { status: 400 });
  }
  console.error(error);
  return NextResponse.json({ error: "Internal server error." }, { status: 500 });
}
