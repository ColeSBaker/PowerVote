import { parse } from "csv-parse/sync";

import type { PartyCode } from "@/lib/domain/schemas";

const PARTY_ALIASES: Record<string, PartyCode> = {
  DEM: "DEM",
  DEMOCRATIC: "DEM",
  D: "DEM",
  REP: "REP",
  REPUBLICAN: "REP",
  R: "REP",
  IND: "IND",
  INDEPENDENT: "IND",
  LIB: "LIB",
  LIBERTARIAN: "LIB",
  GRE: "GRE",
  GRN: "GRE",
  GREEN: "GRE",
  OTH: "OTH",
  OTHER: "OTH",
  NP: "NP",
  NONPARTISAN: "NP",
};

export type CsvRow = Record<string, string>;

export function parseCsvText(input: string, keepColumns?: Set<string>): CsvRow[] {
  const rows = parse(input, {
    columns: true,
    skip_empty_lines: true,
    relax_column_count: true,
    trim: true,
  }) as CsvRow[];
  if (!keepColumns) return rows;
  return rows.map((row) => {
    const projected: CsvRow = {};
    for (const col of keepColumns) {
      if (col in row) projected[col] = row[col];
    }
    return projected;
  });
}

export function assertRequiredColumns(rows: CsvRow[], columns: string[], fileLabel: string): void {
  if (!rows.length) {
    throw new Error(`${fileLabel} is empty.`);
  }
  const available = new Set(Object.keys(rows[0]));
  const missing = columns.filter((column) => !available.has(column));
  if (missing.length) {
    throw new Error(`${fileLabel} is missing required columns: ${missing.join(", ")}`);
  }
}

export function parseJsonObject<T extends Record<string, unknown>>(raw: string | undefined): T | null {
  if (!raw || !raw.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as T;
    }
    return null;
  } catch {
    return null;
  }
}

export function parseJsonArray<T>(raw: string | undefined): T[] {
  if (!raw || !raw.trim()) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export function parseBooleanText(raw: string | undefined): boolean {
  const normalized = String(raw ?? "").trim().toLowerCase();
  return normalized === "true" || normalized === "1" || normalized === "yes";
}

export function parseNullableNumber(raw: string | undefined): number | null {
  if (raw === undefined || raw === null || raw === "") {
    return null;
  }
  const num = Number(raw);
  return Number.isFinite(num) ? num : null;
}

export function normalizeSeatId(input: string | undefined): string {
  const text = String(input ?? "").trim().toUpperCase();
  const houseMatch = /^([A-Z]{2})-(AL|\d{1,2})$/.exec(text);
  if (houseMatch) {
    const state = houseMatch[1];
    const district = houseMatch[2] === "AL" ? "AL" : String(Number(houseMatch[2])).padStart(2, "0");
    return `${state}-${district}`;
  }

  const senateMatch = /^([A-Z]{2})-SEN-(C[123](?:-SPL)?|SP1)$/.exec(text);
  if (senateMatch) {
    return `${senateMatch[1]}-SEN-${senateMatch[2]}`;
  }

  if (!text) {
    return text;
  }
  return text;
}

export function isHouseSeatId(input: string | undefined): boolean {
  return /^[A-Z]{2}-(AL|\d{2})$/.test(normalizeSeatId(input));
}

export function isSenateSeatId(input: string | undefined): boolean {
  return /^[A-Z]{2}-SEN-(C[123](?:-SPL)?|SP1)$/.test(normalizeSeatId(input));
}

export function isGovernorSeatId(input: string | undefined): boolean {
  return /^[A-Z]{2}-GOV$/.test(String(input ?? "").trim().toUpperCase());
}

export function isLtGovernorSeatId(input: string | undefined): boolean {
  return /^[A-Z]{2}-LTGOV$/.test(String(input ?? "").trim().toUpperCase());
}

export function isAttorneyGeneralSeatId(input: string | undefined): boolean {
  return /^[A-Z]{2}-AG$/.test(String(input ?? "").trim().toUpperCase());
}

export function normalizePartyCode(input: string | undefined): PartyCode | null {
  if (!input) {
    return null;
  }
  const cleaned = input.replace(/[^A-Za-z]/g, "").toUpperCase();
  return PARTY_ALIASES[cleaned] ?? null;
}
