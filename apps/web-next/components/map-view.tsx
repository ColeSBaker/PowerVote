"use client";

import type { FeatureCollection } from "geojson";
import type { FilterSpecification, GeoJSONSource, Map as MapLibreMap, MapMouseEvent, StyleSpecification } from "maplibre-gl";

import React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  buildFocusFilters,
  buildRegionBoundsLookup,
  buildRegionFilter,
  buildSeatBoundsLookup,
  buildStateBoundsLookup,
  deriveSeatOptions,
  deriveStateOptions,
  getMapRegionForStateCode,
  getStateCodeFromSeatId,
  type MapRegion,
  resolveFocusTarget,
} from "@/lib/client/map-view-focus";
import { loadMapLibre } from "@/lib/client/maplibre";
import type { DistrictDetailResponse, MapDistrictsResponse, UnifiedPartyLane } from "@/lib/domain/schemas";
import { partyLabel } from "@/lib/server/district-detail";

type MapPayload = MapDistrictsResponse;
type DistrictPayload = DistrictDetailResponse;

const GENERAL_COLOR_MODES = [
  { value: "contention", label: "Contention", description: "Combined Kalshi odds + polling signals. Darker = more competitive." },
  { value: "incumbent", label: "Incumbent party", description: "Districts colored by the incumbent's party affiliation." },
  { value: "market_favorite", label: "Kalshi market favorite", description: "Kalshi prediction market implied winner by party." },
  { value: "polling_proxy", label: "Polling favorite proxy", description: "Historical vote margin used as a polling proxy for competitiveness." },
  { value: "targeting", label: "DCCC / NRCC targeting", description: "Congressional campaign committee targeting status." },
  { value: "powervote", label: "PowerVote", description: "PowerVote composite competitiveness score." },
  { value: "kalshi_integrity_general", label: "Kalshi integrity (general)", description: "Data integrity status of Kalshi general election market joins." },
];

const PRIMARY_COLOR_MODES = [
  { value: "primary_status", label: "Primary and runoff state", description: "Current primary and runoff election stage for each district." },
  { value: "primary_kalshi", label: "Kalshi primary market lanes", description: "Kalshi prediction market implied winner in primary races (DEM + REP combined)." },
  { value: "primary_contention_dem", label: "DEM primary contention", description: "Democratic primary contention status: crowded (3+ candidates), contested, runoff, complete, or no primary." },
  { value: "primary_contention_rep", label: "REP primary contention", description: "Republican primary contention status: crowded (3+ candidates), contested, runoff, complete, or no primary." },
  { value: "primary_contention_np",  label: "NP primary contention",  description: "Nonpartisan primary contention status: crowded (3+ candidates), contested, runoff, complete, or no primary." },
  { value: "primary_kalshi_dem", label: "Kalshi DEM primary", description: "Kalshi prediction market presence for Democratic primary races only." },
  { value: "primary_kalshi_rep", label: "Kalshi REP primary", description: "Kalshi prediction market presence for Republican primary races only." },
  { value: "primary_kalshi_np",  label: "Kalshi NP primary",  description: "Kalshi prediction market presence for nonpartisan primary races only." },
  { value: "kalshi_integrity_primary", label: "Kalshi integrity (primary)", description: "Data integrity status of Kalshi primary election market joins (all parties)." },
  { value: "kalshi_integrity_primary_dem", label: "Kalshi integrity (DEM primary)", description: "Data integrity status of Kalshi Democratic primary election market joins." },
  { value: "kalshi_integrity_primary_rep", label: "Kalshi integrity (REP primary)", description: "Data integrity status of Kalshi Republican primary election market joins." },
  { value: "kalshi_integrity_primary_np",  label: "Kalshi integrity (NP primary)",  description: "Data integrity status of Kalshi nonpartisan primary election market joins." },
];

function mapBackgroundColor(theme: "dark" | "light") {
  return theme === "light" ? "#dbe9f7" : "#0f1724";
}

function buildMapStyle(theme: "dark" | "light"): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: {
          "background-color": mapBackgroundColor(theme),
        },
      },
    ],
  };
}

