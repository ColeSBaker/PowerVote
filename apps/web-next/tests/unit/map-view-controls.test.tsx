/** @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

const fetchMock = vi.fn();
const setFilterMock = vi.fn();
const fitBoundsMock = vi.fn();

class MockMap {
  private handlers = new Map<string, Function[]>();

  constructor() {}

  on(event: string, arg1: unknown, arg2?: unknown) {
    const callback = typeof arg1 === "function" ? arg1 : (arg2 as Function);
    const existing = this.handlers.get(event) ?? [];
    existing.push(callback);
    this.handlers.set(event, existing);
    if (event === "load") {
      callback();
    }
    return this;
  }

  addSource() {}

  addLayer() {}

  getSource() {
    return { setData: vi.fn() };
  }

  getCanvas() {
    return { style: { cursor: "" } };
  }

  setFilter(...args: unknown[]) {
    setFilterMock(...args);
  }

  fitBounds(...args: unknown[]) {
    fitBoundsMock(...args);
  }

  remove() {}
}

vi.mock("maplibre-gl", () => ({
  Map: MockMap,
  setWorkerUrl: vi.fn(),
}));

async function renderMapView() {
  const { MapView } = await import("@/components/map-view");
  render(<MapView />);
}

describe("map view controls", () => {
  beforeEach(() => {
    vi.resetModules();
    fetchMock.mockReset();
    setFilterMock.mockReset();
    fitBoundsMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    (globalThis.URL as any).createObjectURL = vi.fn(() => "blob:mock-url");
    (globalThis.URL as any).revokeObjectURL = vi.fn();
  });

  test("state/seat selectors render and seat list follows selected state", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        office: "us_house",
        electionView: "general",
        colorMode: "contention",
        snapshotDate: "2026-04-02",
        updatedAt: "2026-04-02T00:00:00.000Z",
        sourceAttribution: [],
        legend: [],
        districts: [
          { seatId: "AK-AL", districtLabel: "AK At-Large", state: "AK", colorKey: "contested", colorHex: "#0f766e", contentionKey: "contested", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, targetingKey: "none", primaryState: "none", dcccTarget: false, nrccTarget: false, candidateCount: 1 },
          { seatId: "HI-01", districtLabel: "HI-01", state: "HI", colorKey: "contested", colorHex: "#0f766e", contentionKey: "contested", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, targetingKey: "none", primaryState: "none", dcccTarget: false, nrccTarget: false, candidateCount: 1 },
          { seatId: "HI-02", districtLabel: "HI-02", state: "HI", colorKey: "contested", colorHex: "#0f766e", contentionKey: "contested", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, targetingKey: "none", primaryState: "none", dcccTarget: false, nrccTarget: false, candidateCount: 1 },
        ],
        featureCollection: {
          type: "FeatureCollection",
          features: [],
        },
      }),
    });

    await renderMapView();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const stateSelect = screen.getByLabelText("Zoom to State");
    const seatSelect = screen.getByLabelText("Zoom to Seat");
    expect(stateSelect).toBeInTheDocument();
    expect(seatSelect).toBeInTheDocument();

    fireEvent.change(stateSelect, { target: { value: "HI" } });
    expect(screen.getByRole("option", { name: "HI-01" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "HI-02" })).toBeInTheDocument();
  });

  test("state and seat selection route to focused seat detail lookup", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          office: "us_house",
          electionView: "general",
          colorMode: "contention",
          snapshotDate: "2026-04-02",
          updatedAt: "2026-04-02T00:00:00.000Z",
          sourceAttribution: [],
          legend: [],
          districts: [
            { seatId: "AK-AL", districtLabel: "AK At-Large", state: "AK", colorKey: "contested", colorHex: "#0f766e", contentionKey: "contested", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, targetingKey: "none", primaryState: "none", dcccTarget: false, nrccTarget: false, candidateCount: 1 },
            { seatId: "HI-01", districtLabel: "HI-01", state: "HI", colorKey: "contested", colorHex: "#0f766e", contentionKey: "contested", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, targetingKey: "none", primaryState: "none", dcccTarget: false, nrccTarget: false, candidateCount: 1 },
            { seatId: "CA-01", districtLabel: "CA-01", state: "CA", colorKey: "contested", colorHex: "#0f766e", contentionKey: "contested", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, targetingKey: "none", primaryState: "none", dcccTarget: false, nrccTarget: false, candidateCount: 1 },
          ],
          featureCollection: {
            type: "FeatureCollection",
            features: [
              { type: "Feature", properties: { seatId: "AK-AL", state: "AK", fillColor: "#0f766e" }, geometry: { type: "Polygon", coordinates: [[[-150, 60], [-149, 60], [-149, 61], [-150, 60]]] } },
              { type: "Feature", properties: { seatId: "HI-01", state: "HI", fillColor: "#0f766e" }, geometry: { type: "Polygon", coordinates: [[[-158, 21], [-157, 21], [-157, 22], [-158, 21]]] } },
              { type: "Feature", properties: { seatId: "CA-01", state: "CA", fillColor: "#0f766e" }, geometry: { type: "Polygon", coordinates: [[[-122, 38], [-121, 38], [-121, 39], [-122, 38]]] } },
            ],
          },
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          office: "us_house",
          seatId: "CA-01",
          electionView: "general",
          snapshotDate: "2026-04-02",
          updatedAt: "2026-04-02T00:00:00.000Z",
          sourceAttribution: [],
          districtLabel: "CA-01",
          generalElection: { partyLanes: [], kalshiOnlyCandidates: [] },
          incumbencyAndControl: { controllingParty: null, incumbentIndividual: "Nancy Pelosi", openSeat: true, departureReason: "unknown", departedIncumbentParty: null },
          competitiveness: { pollingStatus: { summary: "Unknown", latestDate: null, sourceCount: 0, leadingParty: null, sources: [] }, kalshiGeneralOdds: { favoriteParty: null, favoriteLabel: null, favoriteOdds: null, oddsMap: {} }, targeting: { key: "none", dcccTarget: false, nrccTarget: false } },
          primaryElection: { primaryState: "none", parties: [] },
          electionStatus: { generalStatus: "unknown", primaryState: "none", primaryStatusD: null, primaryStatusR: null, runoffCount: 0 },
          mapSignals: { contentionKey: "unknown", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, dcccTarget: false, nrccTarget: false },
          candidates: { all: [], general: [], primary: [], runoff: [] },
        }),
      });

    await renderMapView();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Zoom to State"), { target: { value: "CA" } });
    expect(screen.getByRole("option", { name: "CA-01" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Zoom to Seat"), { target: { value: "CA-01" } });
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/districts/CA-01?office=us_house&election_view=general&detail_version=v2"),
    );
  });

  test("office switch triggers senate map fetch", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          office: "us_house",
          mapMode: "district",
          electionView: "general",
          colorMode: "contention",
          snapshotDate: "2026-04-02",
          updatedAt: "2026-04-02T00:00:00.000Z",
          sourceAttribution: [],
          legend: [],
          districts: [],
          featureCollection: { type: "FeatureCollection", features: [] },
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          office: "us_senate",
          mapMode: "statewide",
          electionView: "general",
          colorMode: "contention",
          snapshotDate: "2026-04-02",
          updatedAt: "2026-04-02T00:00:00.000Z",
          sourceAttribution: [],
          legend: [],
          districts: [],
          featureCollection: { type: "FeatureCollection", features: [] },
        }),
      });

    await renderMapView();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Office"), { target: { value: "us_senate" } });
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/map/districts?office=us_senate&election_view=general&color_mode=contention"),
    );
  });

  test("map filters never use legacy invalid empty filter literals", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        office: "us_house",
        electionView: "general",
        colorMode: "contention",
        snapshotDate: "2026-04-02",
        updatedAt: "2026-04-02T00:00:00.000Z",
        sourceAttribution: [],
        legend: [],
        districts: [{ seatId: "CA-01", districtLabel: "CA-01", state: "CA", colorKey: "contested", colorHex: "#0f766e", contentionKey: "contested", incumbentParty: null, marketFavoriteParty: null, pollingProxyParty: null, targetingKey: "none", primaryState: "none", dcccTarget: false, nrccTarget: false, candidateCount: 1 }],
        featureCollection: {
          type: "FeatureCollection",
          features: [
            { type: "Feature", properties: { seatId: "CA-01", state: "CA", fillColor: "#0f766e" }, geometry: { type: "Polygon", coordinates: [[[-122, 38], [-121, 38], [-121, 39], [-122, 38]]] } },
          ],
        },
      }),
    });

    await renderMapView();
    await waitFor(() => expect(setFilterMock).toHaveBeenCalled());

    const invalidLegacyEmptyFilterSeen = setFilterMock.mock.calls.some(([, filter]) => JSON.stringify(filter) === JSON.stringify(["==", 1, 0]));
    expect(invalidLegacyEmptyFilterSeen).toBe(false);
  });
});
