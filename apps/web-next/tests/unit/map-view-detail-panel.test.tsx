/** @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { MapDetailPanel } from "@/components/map-view";
import type { DistrictDetailResponse } from "@/lib/domain/schemas";

function buildPayload(): DistrictDetailResponse {
  return {
    office: "us_house",
    seatId: "AL-01",
    electionView: "general",
    snapshotDate: "2026-04-01",
    updatedAt: "2026-04-02T00:00:00.000Z",
    sourceAttribution: [],
    districtLabel: "AL-1",
    generalElection: {
      partyLanes: [
        {
          party: "DEM",
          hasNominee: true,
          nomineeName: "Clyde Jones",
          primaryOngoing: false,
          primaryDate: null,
          primaryCandidates: [],
          runoffOngoing: false,
          runoffDate: null,
          runoffCandidates: [],
          visibleCandidates: [{ name: "Clyde Jones", context: "general", odds: 31, eliminated: false }],
        },
        {
          party: "REP",
          hasNominee: false,
          nomineeName: null,
          primaryOngoing: true,
          primaryDate: "2026-05-19",
          primaryCandidates: [],
          runoffOngoing: true,
          runoffDate: "2026-06-16",
          runoffCandidates: ["A", "B"],
          visibleCandidates: [{ name: "A", context: "runoff", odds: null, eliminated: false }],
        },
      ],
      kalshiOnlyCandidates: [],
    },
    incumbencyAndControl: {
      controllingParty: "REP",
      incumbentIndividual: "Ken Calvert",
      openSeat: true,
      departureReason: "retiring",
      departedIncumbentParty: "REP",
    },
    competitiveness: {
      pollingStatus: {
        summary: "Likely Republican",
        latestDate: "3/17/2026",
        sourceCount: 3,
        leadingParty: "REP",
        sources: [],
      },
      kalshiGeneralOdds: {
        favoriteParty: "REP",
        favoriteLabel: "Republican party",
        favoriteOdds: 72,
        oddsMap: { "Republican party": 72, "Democratic party": 31 },
      },
      targeting: {
        key: "dccc",
        dcccTarget: true,
        nrccTarget: false,
        dsccTarget: false,
        nrscTarget: false,
      },
    },
    primaryElection: {
      primaryState: "ongoing_runoff",
      primaryType: "partisan_binary",
      advanceCount: 1,
      kalshiOnlyPrimaryCandidates: [],
      parties: [
        {
          party: "DEM",
          hasPrimaryMarket: true,
          candidates: [
            { name: "A", status: "runoff", stage: "runoff", odds: 41, eliminated: false, kalshiMarketUrl: null },
            { name: "B", status: "runoff", stage: "runoff", odds: 39, eliminated: false, kalshiMarketUrl: null },
            { name: "C", status: "primary", stage: "candidate", odds: null, eliminated: true, kalshiMarketUrl: null },
          ],
        },
      ],
    },
    unifiedElection: {
      parties: [
        {
          party: "DEM",
          hasNominee: true,
          nomineeName: "Clyde Jones",
          primaryOngoing: false,
          runoffOngoing: true,
          primaryDate: null,
          runoffDate: "2026-06-16",
          partyGeneralOdds: 31,
          candidates: [
            { name: "A", stage: "runoff", primaryOdds: 41, generalOdds: null, eliminated: false, nameUnmatched: false },
            { name: "B", stage: "runoff", primaryOdds: 39, generalOdds: null, eliminated: false, nameUnmatched: false },
            { name: "Clyde Jones", stage: "nominee", primaryOdds: null, generalOdds: 31, eliminated: false, nameUnmatched: false },
            { name: "C", stage: "candidate", primaryOdds: null, generalOdds: null, eliminated: true, nameUnmatched: false },
          ],
        },
      ],
      kalshiOnlyCandidates: [],
    },
    electionStatus: {
      generalStatus: "unknown",
      primaryState: "ongoing_runoff",
      primaryStatusD: "complete",
      primaryStatusR: "upcoming",
      primaryStatusNP: null,
      runoffCount: 1,
    },
    mapSignals: {
      contentionKey: "contested",
      incumbentParty: "REP",
      marketFavoriteParty: "REP",
      pollingProxyParty: "REP",
      dcccTarget: true,
      nrccTarget: false,
      dsccTarget: false,
      nrscTarget: false,
    },
    candidates: {
      all: [],
      general: [],
      primary: [],
      runoff: [],
    },
  };
}

describe("map detail panel", () => {
  test("general panel renders incumbency and competitiveness sections", () => {
    render(<MapDetailPanel districtDetail={buildPayload()} electionView="general" />);

    expect(screen.getByText("Incumbency and Controlling Party")).toBeInTheDocument();
    expect(screen.getByText("Competitiveness")).toBeInTheDocument();
    expect(screen.getByText("Ken Calvert")).toBeInTheDocument();
    expect(screen.getByText("Open seat")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("Departure")).toBeInTheDocument();
    expect(screen.getByText("retiring")).toBeInTheDocument();
    // Clyde Jones appears in the party lane header (nominee) and the candidate list row
    expect(screen.getAllByText("Clyde Jones").length).toBeGreaterThan(0);
  });

  test("primary panel renders unified election section regardless of electionView", () => {
    render(<MapDetailPanel districtDetail={buildPayload()} electionView="primary" />);

    // Unified panel always shown — section label changed from "Primary Election" to "Election"
    expect(screen.getByText("Election")).toBeInTheDocument();
    // Party label uses partyLabel() — "Democratic party" not raw "DEM"
    expect(screen.getByText("Democratic party")).toBeInTheDocument();
    // Incumbency and competitiveness always present
    expect(screen.getByText("Incumbency and Controlling Party")).toBeInTheDocument();
    expect(screen.getByText("Competitiveness")).toBeInTheDocument();

    // Candidates are hidden by default — expand the DEM lane
    const demToggle = screen.getByRole("button", { name: /democratic party/i });
    fireEvent.click(demToggle);

    // After expanding, candidate rows and odds are visible
    expect(screen.getAllByText("N/A").length).toBeGreaterThan(0);
    expect(screen.getByText("Eliminated")).toBeInTheDocument();
  });
});