const REGION_ORDER: MapRegion[] = ["contiguous", "alaska", "hawaii"];

function safeSetFilter(map: MapLibreMap, layerId: string, filter: FilterSpecification) {
  try {
    map.setFilter(layerId, filter);
  } catch {
    // Ignore setFilter calls before the map has fully finished loading layers.
  }
}

function safeFitBounds(map: MapLibreMap, bounds: [[number, number], [number, number]] | null, region: MapRegion, focusKind: "all" | "state" | "seat") {
  if (!bounds) return;
  const padding = region === "contiguous" ? 36 : 20;
  const maxZoom = focusKind === "seat" ? 7.25 : region === "contiguous" ? 5.6 : 6.2;
  map.fitBounds(bounds, {
    padding,
    duration: 0,
    maxZoom,
  });
}

function getRegionContainer(region: MapRegion, refs: {
  contiguous: React.RefObject<HTMLDivElement | null>;
  alaska: React.RefObject<HTMLDivElement | null>;
  hawaii: React.RefObject<HTMLDivElement | null>;
}) {
  if (region === "alaska") return refs.alaska.current;
  if (region === "hawaii") return refs.hawaii.current;
  return refs.contiguous.current;
}

export function MapView({ initialSeat }: { initialSeat?: string } = {}) {
  const contiguousMapRef = useRef<HTMLDivElement | null>(null);
  const alaskaMapRef = useRef<HTMLDivElement | null>(null);
  const hawaiiMapRef = useRef<HTMLDivElement | null>(null);
  const mapInstancesRef = useRef<Partial<Record<MapRegion, MapLibreMap>>>({});

  const [office, setOffice] = useState<"us_house" | "us_senate" | "us_governor" | "us_lieutenant_governor" | "us_attorney_general">("us_house");
  const [electionView, setElectionView] = useState<"general" | "primary">("general");
  const [colorMode, setColorMode] = useState<string>("contention");
  const [payload, setPayload] = useState<MapPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedState, setSelectedState] = useState<string>("");
  const [selectedSeat, setSelectedSeat] = useState<string>("");
  const [focusedState, setFocusedState] = useState<string>("");
  const [focusedSeat, setFocusedSeat] = useState<string>("");
  const [districtDetail, setDistrictDetail] = useState<DistrictPayload | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    if (typeof document === "undefined") return;
    const resolveTheme = () => (document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");
    setTheme(resolveTheme());

    const observer = new MutationObserver(() => {
      setTheme(resolveTheme());
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  const modeOptions = useMemo(() => {
    if (electionView !== "general") return PRIMARY_COLOR_MODES;
    const modes = office === "us_house" ? GENERAL_COLOR_MODES : GENERAL_COLOR_MODES.filter((m) => m.value !== "targeting");
    return modes;
  }, [electionView, office]);

  const activeColorModeDesc = modeOptions.find((m) => m.value === colorMode)?.description ?? null;

  useEffect(() => {
    const activeMode = modeOptions.find((option) => option.value === colorMode);
    if (!activeMode) {
      setColorMode(modeOptions[0].value);
    }
  }, [modeOptions, colorMode]);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({
      office,
      election_view: electionView,
      color_mode: colorMode,
    });
    fetch(`/api/v1/map/districts?${params.toString()}`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json()).error || "Failed to load map districts.");
        return response.json();
      })
      .then((data) => {
        if (!cancelled) {
          setPayload(data);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load map data.");
          setPayload(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [office, electionView, colorMode]);

  useEffect(() => {
    if (!selectedSeat) {
      setDistrictDetail(null);
      return;
    }
    let cancelled = false;
    fetch(`/api/v1/districts/${selectedSeat}?office=${office}&election_view=${electionView}&detail_version=v2`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json()).error || "Failed to load district details.");
        return response.json();
      })
      .then((data) => {
        if (!cancelled) setDistrictDetail(data);
      })
      .catch(() => {
        if (!cancelled) setDistrictDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSeat, electionView, office]);

  const districts = payload?.districts ?? [];
  const districtCountByKey = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of districts) {
      counts[d.colorKey] = (counts[d.colorKey] ?? 0) + 1;
    }
    return counts;
  }, [districts]);
  const stateOptions = useMemo(() => deriveStateOptions(districts), [districts]);
  // Use focusedState for seat options (so dropdown only shows seats in focused state, not selected state)
  const seatOptions = useMemo(() => deriveSeatOptions(districts, focusedState || null), [districts, focusedState]);
  const features = useMemo(() => payload?.featureCollection.features ?? [], [payload]);
  const seatBoundsLookup = useMemo(() => buildSeatBoundsLookup(features), [features]);
  const stateBoundsLookup = useMemo(() => buildStateBoundsLookup(features), [features]);
  const regionBoundsLookup = useMemo(() => buildRegionBoundsLookup(features), [features]);

  const selectionTarget = useMemo(
    () =>
      resolveFocusTarget({
        selectedState: selectedState || null,
        selectedSeat: selectedSeat || null,
        districts,
      }),
    [selectedState, selectedSeat, districts],
  );

  const focusTarget = useMemo(
    () =>
      resolveFocusTarget({
        selectedState: focusedState || null,
        selectedSeat: focusedSeat || null,
        districts,
      }),
    [focusedState, focusedSeat, districts],
  );

  const geometryGapNotice = useMemo(() => {
    if (!focusedState) return null;
    if (stateBoundsLookup.has(focusedState)) return null;
    return `No map geometry is currently available for ${focusedState}.`;
  }, [focusedState, stateBoundsLookup]);

  const syncRegionMap = useCallback(
    (region: MapRegion, map: MapLibreMap) => {
      if (!payload) return;

      const source = map.getSource?.("districts") as GeoJSONSource | undefined;
      if (source) {
        source.setData(payload.featureCollection as unknown as FeatureCollection);
      }

      const regionFilter = buildRegionFilter(region);
      // Use selectionTarget for visual highlighting (shows what's selected)
      const selectionFilters = buildFocusFilters(region, selectionTarget);

      safeSetFilter(map, "district-fill-dim", selectionFilters.dimFilter);
      safeSetFilter(map, "district-fill-active", selectionFilters.activeFilter);
      safeSetFilter(map, "district-highlight", selectionFilters.highlightFilter);
      safeSetFilter(map, "district-line", regionFilter);
      safeSetFilter(map, "district-hit", regionFilter);

      // Use focusTarget only for zoom (doesn't zoom if focusTarget is "all")
      const focusedRegion = focusTarget.kind === "all" ? null : getMapRegionForStateCode(focusTarget.stateCode);
      const defaultBounds = regionBoundsLookup.get(region) ?? null;
      const focusBounds =
        focusTarget.kind === "seat"
          ? seatBoundsLookup.get(focusTarget.seatId) ?? null
          : focusTarget.kind === "state"
            ? stateBoundsLookup.get(focusTarget.stateCode) ?? null
            : null;

      const bounds = focusedRegion === region ? focusBounds ?? defaultBounds : defaultBounds;
      safeFitBounds(map, bounds, region, focusTarget.kind);
    },
    [focusTarget, selectionTarget, payload, regionBoundsLookup, seatBoundsLookup, stateBoundsLookup],
  );

  useEffect(() => {
    if (!payload) return;
    const currentPayload = payload;

    let disposed = false;

    async function ensureMaps() {
      const maplibregl = await loadMapLibre();

      for (const region of REGION_ORDER) {
        if (mapInstancesRef.current[region]) continue;

        const container = getRegionContainer(region, {
          contiguous: contiguousMapRef,
          alaska: alaskaMapRef,
          hawaii: hawaiiMapRef,
        });
        if (!container) continue;

        const map = new maplibregl.Map({
          container,
          style: buildMapStyle(theme),
          center: region === "alaska" ? [-152, 63] : region === "hawaii" ? [-157.8, 20.8] : [-96, 38],
          zoom: region === "contiguous" ? 2.8 : 3.2,
          attributionControl: false,
        });
        mapInstancesRef.current[region] = map;

        map.on("load", () => {
          map.addSource("districts", {
            type: "geojson",
            data: currentPayload.featureCollection as unknown as FeatureCollection,
          });

          map.on("click", "district-hit", (event: MapMouseEvent & { features?: Array<{ properties: Record<string, unknown> }> }) => {
            const seat = event.features?.[0]?.properties?.seatId;
            if (!seat) return;
            const nextSeatId = String(seat);
            const stateCode = getStateCodeFromSeatId(nextSeatId);
            if (stateCode) {
              setSelectedState(stateCode);
            }
            setSelectedSeat(nextSeatId);
          });

          map.on("mouseenter", "district-hit", () => {
            map.getCanvas().style.cursor = "pointer";
          });

          map.on("mouseleave", "district-hit", () => {
            map.getCanvas().style.cursor = "";
          });

          map.addLayer({
            id: "district-fill-dim",
            type: "fill",
            source: "districts",
            paint: {
              "fill-color": ["coalesce", ["get", "fillColor"], "#9ca3af"],
              "fill-opacity": 0.18,
            },
          });

          map.addLayer({
            id: "district-fill-active",
            type: "fill",
            source: "districts",
            paint: {
              "fill-color": ["coalesce", ["get", "fillColor"], "#9ca3af"],
              "fill-opacity": 0.78,
            },
          });

          map.addLayer({
            id: "district-line",
            type: "line",
            source: "districts",
            paint: {
              "line-color": "#111827",
              "line-width": 0.35,
              "line-opacity": 0.5,
            },
          });

          map.addLayer({
            id: "district-highlight",
            type: "line",
            source: "districts",
            paint: {
              "line-color": "#f8fafc",
              "line-width": 1.8,
              "line-opacity": 0.95,
            },
          });

          map.addLayer({
            id: "district-hit",
            type: "fill",
            source: "districts",
            paint: {
              "fill-color": "#000000",
              "fill-opacity": 0.001,
            },
          });

          syncRegionMap(region, map);
        });
      }
    }

    ensureMaps().catch((err: unknown) => {
      if (!disposed) {
        setError(err instanceof Error ? err.message : "Failed to initialize map.");
      }
    });

    return () => {
      disposed = true;
    };
  }, [payload, syncRegionMap, theme]);

  useEffect(() => {
    const color = mapBackgroundColor(theme);
    for (const map of Object.values(mapInstancesRef.current)) {
      if (!map) continue;
      (map as unknown as { setPaintProperty?: (layerId: string, property: string, value: string) => void })
        .setPaintProperty?.("background", "background-color", color);
    }
  }, [theme]);

  useEffect(() => {
    REGION_ORDER.forEach((region) => {
      const map = mapInstancesRef.current[region];
      if (!map) return;
      syncRegionMap(region, map);
    });
  }, [syncRegionMap, selectionTarget, focusTarget]);

  useEffect(
    () => () => {
      REGION_ORDER.forEach((region) => {
        mapInstancesRef.current[region]?.remove?.();
      });
      mapInstancesRef.current = {};
    },
    [],
  );

  useEffect(() => {
    if (!payload) {
      setSelectedState("");
      setSelectedSeat("");
      setFocusedState("");
      setFocusedSeat("");
      return;
    }

    if (selectedState && !stateOptions.includes(selectedState)) {
      setSelectedState("");
      setSelectedSeat("");
      return;
    }

    if (selectedSeat && !districts.some((district) => district.seatId === selectedSeat)) {
      setSelectedSeat("");
    }

    if (focusedState && !stateOptions.includes(focusedState)) {
      setFocusedState("");
      setFocusedSeat("");
      return;
    }

    if (focusedSeat && !districts.some((district) => district.seatId === focusedSeat)) {
      setFocusedSeat("");
    }
  }, [payload, selectedSeat, selectedState, focusedState, focusedSeat, stateOptions, districts]);

  // Auto-zoom to seat from URL param once districts are available
  const initialSeatAppliedRef = useRef(false);
  useEffect(() => {
    if (!initialSeat || initialSeatAppliedRef.current || districts.length === 0) return;
    const match = districts.find((d) => d.seatId === initialSeat);
    if (!match) return;
    initialSeatAppliedRef.current = true;
    // Derive the state code from the seat ID (e.g. "TX-07" → "TX")
    const stateCode = initialSeat.split("-")[0];
    setSelectedState(stateCode);
    setFocusedState(stateCode);
    setSelectedSeat(initialSeat);
    setFocusedSeat(initialSeat);
  }, [initialSeat, districts]);

  const handleStateChange = (nextState: string) => {
    setSelectedState(nextState);
    setFocusedState(nextState);
    if (!nextState) {
      setSelectedSeat("");
      setFocusedSeat("");
      return;
    }

    const nextSeatOptions = deriveSeatOptions(districts, nextState);
    if (nextSeatOptions.length === 1) {
      setSelectedSeat(nextSeatOptions[0].seatId);
      setFocusedSeat(nextSeatOptions[0].seatId);
      return;
    }

    if (!nextSeatOptions.some((seat) => seat.seatId === selectedSeat)) {
      setSelectedSeat("");
      setFocusedSeat("");
    }
  };

  const handleSeatChange = (seatId: string) => {
    setSelectedSeat(seatId);
    setFocusedSeat(seatId);
    if (!seatId) {
      return;
    }
    const stateCode = getStateCodeFromSeatId(seatId);
    if (stateCode && stateCode !== selectedState) {
      setSelectedState(stateCode);
      setFocusedState(stateCode);
    }
  };

  return (
    <section className="pv-grid">
      <div className="pv-panel pv-panel--map">
        <div className="pv-controls pv-controls--map-view">
          <label>
            Office
            <select
              value={office}
              onChange={(event) => {
                const nextOffice = event.target.value as "us_house" | "us_senate" | "us_governor" | "us_lieutenant_governor" | "us_attorney_general";
                setOffice(nextOffice);
                setSelectedSeat("");
                setSelectedState("");
                setFocusedSeat("");
                setFocusedState("");
              }}
            >
              <option value="us_house">US House</option>
              <option value="us_senate">US Senate</option>
              <option value="us_governor">Governor</option>
              <option value="us_lieutenant_governor">Lt. Governor</option>
              <option value="us_attorney_general">Attorney General</option>
            </select>
          </label>
          <label>
            Election View
            <select value={electionView} onChange={(event) => setElectionView(event.target.value as "general" | "primary")}>
              <option value="general">General</option>
              <option value="primary">Primary</option>
            </select>
          </label>
          <label>
            Color Mode
            <select value={colorMode} onChange={(event) => setColorMode(event.target.value)}>
              {modeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Zoom to State
            <select value={focusedState} onChange={(event) => handleStateChange(event.target.value)}>
              <option value="">All states</option>
              {stateOptions.map((stateCode) => (
                <option key={stateCode} value={stateCode}>
                  {stateCode}
                </option>
              ))}
            </select>
          </label>
          <label>
            Zoom to Seat
            <select value={focusedSeat} onChange={(event) => handleSeatChange(event.target.value)} disabled={!focusedState}>
              <option value="">All seats</option>
              {seatOptions.map((seat) => (
                <option key={seat.seatId} value={seat.seatId}>
                  {seat.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="pv-map-layout">
          <div
            ref={contiguousMapRef}
            className="pv-map-canvas pv-map-canvas--main"
            aria-label={office === "us_house" ? "Contiguous U.S. congressional districts map" : "Contiguous U.S. statewide election map"}
          />
          <div className="pv-map-insets" aria-label="Alaska and Hawaii inset maps">
            <section className="pv-map-inset">
              <h3>Alaska</h3>
              <div
                ref={alaskaMapRef}
                className="pv-map-canvas pv-map-canvas--inset"
                aria-label={office === "us_house" ? "Alaska congressional districts inset" : "Alaska statewide election inset"}
              />
            </section>
            <section className="pv-map-inset">
              <h3>Hawaii</h3>
              <div
                ref={hawaiiMapRef}
                className="pv-map-canvas pv-map-canvas--inset"
                aria-label={office === "us_house" ? "Hawaii congressional districts inset" : "Hawaii statewide election inset"}
              />
            </section>
          </div>
        </div>
        <div className="pv-map-actions">
          <button type="button" onClick={() => {
            setSelectedState("");
            setSelectedSeat("");
            setFocusedState("");
            setFocusedSeat("");
          }}>
            Clear Focus
          </button>
          {geometryGapNotice ? <p className="pv-map-focus-note">{geometryGapNotice}</p> : null}
          {office === "us_senate" && focusedState && seatOptions.length > 1 ? (
            <p className="pv-map-focus-note">Multiple Senate seats for {focusedState}: select a specific seat.</p>
          ) : null}
        </div>
        {error ? <p className="pv-error">{error}</p> : null}
        <p className="pv-meta">
          Snapshot: <strong>{payload?.snapshotDate ?? "N/A"}</strong> | Updated:{" "}
          <time dateTime={payload?.updatedAt ?? ""}>{payload?.updatedAt ? new Date(payload.updatedAt).toLocaleString() : "N/A"}</time>
        </p>
      </div>

      <aside className="pv-panel">
        <h2>Legend</h2>
        {activeColorModeDesc && <p className="pv-legend-caption">{activeColorModeDesc}</p>}
        <ul className="pv-legend-list">
          {(payload?.legend ?? []).map((item) => {
            const count = districtCountByKey[item.key];
            return (
              <li key={item.key}>
                <span className="pv-legend-chip" style={{ backgroundColor: item.colorHex }} />
                {item.label}
                {count !== undefined && count > 0 ? <span className="pv-legend-count">{count}</span> : null}
              </li>
            );
          })}
        </ul>
        <h2>District Detail</h2>
        {districtDetail ? (
          <MapDetailPanel districtDetail={districtDetail} electionView={electionView} />
        ) : (
          <p className="pv-muted">Click a district on the map to inspect concise candidate and election details.</p>
        )}
      </aside>
    </section>
  );
}

function formatOdds(odds: number | null): string {
  if (odds === null) return "N/A";
  return `${Math.round(odds)}%`;
}

const STAGE_LABEL: Record<string, string> = {
  nominee: "Nominee",
  candidate: "Candidate",
  runoff: "Runoff",
  general: "Advancing",
};

function primaryStateLabel(state: string): string {
  switch (state) {
    case "ongoing_primary": return "Primary ongoing";
    case "ongoing_runoff":  return "Runoff ongoing";
    case "complete":        return "Primary complete";
    default: return "";
  }
}

export function MapDetailPanel(props: { districtDetail: DistrictPayload; electionView: "general" | "primary" }) {
  const { districtDetail } = props;

  return (
    <div className="pv-district-detail">
      <div className="pv-district-header">
        <span className="pv-district-seat-id">{districtDetail.seatId}</span>
        <span className="pv-district-primary-state">{primaryStateLabel(districtDetail.primaryElection.primaryState)}</span>
      </div>

      <UnifiedElectionPanel detail={districtDetail} />

      <div className="pv-district-section">
        <span className="pv-district-section-label">Incumbency and Controlling Party</span>
        <div className="pv-district-rows">
          <div className="pv-seat-row">
            <span className="pv-seat-row-label">Party</span>
            <span>{districtDetail.incumbencyAndControl.controllingParty ?? "N/A"}</span>
          </div>
          <div className="pv-seat-row">
            <span className="pv-seat-row-label">Incumbent</span>
            <span>{districtDetail.incumbencyAndControl.incumbentIndividual}</span>
          </div>
          <div className="pv-seat-row">
            <span className="pv-seat-row-label">Open seat</span>
            <span>{districtDetail.incumbencyAndControl.openSeat ? "Yes" : "No"}</span>
          </div>
          {districtDetail.incumbencyAndControl.departureReason &&
            districtDetail.incumbencyAndControl.departureReason !== "none" && (
            <div className="pv-seat-row">
              <span className="pv-seat-row-label">Departure</span>
              <span>{districtDetail.incumbencyAndControl.departureReason}</span>
            </div>
          )}
        </div>
      </div>

      <div className="pv-district-section">
        <span className="pv-district-section-label">Competitiveness</span>
        <div className="pv-district-rows">
          <div className="pv-seat-row">
            <span className="pv-seat-row-label">Polling</span>
            <span>{districtDetail.competitiveness.pollingStatus.summary}</span>
          </div>
          <div className="pv-seat-row">
            <span className="pv-seat-row-label">Kalshi</span>
            <span>
              {districtDetail.competitiveness.kalshiGeneralOdds.favoriteLabel ?? "N/A"}
              {districtDetail.competitiveness.kalshiGeneralOdds.favoriteOdds !== null && (
                <span className="pv-odds-badge">{formatOdds(districtDetail.competitiveness.kalshiGeneralOdds.favoriteOdds)}</span>
              )}
            </span>
          </div>
          <div className="pv-seat-row">
            <span className="pv-seat-row-label">Targeting</span>
            <span>{districtDetail.competitiveness.targeting.key.toUpperCase()}</span>
          </div>
        </div>
      </div>

      <DistrictLinksSection districtDetail={districtDetail} />
    </div>
  );
}

function DistrictLinksSection({ districtDetail }: { districtDetail: DistrictPayload }) {
  const hasGeneralMarket = Object.keys(districtDetail.competitiveness.kalshiGeneralOdds.oddsMap).length > 0;
  const demLane = districtDetail.primaryElection.parties.find((p) => p.party === "DEM");
  const repLane = districtDetail.primaryElection.parties.find((p) => p.party === "REP");
  const npLane  = districtDetail.primaryElection.parties.find((p) => p.party === "NP");
  const hasKalshiPrimaryD  = demLane?.hasPrimaryMarket ?? false;
  const hasKalshiPrimaryR  = repLane?.hasPrimaryMarket ?? false;
  const hasKalshiPrimaryNP = npLane?.hasPrimaryMarket  ?? false;

  const hasAnyLink = districtDetail.ballotpediaUrl || hasGeneralMarket || hasKalshiPrimaryD || hasKalshiPrimaryR || hasKalshiPrimaryNP;
  if (!hasAnyLink) return null;

  return (
    <div className="pv-district-section">
      <span className="pv-district-section-label">Links</span>
      <div className="pv-district-rows">
        {districtDetail.ballotpediaUrl && (
          <div className="pv-seat-row">
            <a href={districtDetail.ballotpediaUrl} target="_blank" rel="noopener noreferrer" className="pv-detail-link">
              Ballotpedia ↗
            </a>
          </div>
        )}
        {hasGeneralMarket && (
          <div className="pv-seat-row">
            <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (General Election)</button>
          </div>
        )}
        {hasKalshiPrimaryD && (
          <div className="pv-seat-row">
            <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (D Primary)</button>
          </div>
        )}
        {hasKalshiPrimaryR && (
          <div className="pv-seat-row">
            <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (R Primary)</button>
          </div>
        )}
        {hasKalshiPrimaryNP && (
          <div className="pv-seat-row">
            <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (NP Primary)</button>
          </div>
        )}
      </div>
    </div>
  );
}

function UnifiedElectionPanel({ detail }: { detail: DistrictPayload }) {
  const unified = detail.unifiedElection;
  if (!unified) return <p className="pv-muted">Unified view not available.</p>;
  const advanceCount = detail.primaryElection.advanceCount;
  const primaryType = detail.primaryElection.primaryType;
  return (
    <div className="pv-district-section">
      <span className="pv-district-section-label">
        Election
        {primaryType === "jungle" && <span className="pv-race-type-badge">JUNGLE</span>}
        {primaryType !== "jungle" && advanceCount > 1 && <span className="pv-race-type-badge">TOP-{advanceCount}</span>}
      </span>
      <div className="pv-party-lanes">
        {unified.parties.map((lane) => (
          <UnifiedPartyLaneCard key={lane.party} lane={lane} advanceCount={advanceCount} />
        ))}
        {unified.kalshiOnlyCandidates.length > 0 && (
          <div className="pv-party-lane pv-party-lane--kalshi-only">
            <div className="pv-party-lane-header">
              <span className="pv-primary-party">Kalshi Only</span>
            </div>
            <ul className="pv-candidate-list pv-candidate-list--unified">
              <li className="pv-candidate-list__header">
                <span>Candidate</span>
                <span>Stage</span>
                <span>P.Odds</span>
                <span>G.Odds</span>
              </li>
              {unified.kalshiOnlyCandidates.map((c) => (
                <li key={c.name}>
                  <span>{c.name}</span>
                  <span>—</span>
                  <span className="pv-odds-muted">—</span>
                  <span className={c.generalOdds !== null ? "pv-odds-badge" : "pv-odds-muted"}>{formatOdds(c.generalOdds)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function UnifiedPartyLaneCard({ lane, advanceCount = 1 }: { lane: UnifiedPartyLane; advanceCount?: number }) {
  const [expanded, setExpanded] = useState(false);
  const toggle = () => setExpanded((prev) => !prev);
  const expandable = lane.candidates.length > 0 || lane.primaryOngoing || lane.runoffOngoing;

  const header = (
    <div
      className={`pv-party-lane-header pv-party-lane-header--unified${expandable ? " pv-party-lane-header--toggle" : ""}`}
      role={expandable ? "button" : undefined}
      tabIndex={expandable ? 0 : undefined}
      onClick={expandable ? toggle : undefined}
      onKeyDown={expandable ? (e) => { if (e.key === "Enter" || e.key === " ") toggle(); } : undefined}
      aria-expanded={expandable ? expanded : undefined}
    >
      <span className={`pv-primary-party pv-primary-party--${lane.party.toLowerCase()}`}>
        {expandable && <span className="pv-lane-chevron">{expanded ? "▼" : "▶"}</span>}
        {partyLabel(lane.party)}
      </span>
      <span className="pv-party-nominee">{lane.hasNominee ? lane.nomineeName : "TBD"}</span>
      <span />
      <span className={lane.partyGeneralOdds !== null ? "pv-odds-badge" : "pv-odds-muted"}>
        {formatOdds(lane.partyGeneralOdds)}
      </span>
    </div>
  );

  return (
    <div className={`pv-party-lane pv-party-lane--${lane.party.toLowerCase()}`}>
      {header}
      {expandable && expanded && (
        <>
          {lane.primaryOngoing && (
            <p className="pv-party-status">Primary: {lane.primaryDate ?? "date TBD"}</p>
          )}
          {lane.runoffOngoing && (
            <p className="pv-party-status">Runoff: {lane.runoffDate ?? "date TBD"}</p>
          )}
          {lane.candidates.length > 0 && (
            <ul className="pv-candidate-list pv-candidate-list--unified">
              <li className="pv-candidate-list__header">
                <span>Candidate</span>
                <span>Stage</span>
                <span>{advanceCount > 1 ? "Adv.Odds" : "P.Odds"}</span>
                <span>G.Odds</span>
              </li>
              {lane.candidates.map((c) => (
                <li key={`${lane.party}:${c.name}`} className={c.eliminated ? "pv-candidate--eliminated" : undefined}>
                  <span>
                    {c.name}
                    {c.nameUnmatched && <span className="pv-name-unmatched" title="Name from market — not matched to Ballotpedia entry">~</span>}
                    {c.partyAffiliation && (
                      <span className={`pv-party-affil pv-party-affil--${c.partyAffiliation.toLowerCase()}`}>
                        ({c.partyAffiliation})
                      </span>
                    )}
                  </span>
                  <span>{c.eliminated ? "Eliminated" : (STAGE_LABEL[c.stage] ?? c.stage)}</span>
                  <span className={c.primaryOdds !== null ? "pv-odds-badge" : "pv-odds-muted"}>{formatOdds(c.primaryOdds)}</span>
                  <span className={c.generalOdds !== null ? "pv-odds-badge" : "pv-odds-muted"}>{formatOdds(c.generalOdds)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
