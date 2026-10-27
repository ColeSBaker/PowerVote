"use client";

import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";

import type { PowerVoteAllResponse, PowerVoteResponse } from "@/lib/domain/schemas";
import { computeLocationSummary, hasCompetitiveRace } from "@/lib/domain/powervote-summary";
import { useSavedLocations } from "@/lib/client/use-saved-locations";
import { AddressAutocomplete } from "@/components/address-autocomplete";

// Feature flag: set to false to hide the inline district map on seat cards.
// When false, MiniSeatMap is never imported — its MapLibre dependencies stay
// out of the PowerVote bundle entirely.
const ENABLE_MINI_MAP = false;

const MiniSeatMap = ENABLE_MINI_MAP
  ? dynamic(() => import("@/components/mini-seat-map").then((m) => ({ default: m.MiniSeatMap })), { ssr: false })
  : null;

type PowerVotePayload = PowerVoteResponse;
type PowerVoteAllPayload = PowerVoteAllResponse;

const ALL_PARTY_OPTIONS = [
  { code: "DEM", label: "Dem" },
  { code: "REP", label: "Rep" },
  { code: "NP",  label: "NP" },
  { code: "IND", label: "Ind" },
  { code: "LIB", label: "Lib" },
];

function usePartyPrefs(): { prefs: string[]; toggle: (party: string) => void } {
  const [prefs, setPrefs] = useState<string[]>(() => {
    try {
      const raw = typeof window !== "undefined" ? localStorage.getItem("pv-party-prefs") : null;
      return raw ? (JSON.parse(raw) as string[]) : ["DEM", "REP", "NP"];
    } catch {
      return ["DEM", "REP", "NP"];
    }
  });
  const toggle = (party: string) => {
    setPrefs((prev) => {
      const next = prev.includes(party) ? prev.filter((p) => p !== party) : [...prev, party];
      try { localStorage.setItem("pv-party-prefs", JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };
  return { prefs, toggle };
}

function PartySelector({ prefs, onToggle }: { prefs: string[]; onToggle: (party: string) => void }) {
  return (
    <div className="pv-party-selector">
      <span className="pv-party-selector-label">Primary parties:</span>
      {ALL_PARTY_OPTIONS.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          className={`pv-party-toggle pv-party-toggle--${code.toLowerCase()}${prefs.includes(code) ? " pv-party-toggle--active" : ""}`}
          onClick={() => onToggle(code)}
          aria-pressed={prefs.includes(code)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function bandClass(band: string | null | undefined) {
  if (!band) return "pv-seat--unknown";
  if (band.includes("dem")) return "pv-seat--dem";
  if (band.includes("rep")) return "pv-seat--rep";
  if (band === "toss_up") return "pv-seat--tossup";
  return "pv-seat--unknown";
}

function BandBadge({ band }: { band: string }) {
  return <span className={`pv-band-badge pv-band-badge--${band}`}>{band.replace(/_/g, " ")}</span>;
}

function OfficeSeatSummary({ payload }: { payload: PowerVotePayload }) {
  const generalElection = payload.elections.find((e) => e.electionKind === "general");
  const overview = payload.generalOverview;
  const seatId = payload.address.seatId ?? "—";
  const party = overview?.controllingParty ?? "—";
  const marketSummary = overview?.kalshiGeneral.hasMarket && Object.keys(overview.kalshiGeneral.oddsMap).length
    ? Object.entries(overview.kalshiGeneral.oddsMap).slice(0, 2).map(([l, o]) => `${l} ${o}`).join(" · ")
    : "No market";
  const pollingSummary = overview?.pollingProxy.summary ?? "—";
  const score = generalElection?.score != null ? generalElection.score.toFixed(1) : "—";
  const band = generalElection?.band;

  return (
    <div className="pv-seat-summary-row">
      <span className="pv-seat-summary-id">{seatId}</span>
      <span className={`pv-seat-summary-party pv-seat-summary-party--${(party ?? "unknown").toLowerCase()}`}>{party}</span>
      <span className="pv-seat-summary-market">{marketSummary}</span>
      <span className="pv-seat-summary-polling">{pollingSummary}</span>
      <span className={`pv-seat-summary-score${band ? ` pv-band-score--${band}` : ""}`}>{score}</span>
    </div>
  );
}

function OfficeSection({ label, accentKey, seats, children, defaultOpen = false }: { label: string; accentKey: string; seats?: PowerVotePayload[]; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`pv-office-section pv-office--${accentKey}`}>
      <button
        type="button"
        className="pv-office-section-header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="pv-office-accent" />
        <span className="pv-office-label">{label}</span>
        <span className="pv-office-chevron">{open ? "▲" : "▼"}</span>
      </button>
      {!open && seats && seats.length > 0 && (
        <div className="pv-seat-summaries">
          {seats.map((p, i) => <OfficeSeatSummary key={p.address.seatId ?? i} payload={p} />)}
        </div>
      )}
      {open && <div className="pv-office-content">{children}</div>}
    </div>
  );
}

function PowerVoteSeatCard({ payload, title, partyPrefs }: { payload: PowerVotePayload; title: string; partyPrefs: string[] }) {
  const seatId = payload.address.seatId;
  const [showSources, setShowSources] = useState(false);
  const generalElection = payload.elections.find((e) => e.electionKind === "general");
  const breakdown = generalElection?.breakdown;
  const overview = payload.generalOverview;
  const pollingSources = overview?.pollingProxy.sources ?? [];

  const generalOddsMap = overview?.kalshiGeneral.oddsMap ?? {};
  const primariesByParty = Object.fromEntries((payload.primaries ?? []).map((p) => [p.party, p]));
  const laneParties = collectLaneParties(payload).filter((p) => partyPrefs.includes(p));

  return (
    <article className={`pv-seat-card ${bandClass(generalElection?.band)}`}>
      <div className="pv-seat-header">
        <span className="pv-seat-title">{title}</span>
        {generalElection?.band && <BandBadge band={generalElection.band} />}
        {generalElection?.score != null && (
          <span className="pv-seat-score">{generalElection.score.toFixed(1)}</span>
        )}
        {seatId && !ENABLE_MINI_MAP && (
          <a
            href={`/map?seat=${encodeURIComponent(seatId)}`}
            className="pv-view-on-map-btn"
            title={`View ${seatId} on the map`}
          >
            View on Map
          </a>
        )}
        {generalElection?.ballotpediaUrl && (
          <a
            href={generalElection.ballotpediaUrl}
            className="pv-view-on-map-btn"
            target="_blank"
            rel="noopener noreferrer"
            title="View on Ballotpedia"
          >
            Ballotpedia ↗
          </a>
        )}
      </div>

      {overview && (
        <div className="pv-seat-general-context">
          <span>
            <strong>{overview.controllingParty ?? "—"}</strong>
            {" · "}{overview.incumbentIndividual}
            {overview.isOpen ? " · Open seat" : ""}
          </span>
          {overview.targeting.key !== "none" && overview.targeting.key !== "n_a" && (
            <span className="pv-seat-context-tag">{overview.targeting.label}</span>
          )}
          {overview.pollingProxy.summary && (
            <span>{overview.pollingProxy.summary}</span>
          )}
        </div>
      )}

      {laneParties.length > 0 && (
        <div className="pv-party-lanes pv-seat-lanes">
          {laneParties.map((party) => (
            <PowerVotePartyLane
              key={party}
              party={party}
              primary={primariesByParty[party]}
              generalOdds={partyGeneralOdds(generalOddsMap, party, primariesByParty[party]?.winner)}
            />
          ))}
        </div>
      )}

      <div className="pv-seat-footer">
        {(overview?.kalshiGeneral.hasMarket || primariesByParty["DEM"]?.kalshiPrimary.hasMarket || primariesByParty["REP"]?.kalshiPrimary.hasMarket || primariesByParty["NP"]?.kalshiPrimary.hasMarket) && (
          <div className="pv-seat-links">
            {overview?.kalshiGeneral.hasMarket && (
              <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (General Election)</button>
            )}
            {primariesByParty["DEM"]?.kalshiPrimary.hasMarket && (
              <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (D Primary)</button>
            )}
            {primariesByParty["REP"]?.kalshiPrimary.hasMarket && (
              <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (R Primary)</button>
            )}
            {primariesByParty["NP"]?.kalshiPrimary.hasMarket && (
              <button type="button" disabled className="pv-detail-link pv-detail-link--disabled">Kalshi (NP Primary)</button>
            )}
          </div>
        )}
        {breakdown && (
          <details className="pv-seat-details">
            <summary>Scoring breakdown</summary>
            <div className="pv-breakdown">
              {breakdown.incumbency && (
                <span>Incumbency {breakdown.incumbency.score?.toFixed(1)} <em>({(breakdown.incumbency.weight * 100).toFixed(0)}%)</em></span>
              )}
              <span>Market {breakdown.market.score?.toFixed(1)} <em>({(breakdown.market.weight * 100).toFixed(0)}%)</em></span>
              <span>Polling {breakdown.pollingProxy.score?.toFixed(1)} <em>({(breakdown.pollingProxy.weight * 100).toFixed(0)}%)</em></span>
              <span>Targeting {breakdown.targeting.score?.toFixed(1)} <em>({(breakdown.targeting.weight * 100).toFixed(0)}%)</em></span>
              {generalElection?.reason && <span className="pv-muted">{generalElection.reason}</span>}
            </div>
          </details>
        )}
        <div className="pv-seat-row">
          <button type="button" className="pv-sources-toggle" onClick={() => setShowSources((v) => !v)}>
            Show polling sources ({pollingSources.length})
          </button>
        </div>
        {showSources && (
          <div className="pv-sources-expanded">
            {pollingSources.length > 0 ? (
              <ul className="pv-sources-list">
                {pollingSources.map((s, i) => (
                  <li key={`${s.outlet}:${i}`}>
                    {s.date ? `${s.outlet}: ${s.rating} (${s.date})` : `${s.outlet}: ${s.rating}`}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="pv-muted">No individual polling sources available.</p>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

function SeatCardWithMap({ payload, title, partyPrefs }: { payload: PowerVotePayload; title: string; partyPrefs: string[] }) {
  const seatId = payload.address.seatId;
  const [showMap, setShowMap] = useState(false);
  return (
    <div className="pv-seat-card-wrap">
      <PowerVoteSeatCard payload={payload} title={title} partyPrefs={partyPrefs} />
      {ENABLE_MINI_MAP && seatId && (
        <div className="pv-mini-map-section">
          <button
            type="button"
            className="pv-mini-map-toggle"
            onClick={() => setShowMap((v) => !v)}
            aria-expanded={showMap}
          >
            <span className="pv-mini-map-toggle__icon">{showMap ? "▲" : "▼"}</span>
            {showMap ? "Hide district map" : "Show district map"}
          </button>
          {showMap && MiniSeatMap && <MiniSeatMap seatId={seatId} />}
        </div>
      )}
    </div>
  );
}

function PowerVoteAllLocationCard({ location, showPowerVoteIndicator, onRemove, onSave, saved, partyPrefs }: { location: PowerVoteAllPayload["locations"][number]; showPowerVoteIndicator?: boolean; onRemove?: () => void; onSave?: () => void; saved?: boolean; partyPrefs: string[] }) {
  return (
    <article className="pv-location-card">
      <div className="pv-location-header">
        <div className="pv-location-title-row">
          <h3 className="pv-location-title" title={location.label} data-full={location.label}>{location.label}</h3>
          {onRemove && (
            <button type="button" className="pv-location-remove" onClick={onRemove} aria-label="Remove location">
              ×
            </button>
          )}
        </div>
        <div className="pv-location-meta-row">
          {showPowerVoteIndicator && (
            <span className="pv-powervote-badge" title="This location has more competitive races based on PowerVote scoring.">
              POWERVOTE
            </span>
          )}
          {onSave && (
            <button
              type="button"
              className={`pv-save-btn${saved ? " pv-save-btn--saved" : ""}`}
              onClick={onSave}
              disabled={saved}
              aria-label={saved ? "Location saved" : "Save location"}
            >
              {saved ? "Saved" : "Save"}
            </button>
          )}
          <span className="pv-location-context">
            {location.resolvedContext.stateCode} · House {location.resolvedContext.houseSeatId}
            {location.resolvedContext.senateSeatIds.length ? ` · Senate ${location.resolvedContext.senateSeatIds.join(", ")}` : ""}
            {location.resolvedContext.governorSeatIds.length ? ` · Gov ${location.resolvedContext.governorSeatIds.join(", ")}` : ""}
          </span>
        </div>
        <PowerVoteSummaryBanner location={location} partyPrefs={partyPrefs} />
      </div>

      <div className="pv-office-sections">
        <OfficeSection label="House Elections" accentKey="house" seats={[location.house]} defaultOpen={true}>
          <SeatCardWithMap payload={location.house} title={location.house.address.seatId ?? "House Seat"} partyPrefs={partyPrefs} />
        </OfficeSection>
        <OfficeSection label="Senate Elections" accentKey="senate" seats={location.senate}>
          {location.senate.length ? (
            location.senate.map((p, i) => (
              <SeatCardWithMap key={p.address.seatId ?? i} payload={p} title={p.address.seatId ?? `Senate Seat ${i + 1}`} partyPrefs={partyPrefs} />
            ))
          ) : (
            <p className="pv-muted">No Senate race indexed for this state.</p>
          )}
        </OfficeSection>
        <OfficeSection label="Governor" accentKey="governor" seats={location.governor}>
          {location.governor.length ? (
            location.governor.map((p, i) => (
              <SeatCardWithMap key={p.address.seatId ?? i} payload={p} title={p.address.seatId ?? `Governor Seat ${i + 1}`} partyPrefs={partyPrefs} />
            ))
          ) : (
            <p className="pv-muted">No Governor race indexed for this state.</p>
          )}
        </OfficeSection>
        <OfficeSection label="Lt. Governor" accentKey="lt-governor" seats={location.lieutenantGovernor}>
          {location.lieutenantGovernor.length ? (
            location.lieutenantGovernor.map((p, i) => (
              <SeatCardWithMap key={p.address.seatId ?? i} payload={p} title={p.address.seatId ?? `Lt. Governor Seat ${i + 1}`} partyPrefs={partyPrefs} />
            ))
          ) : (
            <p className="pv-muted">No Lt. Governor race indexed for this state.</p>
          )}
        </OfficeSection>
        <OfficeSection label="Attorney General" accentKey="ag" seats={location.attorneyGeneral}>
          {location.attorneyGeneral.length ? (
            location.attorneyGeneral.map((p, i) => (
              <SeatCardWithMap key={p.address.seatId ?? i} payload={p} title={p.address.seatId ?? `Attorney General Seat ${i + 1}`} partyPrefs={partyPrefs} />
            ))
          ) : (
            <p className="pv-muted">No Attorney General race indexed for this state.</p>
          )}
        </OfficeSection>
      </div>
    </article>
  );
}

const PARTY_LABELS: Record<string, string> = { DEM: "Dem", REP: "Rep", NP: "NP", IND: "Ind", LIB: "Lib", GRE: "Grn", OTH: "Oth" };
const PARTY_CODE_FROM_LABEL: Record<string, string> = { "Democrat": "DEM", "Democratic": "DEM", "Democratic party": "DEM", "Republican": "REP", "Republican party": "REP", "Non-Partisan": "NP", "Independent": "IND", "Libertarian": "LIB", "Green": "GRE" };
const PARTY_LANE_ORDER = ["DEM", "REP", "NP", "IND", "LIB", "GRE", "OTH"];

// Mirrors normalizeName / partyOddsLabels / partyOddsForLane from lib/server/district-detail.ts
// (duplicated here because district-detail is server-only; these are pure string utils)
function _normName(v: string): string {
  const base = v.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
  const tokens = base.split(" ");
  if (tokens.length > 2) return tokens.filter((t, i) => t.length > 1 || i === 0 || i === tokens.length - 1).join(" ");
  return base;
}
function _partyLabels(party: string): string[] {
  if (party === "DEM") return ["democratic party", "democratic dfl party", "democratic", "democrat", "dem", "dfl"];
  if (party === "REP") return ["republican party", "republican", "gop", "rep"];
  if (party === "GRE") return ["green party", "green", "gre"];
  if (party === "LIB") return ["libertarian party", "libertarian", "lib"];
  if (party === "IND") return ["independent", "ind"];
  return [party.toLowerCase()];
}
function partyGeneralOdds(oddsMap: Record<string, number>, party: string, nominee?: string | null): number | null {
  const norm = new Map<string, number>();
  for (const [k, v] of Object.entries(oddsMap)) norm.set(_normName(k), v);
  // 1. Try party-label matching ("republican party", "democratic party", etc.)
  for (const label of _partyLabels(party)) {
    const hit = norm.get(_normName(label));
    if (typeof hit === "number") return hit;
  }
  // 2. Fall back to nominee-name matching (e.g. "James Talarico": 42 in the DEM lane)
  if (nominee) {
    const hit = norm.get(_normName(nominee));
    if (typeof hit === "number") return hit;
  }
  return null;
}

function collectLaneParties(payload: PowerVotePayload): string[] {
  const seen = new Set<string>();
  for (const p of payload.primaries ?? []) {
    if (p.status !== "No Primary" && p.status !== "Unknown") seen.add(p.party);
  }
  for (const key of Object.keys(payload.generalOverview?.kalshiGeneral.oddsMap ?? {})) {
    // Try exact match first, then normalization via _partyLabels
    const direct = PARTY_CODE_FROM_LABEL[key];
    if (direct) { seen.add(direct); continue; }
    for (const code of ["DEM", "REP", "NP", "IND", "LIB", "GRE"]) {
      if (_partyLabels(code).includes(_normName(key))) { seen.add(code); break; }
    }
  }
  const ctrl = payload.generalOverview?.controllingParty;
  if (ctrl) seen.add(ctrl);
  return PARTY_LANE_ORDER.filter((p) => seen.has(p));
}

type PrimaryEntry = NonNullable<PowerVotePayload["primaries"]>[number];

function PowerVotePartyLane({ party, primary, generalOdds }: { party: string; primary: PrimaryEntry | undefined; generalOdds: number | null }) {
  const isActive = primary ? ["Upcoming", "In Progress", "Runoff Active"].includes(primary.status) : false;
  const [open, setOpen] = useState(isActive);
  const partyKey = party.toLowerCase();

  const runoffCandidates = primary?.details.runoffCandidates ?? [];
  const primaryCandidates = primary?.details.primaryCandidates ?? [];
  const displayCandidates = runoffCandidates.length > 0
    ? runoffCandidates
    : primaryCandidates;
  const hasContent = displayCandidates.length > 0 || !!primary?.details.primaryDate || !!primary?.details.runoffDate;

  const toggle = () => setOpen((v) => !v);

  return (
    <div className={`pv-party-lane pv-party-lane--${partyKey}`}>
      <div
        className={`pv-party-lane-header${hasContent ? " pv-party-lane-header--toggle" : ""}`}
        onClick={hasContent ? toggle : undefined}
        role={hasContent ? "button" : undefined}
        tabIndex={hasContent ? 0 : undefined}
        onKeyDown={hasContent ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } } : undefined}
      >
        <span className={`pv-primary-party pv-primary-party--${partyKey}`}>
          {hasContent && <span className="pv-lane-chevron">{open ? "▾" : "▸"}</span>}
          {PARTY_LABELS[party] ?? party}
        </span>
        <span className="pv-party-nominee">
          {primary?.winner
            ? primary.winner
            : primary?.status && primary.status !== "No Primary" && primary.status !== "Unknown"
              ? primary.status
              : "—"}
        </span>
        {generalOdds != null
          ? <span className="pv-odds-badge">{generalOdds}%</span>
          : <span className="pv-odds-muted">—</span>}
      </div>

      {open && hasContent && (
        <div className="pv-party-lane-body">
          {(primary?.details.runoffDate || primary?.details.primaryDate) && (
            <div className="pv-party-status">
              {primary.details.runoffDate
                ? `Runoff: ${primary.details.runoffDate}`
                : `Primary: ${primary.details.primaryDate}`}
            </div>
          )}
          {displayCandidates.length > 0 && (
            <ul className="pv-candidate-list">
              <li className="pv-candidate-list__header">
                <span>Candidate</span>
                <span>Stage</span>
                <span>P.Odds</span>
              </li>
              {displayCandidates.map((name) => {
                const isNominee = primary?.winner === name;
                const isRunoff = runoffCandidates.includes(name);
                const odds = primary?.kalshiPrimary.oddsMap[name];
                return (
                  <li key={name}>
                    <span>{name}</span>
                    <span>{isNominee ? "Nominee" : isRunoff ? "Runoff" : "Candidate"}</span>
                    <span>
                      {odds != null
                        ? <span className="pv-odds-badge">{odds}%</span>
                        : <span className="pv-odds-muted">—</span>}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
const PARTY_CHIP_CLASSES: Record<string, string> = {
  DEM: "pv-summary-chip--dem",
  REP: "pv-summary-chip--rep",
  NP:  "pv-summary-chip--np",
  IND: "pv-summary-chip--ind",
  LIB: "pv-summary-chip--lib",
  GRE: "pv-summary-chip--grn",
};

function PowerVoteSummaryBanner({ location, partyPrefs }: { location: PowerVoteAllPayload["locations"][number]; partyPrefs: string[] }) {
  const stats = useMemo(() => computeLocationSummary(location), [location]);
  const partyChips = Object.entries(stats.primaryByParty)
    .filter(([party, s]) => partyPrefs.includes(party) && s.total > 0)
    .map(([party, s]) => {
      const parts: string[] = [];
      if (s.competitive > 0) parts.push(`${s.competitive} competitive`);
      if (s.uncontested > 0) parts.push(`${s.uncontested} uncontested`);
      if (s.runoff > 0) parts.push(`${s.runoff} runoff`);
      const detail = parts.length ? ` — ${parts.join(", ")}` : "";
      const label = `${s.total} ${PARTY_LABELS[party] ?? party} ${s.total === 1 ? "Primary" : "Primaries"}${detail}`;
      return (
        <span key={party} className={`pv-summary-chip ${PARTY_CHIP_CLASSES[party] ?? ""}`}>{label}</span>
      );
    });
  return (
    <div className="pv-summary-strip">
      <span className="pv-summary-chip">{stats.generalCount} General</span>
      {stats.tossUpCount > 0 && <span className="pv-summary-chip pv-summary-chip--tossup">{stats.tossUpCount} Toss-up</span>}
      {stats.competitiveCount > 0 && <span className="pv-summary-chip pv-summary-chip--competitive">{stats.competitiveCount} Competitive</span>}
      {stats.leanCount > 0 && <span className="pv-summary-chip">{stats.leanCount} Lean</span>}
      {stats.safeCount > 0 && <span className="pv-summary-chip">{stats.safeCount} Safe</span>}
      {partyChips}
    </div>
  );
}

export function PowerVoteView({
  locations,
  setLocations,
  initialAddress,
  initialZipcode,
}: {
  locations: PowerVoteAllPayload["locations"];
  setLocations: React.Dispatch<React.SetStateAction<PowerVoteAllPayload["locations"]>>;
  initialAddress?: string;
  initialZipcode?: string;
}) {
  const [addressInput, setAddressInput] = useState(initialAddress ?? "");
  const [zipcodeInput, setZipcodeInput] = useState(initialZipcode ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { saveLocation, isSaved } = useSavedLocations();
  const { prefs: partyPrefs, toggle: toggleParty } = usePartyPrefs();
  const autoFetched = useRef(false);

  useEffect(() => {
    if (autoFetched.current) return;
    const address = initialAddress?.trim();
    const zipcode = initialZipcode?.trim();
    if (!address && !zipcode) return;
    autoFetched.current = true;
    setIsLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (address) params.set("address", address);
    else params.set("zipcode", zipcode!);
    fetch(`/api/v1/powervote/all?${params.toString()}`)
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error || "Failed to load PowerVote data.");
        setLocations((prev) => [...prev, ...(data as PowerVoteAllPayload).locations]);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load PowerVote data."))
      .finally(() => setIsLoading(false));
  }, [initialAddress, initialZipcode, setLocations]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!zipcodeInput.trim() && !addressInput.trim()) {
      setError("Provide a zipcode or address.");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (addressInput.trim()) params.set("address", addressInput.trim());
      else params.set("zipcode", zipcodeInput.trim());
      const response = await fetch(`/api/v1/powervote/all?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to load PowerVote data.");
      setLocations((prev) => [...prev, ...(data as PowerVoteAllPayload).locations]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load PowerVote data.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="pv-grid">
      <div className="pv-panel">
        <h2>PowerVote</h2>
        <p className="pv-muted">Enter your address or zip code to see every race on your ballot — House, Senate, Governor, and more — with live market odds and competitiveness signals. Want the big picture? <a href="/map" className="pv-inline-link">Explore all races on the national map.</a></p>
        <form onSubmit={handleSubmit} className="pv-form">
          <p className="pv-muted" style={{ margin: 0, fontSize: "0.875rem" }}>
            Enter a zip code <em>or</em> a full address for higher accuracy.
          </p>
          <label>
            Zip Code
            <input
              type="text"
              value={zipcodeInput}
              onChange={(event) => setZipcodeInput(event.target.value)}
              placeholder="e.g. 90210"
              maxLength={5}
            />
          </label>
          <label>
            <span>Address <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, color: "var(--pv-accent)", fontSize: "0.78rem" }}>— higher accuracy</span></span>
            <AddressAutocomplete
              value={addressInput}
              onChange={setAddressInput}
              onSelect={(address) => {
                setAddressInput(address);
                setZipcodeInput("");
              }}
              placeholder="e.g. 1600 Pennsylvania Ave NW"
            />
          </label>
          <button type="submit" disabled={isLoading || locations.length >= 2}>
            {isLoading
              ? "Loading…"
              : locations.length === 0
                ? "Look Up Elections"
                : locations.length >= 2
                  ? "Max 2 Locations"
                  : "Compare Another Location"}
          </button>
          {locations.length > 0 && (
            <button type="button" onClick={() => { setLocations([]); setError(null); }}>
              Clear All
            </button>
          )}
        </form>
        <PartySelector prefs={partyPrefs} onToggle={toggleParty} />
        {error ? <p className="pv-error">{error}</p> : null}

        {locations.length > 0 ? (
          <div className="pv-detail">
            {(() => {
              const competitiveCounts = locations.map((loc) => {
                const stats = computeLocationSummary(loc);
                return hasCompetitiveRace(stats) ? stats.tossUpCount + stats.competitiveCount + stats.leanCount : 0;
              });
              const maxCompetitive = Math.max(...competitiveCounts);
              const indicatorIndex = maxCompetitive > 0 ? competitiveCounts.indexOf(maxCompetitive) : -1;
              return (
                <div className={locations.length === 2 ? "pv-compare-grid pv-compare-grid--two" : undefined}>
                  {locations.map((location, index) => (
                    <React.Fragment key={`loc:${location.label ?? ""}:${index}`}>
                      {index === 1 && <div className="pv-compare-vs">vs</div>}
                      <PowerVoteAllLocationCard
                        location={location}
                        showPowerVoteIndicator={index === indicatorIndex}
                        onRemove={() => setLocations((prev) => prev.filter((_, i) => i !== index))}
                        onSave={() => {
                          const query = location.label;
                          const queryType = /^\d{5}$/.test(query) ? "zipcode" : "address";
                          saveLocation(location.label, query, queryType);
                        }}
                        saved={isSaved(location.label)}
                        partyPrefs={partyPrefs}
                      />
                    </React.Fragment>
                  ))}
                </div>
              );
            })()}
          </div>
        ) : (
          <div className="pv-empty-state">
            <p className="pv-empty-state__lead">Enter your address above to see every competitive race on your 2026 ballot.</p>
            <ul className="pv-empty-state__list">
              <li>House, Senate, Governor, and more</li>
              <li>Live Kalshi market odds and competitiveness scores</li>
              <li>Primary and general election context</li>
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
