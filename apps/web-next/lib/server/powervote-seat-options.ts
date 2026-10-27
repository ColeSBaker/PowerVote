import { isAttorneyGeneralSeatId, isGovernorSeatId, isHouseSeatId, isLtGovernorSeatId, isSenateSeatId, normalizeSeatId } from "@/lib/server/csv";
import type { GeneralRow } from "@/lib/server/data-source";
import { ClientInputError } from "@/lib/server/errors";

export type SeatOption = {
  seatId: string;
  seatLabel: string;
};

export type StateSeatOption = {
  stateCode: string;
  seats: SeatOption[];
};

function seatSortValue(seatLabel: string): number {
  if (seatLabel === "AL") return -1;
  if (seatLabel.startsWith("C")) return Number.parseInt(seatLabel.slice(1), 10) || 9997;
  if (seatLabel === "SP1") return 9998;
  const num = Number(seatLabel);
  return Number.isFinite(num) ? num : 9999;
}

export function buildStateSeatOptions(generalRows: Array<Pick<GeneralRow, "seat">>): StateSeatOption[] {
  const byState = new Map<string, Set<string>>();
  for (const row of generalRows) {
    const seatId = normalizeSeatId(row.seat);
    const [stateCode, district] = seatId.split("-");
    if (!stateCode || !district) continue;
    if (!byState.has(stateCode)) byState.set(stateCode, new Set());
    byState.get(stateCode)!.add(seatId);
  }

  return Array.from(byState.entries())
    .map(([stateCode, seats]) => {
      const seatEntries = Array.from(seats)
        .map((seatId) => {
          const district = seatId.startsWith(`${stateCode}-SEN-`) ? seatId.replace(`${stateCode}-SEN-`, "") : seatId.split("-")[1];
          return {
            seatId,
            seatLabel: district,
          };
        })
        .sort((left, right) => {
          const valueDiff = seatSortValue(left.seatLabel) - seatSortValue(right.seatLabel);
          if (valueDiff !== 0) return valueDiff;
          return left.seatId.localeCompare(right.seatId);
        });
      return {
        stateCode,
        seats: seatEntries,
      };
    })
    .sort((left, right) => left.stateCode.localeCompare(right.stateCode));
}

export function normalizeRequestedSeatId(rawSeatId: string): string {
  const normalized = normalizeSeatId(rawSeatId);
  if (!isHouseSeatId(normalized) && !isSenateSeatId(normalized) && !isGovernorSeatId(normalized) && !isLtGovernorSeatId(normalized) && !isAttorneyGeneralSeatId(normalized)) {
    throw new ClientInputError(`Invalid seat_id: ${rawSeatId}`);
  }
  return normalized;
}
