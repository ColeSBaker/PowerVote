/** @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { PowerVoteView } from "@/components/powervote-view";
import type { PowerVoteAllResponse } from "@/lib/domain/schemas";

const fetchMock = vi.fn();

function renderView() {
  function Wrapper() {
    const [locations, setLocations] = React.useState<PowerVoteAllResponse["locations"]>([]);
    return <PowerVoteView locations={locations} setLocations={setLocations} />;
  }
  return render(<Wrapper />);
}

function makeAllElectionsResponse(locations: unknown[]) {
  return {
    ok: true,
    json: async () => ({
      snapshotDate: "2026-04-02",
      updatedAt: "2026-04-02T00:00:00.000Z",
      sourceAttribution: [],
      locations,
    }),
  };
}

function makeLocation(
  label: string,
  stateCode: string,
  houseSeatId: string,
  generalOverrideProps: Record<string, unknown> = {},
  senateSeats: unknown[] = [],
) {
  return {
    label,
    resolvedContext: {
      stateCode,
      houseSeatId,
      senateSeatIds: senateSeats.length ? [`${stateCode}-SEN-C1`] : [],
      governorSeatIds: [],
      lieutenantGovernorSeatIds: [],
      attorneyGeneralSeatIds: [],
    },
    house: {
      office: "us_house",
      snapshotDate: "2026-04-02",
      updatedAt: "2026-04-02T00:00:00.000Z",
      sourceAttribution: [],
      address: { input: label, normalized: label, latitude: null, longitude: null, seatId: houseSeatId },
      elections: [],
      generalOverview: {
        controllingParty: "DEM",
        incumbentIndividual: "OPEN",
        isOpen: true,
        departureReason: "retiring",
        kalshiGeneral: { hasMarket: false, favoriteParty: null, favoriteLabel: null, oddsMap: {} },
        pollingProxy: { summary: "Unknown", latestDate: null, leadingParty: null },
        targeting: { key: "none", label: "None", dcccTarget: false, nrccTarget: false },
        ...generalOverrideProps,
      },
      primaries: [],
    },
    senate: senateSeats,
    governor: [],
    lieutenantGovernor: [],
    attorneyGeneral: [],
    elections: [],
  };
}

describe("powervote view", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  test("fetches combined payload by zipcode and shows office sections", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const senatePayload = {
        office: "us_senate",
        snapshotDate: "2026-04-02",
        updatedAt: "2026-04-02T00:00:00.000Z",
        sourceAttribution: [],
        address: { input: "90210", normalized: "90210", latitude: null, longitude: null, seatId: "CA-SEN-C1" },
        elections: [],
        generalOverview: {
          controllingParty: "DEM",
          incumbentIndividual: "OPEN",
          isOpen: true,
          departureReason: "retiring",
          kalshiGeneral: { hasMarket: false, favoriteParty: null, favoriteLabel: null, oddsMap: {} },
          pollingProxy: { summary: "Unknown", latestDate: null, leadingParty: null },
          targeting: { key: "none", label: "None", dcccTarget: false, nrccTarget: false },
        },
        primaries: [],
      };

      fetchMock.mockResolvedValueOnce(
        makeAllElectionsResponse([makeLocation("90210", "CA", "CA-01", {}, [senatePayload])]),
      );

      renderView();

      fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "90210" } });
      fireEvent.click(screen.getByRole("button", { name: "Look Up Elections" }));

      await waitFor(() =>
        expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/powervote/all?zipcode=90210"),
      );

      expect(screen.getByText("House Elections")).toBeInTheDocument();
      expect(screen.getByText("Senate Elections")).toBeInTheDocument();
      expect(consoleErrorSpy).not.toHaveBeenCalledWith(
        expect.stringContaining("Received `true` for a non-boolean attribute `jsx`"),
      );
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  test("supports compare using a second address submission", async () => {
    fetchMock.mockResolvedValueOnce(
      makeAllElectionsResponse([makeLocation("90210", "CA", "CA-01")]),
    );
    fetchMock.mockResolvedValueOnce(
      makeAllElectionsResponse([makeLocation("10001", "NY", "NY-12")]),
    );

    renderView();

    fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "90210" } });
    fireEvent.click(screen.getByRole("button", { name: "Look Up Elections" }));

    await screen.findByText("House Elections");

    fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "10001" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare Another Location" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/powervote/all?zipcode=10001"),
    );

    expect(screen.getByText("90210")).toBeInTheDocument();
    expect(screen.getByText("10001")).toBeInTheDocument();
  });

  test("prefers full address over zipcode when both are provided", async () => {
    fetchMock.mockResolvedValueOnce(
      makeAllElectionsResponse([makeLocation("1228 Jerome Street, Brooklyn, New York 11239, United States", "NY", "NY-08")]),
    );

    renderView();

    fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "11239" } });
    fireEvent.change(screen.getByLabelText(/Address/i), {
      target: { value: "1228 Jerome Street, Brooklyn, New York 11239, United States" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Look Up Elections" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/v1/powervote/all?address=1228+Jerome+Street%2C+Brooklyn%2C+New+York+11239%2C+United+States",
      ),
    );
  });

  test("shows senate empty state when no senate races are available", async () => {
    fetchMock.mockResolvedValueOnce(
      makeAllElectionsResponse([makeLocation("90210", "CA", "CA-01")]),
    );

    renderView();

    fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "90210" } });
    fireEvent.click(screen.getByRole("button", { name: "Look Up Elections" }));

    await screen.findByText("Senate Elections");
    fireEvent.click(screen.getByRole("button", { name: /senate elections/i }));
    expect(screen.getByText("No Senate race indexed for this state.")).toBeInTheDocument();
  });

  test("shows polling summary and expandable polling source rows", async () => {
    fetchMock.mockResolvedValueOnce(
      makeAllElectionsResponse([
        makeLocation("90210", "CA", "CA-01", {
          pollingProxy: {
            summary: "Toss-up",
            latestDate: "3/17/2026",
            leadingParty: null,
            sources: [
              { outlet: "Cook", rating: "Toss-up", date: "3/17/2026" },
              { outlet: "Inside Elections", rating: "Lean Republican", date: null },
            ],
          },
        }),
      ]),
    );

    renderView();

    fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "90210" } });
    fireEvent.click(screen.getByRole("button", { name: "Look Up Elections" }));

    await screen.findByText("House Elections");
    // House section is open by default (defaultOpen={true}); no click needed to expand it.
    // Polling summary renders inline (no "Polling Proxy:" label in the redesigned UI).
    await screen.findByText("Toss-up");
    expect(screen.getByText("Toss-up")).toBeInTheDocument();
    expect(screen.getByText("Show polling sources (2)")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Show polling sources (2)"));
    expect(screen.getByText("Cook: Toss-up (3/17/2026)")).toBeInTheDocument();
    expect(screen.getByText("Inside Elections: Lean Republican")).toBeInTheDocument();
  });

  // Regression: SeatCardWithMap was calling itself recursively instead of PowerVoteSeatCard,
  // causing an infinite render loop and timeout on every address lookup.
  // This test verifies that inner seat card content (rendered only by PowerVoteSeatCard)
  // is reachable, which is impossible if SeatCardWithMap recurses infinitely.
  test("SeatCardWithMap renders PowerVoteSeatCard content without infinite recursion", async () => {
    fetchMock.mockResolvedValueOnce(
      makeAllElectionsResponse([makeLocation("90210", "CA", "CA-01")]),
    );

    renderView();

    fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "90210" } });
    fireEvent.click(screen.getByRole("button", { name: "Look Up Elections" }));

    // If SeatCardWithMap recursed into itself, this would never resolve — the test
    // would hang and time out rather than find PowerVoteSeatCard-specific content in the DOM.
    // "Show polling sources" is rendered only by PowerVoteSeatCard, not SeatCardWithMap.
    await screen.findByText("Show polling sources (0)");
    expect(screen.getByText("Show polling sources (0)")).toBeInTheDocument();
  });

  test("shows polling source empty state when no source rows exist", async () => {
    fetchMock.mockResolvedValueOnce(
      makeAllElectionsResponse([
        makeLocation("90210", "CA", "CA-01", {
          pollingProxy: { summary: "Unknown", latestDate: null, leadingParty: null, sources: [] },
        }),
      ]),
    );

    renderView();

    fireEvent.change(screen.getByLabelText("Zip Code"), { target: { value: "90210" } });
    fireEvent.click(screen.getByRole("button", { name: "Look Up Elections" }));

    await screen.findByText("House Elections");
    // House section is open by default (defaultOpen={true}); no click needed to expand it.
    await screen.findByText("Show polling sources (0)");
    fireEvent.click(screen.getByText("Show polling sources (0)"));
    expect(screen.getByText("No individual polling sources available.")).toBeInTheDocument();
  });
});
