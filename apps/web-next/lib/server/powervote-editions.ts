import type { Office } from "@/lib/domain/schemas";

export type PowerVoteEditionProfile = {
  id: "house_2026" | "senate_2026" | "governor_2026" | "lieutenant_governor_2026" | "attorney_general_2026";
  office: Office;
  cycle: 2026;
  primaryActiveScore: number;
  primaryCompleteScore: number;
  runoffActiveScore: number;
  runoffKnownScore: number;
};

const EDITIONS: Record<Office, PowerVoteEditionProfile> = {
  us_house: {
    id: "house_2026",
    office: "us_house",
    cycle: 2026,
    primaryActiveScore: 75,
    primaryCompleteScore: 35,
    runoffActiveScore: 88,
    runoffKnownScore: 45,
  },
  us_senate: {
    id: "senate_2026",
    office: "us_senate",
    cycle: 2026,
    primaryActiveScore: 78,
    primaryCompleteScore: 32,
    runoffActiveScore: 90,
    runoffKnownScore: 48,
  },
  us_governor: {
    id: "governor_2026",
    office: "us_governor",
    cycle: 2026,
    primaryActiveScore: 76,
    primaryCompleteScore: 34,
    runoffActiveScore: 89,
    runoffKnownScore: 46,
  },
  us_lieutenant_governor: {
    id: "lieutenant_governor_2026",
    office: "us_lieutenant_governor",
    cycle: 2026,
    primaryActiveScore: 74,
    primaryCompleteScore: 33,
    runoffActiveScore: 87,
    runoffKnownScore: 44,
  },
  us_attorney_general: {
    id: "attorney_general_2026",
    office: "us_attorney_general",
    cycle: 2026,
    primaryActiveScore: 74,
    primaryCompleteScore: 33,
    runoffActiveScore: 87,
    runoffKnownScore: 44,
  },
};

export function getPowerVoteEditionProfile(office: Office): PowerVoteEditionProfile {
  return EDITIONS[office];
}
