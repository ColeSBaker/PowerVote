import { describe, expect, test } from "vitest";

import { buildDetailEntities } from "@/lib/server/district-detail";

describe("district detail entity model", () => {
  test("general candidate visibility includes general, active runoff, and eliminated primary entrants", () => {
    const entities = buildDetailEntities({
      seatId: "TX-01",
      generalRow: {
        seat: "TX-01",
        district: "1",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Incumbent",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "runoff",
        primary_status_r: "complete",
        nominee_d: "",
        nominee_r: "General Nominee",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-03-03",
        runoff_date: "2026-05-26",
      } as any,
      primaryRows: [] as any,
      runoffRows: [
        {
          party: "D",
          status: "runoff",
          runoff_candidate_1: "Runoff One",
          runoff_candidate_2: "Runoff Two",
          runoff_date: "2026-05-26",
        },
      ] as any,
      candidateRows: [
        { BallotpediaName: "Primary Only", Party: "D", Status: "primary", "Primary ID": "x", RunoffID: "" },
        { BallotpediaName: "General Nominee", Party: "R", Status: "general (nominated)", "Primary ID": "x", RunoffID: "" },
        { BallotpediaName: "Runoff One", Party: "D", Status: "primary", "Primary ID": "x", RunoffID: "runoff-1" },
      ] as any,
      departureRow: null,
    });

    const demLane = entities.generalElection.partyLanes.find((lane) => lane.party === "DEM");
    // Active runoff participants come first, then eliminated primary entrants (sorted last)
    expect(demLane?.visibleCandidates.map((entry) => entry.name)).toEqual(["TBD", "Runoff One", "Runoff Two", "Primary Only"]);
    expect(demLane?.visibleCandidates.find((entry) => entry.name === "TBD")?.odds).toBeNull();
    expect(demLane?.visibleCandidates.find((entry) => entry.name === "Primary Only")?.eliminated).toBe(true);
    expect(demLane?.visibleCandidates.find((entry) => entry.name === "Runoff One")?.eliminated).toBe(false);
    expect(demLane?.primaryCandidates).toEqual([]);
    const repLane = entities.generalElection.partyLanes.find((lane) => lane.party === "REP");
    expect(repLane?.visibleCandidates.map((entry) => entry.name)).toContain("General Nominee");
    expect(repLane?.visibleCandidates.map((entry) => entry.name)).not.toContain("Primary Only");
    expect(repLane?.primaryCandidates).toEqual([]);
  });

  test("general odds map applies candidate odds and falls back to party odds for TBD nominee", () => {
    const entities = buildDetailEntities({
      seatId: "TX-32",
      generalRow: {
        seat: "TX-32",
        district: "32",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Incumbent",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: JSON.stringify({
          "James Talarico": 55,
          "Democratic party": 57,
          "Republican party": 43,
        }),
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "complete",
        primary_status_r: "upcoming",
        nominee_d: "James Talarico",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-03-03",
        runoff_date: "",
      } as any,
      primaryRows: [] as any,
      runoffRows: [] as any,
      candidateRows: [{ BallotpediaName: "James Talarico", Party: "D", Status: "general (nominated)", "Primary ID": "x", RunoffID: "" }] as any,
      departureRow: null,
    });

    const demLane = entities.generalElection.partyLanes.find((lane) => lane.party === "DEM");
    expect(demLane?.visibleCandidates.find((entry) => entry.name === "James Talarico")?.odds).toBe(55);

    const repLane = entities.generalElection.partyLanes.find((lane) => lane.party === "REP");
    expect(repLane?.visibleCandidates.find((entry) => entry.name === "TBD")?.odds).toBe(43);
  });

  test("primary ordering is runoff pair then nominee then odds", () => {
    const entities = buildDetailEntities({
      seatId: "TX-14",
      generalRow: {
        seat: "TX-14",
        district: "14",
        general_status: "contested",
        incumbent_party: "D",
        incumbent_name: "Incumbent",
        incumbent_status: "retiring",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "runoff",
        primary_status_r: "upcoming",
        nominee_d: "Nominee D",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-03-03",
        runoff_date: "2026-05-26",
      } as any,
      primaryRows: [] as any,
      runoffRows: [
        {
          party: "D",
          status: "runoff",
          runoff_candidate_1: "Runoff A",
          runoff_candidate_2: "Runoff B",
          runoff_date: "2026-05-26",
        },
      ] as any,
      candidateRows: [
        { BallotpediaName: "Nominee D", Party: "D", Status: "general (nominated)", "Primary ID": "x", RunoffID: "", KalshiBestPrimaryOdds: "43" },
        { BallotpediaName: "Runoff A", Party: "D", Status: "primary", "Primary ID": "x", RunoffID: "y", KalshiBestPrimaryOdds: "17" },
        { BallotpediaName: "Runoff B", Party: "D", Status: "primary", "Primary ID": "x", RunoffID: "y", KalshiBestPrimaryOdds: "28" },
        { BallotpediaName: "Odds High", Party: "D", Status: "primary", "Primary ID": "x", RunoffID: "", KalshiBestPrimaryOdds: "52" },
        { BallotpediaName: "No Odds", Party: "D", Status: "primary", "Primary ID": "x", RunoffID: "", KalshiBestPrimaryOdds: "" },
      ] as any,
      departureRow: {
        party: "D",
        departure_reason: "retiring",
      } as any,
    });

    const demParty = entities.primaryElection.parties.find((entry) => entry.party === "DEM");
    expect(demParty).toBeDefined();
    expect(demParty?.candidates[0].name).toBe("Runoff A");
    expect(demParty?.candidates[1].name).toBe("Runoff B");
    expect(demParty?.candidates[2].name).toBe("Nominee D");
    expect(demParty?.candidates[3].name).toBe("Odds High");
    expect(demParty?.candidates.find((candidate) => candidate.name === "Odds High")?.eliminated).toBe(true);
  });

  test("primaryCandidates populated when primary ongoing, sorted by odds then alpha, capped at 6", () => {
    const entities = buildDetailEntities({
      seatId: "GA-06",
      generalRow: {
        seat: "GA-06",
        district: "6",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Incumbent",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "upcoming",
        primary_status_r: "upcoming",
        nominee_d: "",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-06-09",
        runoff_date: "",
      } as any,
      primaryRows: [
        {
          seat: "GA-06",
          party: "R",
          primary_id: "GA-06-R",
          status: "upcoming",
          round: "primary",
          primary_date: "2026-06-09",
          runoff_date: "",
          runoff_candidate_1: "",
          runoff_candidate_2: "",
          kalshi_primary_odds_map: JSON.stringify({ "Alpha A": 30, "Charlie C": 10 }),
        },
      ] as any,
      runoffRows: [] as any,
      candidateRows: [
        { BallotpediaName: "Alpha A", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "30" },
        { BallotpediaName: "Bravo B", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "" },
        { BallotpediaName: "Charlie C", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "10" },
        { BallotpediaName: "Delta D", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "" },
        { BallotpediaName: "Echo E", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "50" },
        { BallotpediaName: "Foxtrot F", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "" },
        { BallotpediaName: "Golf G", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "5" },
        { BallotpediaName: "Hotel H", Party: "R", Status: "primary", "Primary ID": "GA-06-R", RunoffID: "", KalshiBestPrimaryOdds: "" },
      ] as any,
      departureRow: null,
    });

    const repLane = entities.generalElection.partyLanes.find((lane) => lane.party === "REP");
    expect(repLane?.primaryOngoing).toBe(true);
    // Odds descending: Echo E (50), Alpha A (30), Charlie C (10), Golf G (5), then alpha: Bravo B, Delta D — cap at 6
    expect(repLane?.primaryCandidates).toEqual(["Echo E", "Alpha A", "Charlie C", "Golf G", "Bravo B", "Delta D"]);
  });

  test("primaryCandidates empty when nominee decided", () => {
    const entities = buildDetailEntities({
      seatId: "GA-07",
      generalRow: {
        seat: "GA-07",
        district: "7",
        general_status: "contested",
        incumbent_party: "D",
        incumbent_name: "Incumbent",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "complete",
        primary_status_r: "upcoming",
        nominee_d: "Winner",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-06-09",
        runoff_date: "",
      } as any,
      primaryRows: [
        { seat: "GA-07", party: "D", primary_id: "GA-07-D", status: "complete", round: "primary", primary_date: "2026-06-09", runoff_date: "", runoff_candidate_1: "", runoff_candidate_2: "", kalshi_primary_odds_map: "{}" },
      ] as any,
      runoffRows: [] as any,
      candidateRows: [
        { BallotpediaName: "Winner", Party: "D", Status: "general (nominated)", "Primary ID": "GA-07-D", RunoffID: "", KalshiBestPrimaryOdds: "80" },
        { BallotpediaName: "Loser", Party: "D", Status: "primary", "Primary ID": "GA-07-D", RunoffID: "", KalshiBestPrimaryOdds: "20" },
      ] as any,
      departureRow: null,
    });

    const demLane = entities.generalElection.partyLanes.find((lane) => lane.party === "DEM");
    expect(demLane?.primaryCandidates).toEqual([]);
  });

  test("primaryCandidates rejects invalid odds values", () => {
    const entities = buildDetailEntities({
      seatId: "GA-08",
      generalRow: {
        seat: "GA-08",
        district: "8",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Incumbent",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "upcoming",
        primary_status_r: "",
        nominee_d: "",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-06-09",
        runoff_date: "",
      } as any,
      primaryRows: [
        { seat: "GA-08", party: "D", primary_id: "GA-08-D", status: "upcoming", round: "primary", primary_date: "2026-06-09", runoff_date: "", runoff_candidate_1: "", runoff_candidate_2: "", kalshi_primary_odds_map: JSON.stringify({ "Valid": 40, "Bad Inf": "Infinity", "Bad NaN": "not-a-number" }) },
      ] as any,
      runoffRows: [] as any,
      candidateRows: [
        { BallotpediaName: "Valid", Party: "D", Status: "primary", "Primary ID": "GA-08-D", RunoffID: "", KalshiBestPrimaryOdds: "40" },
        { BallotpediaName: "Bad Row Odds", Party: "D", Status: "primary", "Primary ID": "GA-08-D", RunoffID: "", KalshiBestPrimaryOdds: "NaN" },
        { BallotpediaName: "No Odds", Party: "D", Status: "primary", "Primary ID": "GA-08-D", RunoffID: "", KalshiBestPrimaryOdds: "" },
      ] as any,
      departureRow: null,
    });

    const demLane = entities.generalElection.partyLanes.find((lane) => lane.party === "DEM");
    // Valid (40) has odds → first; Bad Row Odds and No Odds have null odds → alphabetical
    expect(demLane?.primaryCandidates).toEqual(["Valid", "Bad Row Odds", "No Odds"]);
  });

  const TOP_TWO_CANDIDATE_ROWS = [
    { BallotpediaName: "Alpha A", Party: "DEM", Status: "primary", "Primary ID": "CA-04-ADV", RunoffID: "", KalshiBestPrimaryOdds: "70" },
    { BallotpediaName: "Bravo B", Party: "REP", Status: "primary", "Primary ID": "CA-04-ADV", RunoffID: "", KalshiBestPrimaryOdds: "50" },
    { BallotpediaName: "Charlie C", Party: "DEM", Status: "primary", "Primary ID": "CA-04-ADV", RunoffID: "", KalshiBestPrimaryOdds: "40" },
    { BallotpediaName: "Delta D", Party: "REP", Status: "primary", "Primary ID": "CA-04-ADV", RunoffID: "", KalshiBestPrimaryOdds: "30" },
    { BallotpediaName: "Echo E", Party: "NPA", Status: "primary", "Primary ID": "CA-04-ADV", RunoffID: "", KalshiBestPrimaryOdds: "20" },
  ] as any;

  const TOP_TWO_GENERAL_ROW = {
    seat: "CA-04",
    district: "4",
    general_status: "contested",
    incumbent_party: "D",
    incumbent_name: "Incumbent",
    incumbent_status: "incumbent",
    kalshi_general_odds_map: "{}",
    general_election_race_ratings: "{}",
    dccc_target: "False",
    nrcc_target: "False",
    primary_status_d: "upcoming",
    primary_status_r: "upcoming",
    nominee_d: "",
    nominee_r: "",
    nominee_green: "",
    nominee_libertarian: "",
    primary_date: "2026-06-09",
    runoff_date: "",
  } as any;

  test("top-two primary ongoing: no candidates advancing, none eliminated", () => {
    const entities = buildDetailEntities({
      seatId: "CA-04",
      generalRow: TOP_TWO_GENERAL_ROW,
      primaryRows: [
        { seat: "CA-04", party: "NP", primary_id: "CA-04-ADV", status: "upcoming", round: "primary", primary_date: "2026-06-09", advance_count: 2, kalshi_primary_odds_map: "{}" },
      ] as any,
      runoffRows: [] as any,
      candidateRows: TOP_TWO_CANDIDATE_ROWS,
      departureRow: null,
    });

    const npParty = entities.primaryElection.parties.find((p) => p.party === "NP");
    expect(npParty).toBeDefined();
    // Primary ongoing: zero advancing, zero eliminated
    expect(npParty!.candidates.filter((c) => c.stage === "general")).toHaveLength(0);
    expect(npParty!.candidates.filter((c) => c.stage === "runoff")).toHaveLength(0);
    expect(npParty!.candidates.filter((c) => c.eliminated)).toHaveLength(0);
    expect(npParty!.candidates.every((c) => c.stage === "candidate")).toBe(true);

    // Unified view must match
    const npUnified = entities.unifiedElection?.parties.find((p) => p.party === "NP");
    expect(npUnified).toBeDefined();
    expect(npUnified!.candidates.filter((c) => c.stage === "general")).toHaveLength(0);
    expect(npUnified!.candidates.filter((c) => c.eliminated)).toHaveLength(0);
  });

  test("top-two primary complete: exactly 2 advance, all others eliminated", () => {
    const entities = buildDetailEntities({
      seatId: "CA-04",
      generalRow: TOP_TWO_GENERAL_ROW,
      primaryRows: [
        { seat: "CA-04", party: "NP", primary_id: "CA-04-ADV", status: "complete", round: "primary", primary_date: "2026-06-09", advance_count: 2, kalshi_primary_odds_map: "{}" },
      ] as any,
      runoffRows: [] as any,
      candidateRows: TOP_TWO_CANDIDATE_ROWS,
      departureRow: null,
    });

    const npParty = entities.primaryElection.parties.find((p) => p.party === "NP");
    expect(npParty).toBeDefined();
    const advancing = npParty!.candidates.filter((c) => c.stage === "general");
    const eliminated = npParty!.candidates.filter((c) => c.eliminated);
    // Exactly 2 advance (top-two by odds), all 3 others eliminated
    expect(advancing.map((c) => c.name)).toEqual(["Alpha A", "Bravo B"]);
    expect(advancing.every((c) => !c.eliminated)).toBe(true);
    expect(eliminated).toHaveLength(3);
    expect(eliminated.every((c) => c.stage === "candidate")).toBe(true);
    // No runoff stage ever emitted from an advance primary
    expect(npParty!.candidates.filter((c) => c.stage === "runoff")).toHaveLength(0);

    // Unified view must match
    const npUnified = entities.unifiedElection?.parties.find((p) => p.party === "NP");
    expect(npUnified).toBeDefined();
    expect(npUnified!.candidates.filter((c) => c.stage === "general").map((c) => c.name)).toEqual(["Alpha A", "Bravo B"]);
    expect(npUnified!.candidates.filter((c) => c.eliminated)).toHaveLength(3);
  });

  const TOP_FOUR_CANDIDATE_ROWS = [
    { BallotpediaName: "Tom B",     Party: "REP", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "77" },
    { BallotpediaName: "Bernie W",  Party: "DEM", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "68" },
    { BallotpediaName: "Jonathan K",Party: "REP", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "49" },
    { BallotpediaName: "Dave B",    Party: "DEM", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "41" },
    { BallotpediaName: "Treg T",    Party: "NPA", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "32" },
    { BallotpediaName: "Click B",   Party: "NPA", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "25" },
    { BallotpediaName: "Nancy D",   Party: "DEM", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "19" },
    { BallotpediaName: "Shelley H", Party: "REP", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "14" },
    { BallotpediaName: "Adam C",    Party: "DEM", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "10" },
    { BallotpediaName: "Matt H",    Party: "REP", Status: "primary", "Primary ID": "AK-AL-ADV", RunoffID: "", KalshiBestPrimaryOdds: "7" },
  ] as any;

  const TOP_FOUR_GENERAL_ROW = {
    seat: "AK-AL", district: "AL", general_status: "contested",
    incumbent_party: "D", incumbent_name: "Incumbent", incumbent_status: "incumbent",
    kalshi_general_odds_map: "{}", general_election_race_ratings: "{}",
    dccc_target: "False", nrcc_target: "False",
    primary_status_d: "upcoming", primary_status_r: "upcoming",
    nominee_d: "", nominee_r: "", nominee_green: "", nominee_libertarian: "",
    primary_date: "2026-06-09", runoff_date: "",
  } as any;

  test("top-four primary ongoing: no candidates advancing, none eliminated", () => {
    const entities = buildDetailEntities({
      seatId: "AK-AL",
      generalRow: TOP_FOUR_GENERAL_ROW,
      primaryRows: [
        { seat: "AK-AL", party: "NP", primary_id: "AK-AL-ADV", status: "upcoming", round: "primary", primary_date: "2026-06-09", advance_count: 4, kalshi_primary_odds_map: "{}" },
      ] as any,
      runoffRows: [] as any,
      candidateRows: TOP_FOUR_CANDIDATE_ROWS,
      departureRow: null,
    });

    const npParty = entities.primaryElection.parties.find((p) => p.party === "NP");
    expect(npParty).toBeDefined();
    expect(npParty!.candidates.filter((c) => c.stage === "general")).toHaveLength(0);
    expect(npParty!.candidates.filter((c) => c.eliminated)).toHaveLength(0);
    expect(npParty!.candidates.every((c) => c.stage === "candidate")).toBe(true);

    const npUnified = entities.unifiedElection?.parties.find((p) => p.party === "NP");
    expect(npUnified).toBeDefined();
    expect(npUnified!.candidates.filter((c) => c.stage === "general")).toHaveLength(0);
    expect(npUnified!.candidates.filter((c) => c.eliminated)).toHaveLength(0);
  });

  test("top-four primary complete: exactly 4 advance, all others eliminated", () => {
    const entities = buildDetailEntities({
      seatId: "AK-AL",
      generalRow: TOP_FOUR_GENERAL_ROW,
      primaryRows: [
        { seat: "AK-AL", party: "NP", primary_id: "AK-AL-ADV", status: "complete", round: "primary", primary_date: "2026-06-09", advance_count: 4, kalshi_primary_odds_map: "{}" },
      ] as any,
      runoffRows: [] as any,
      candidateRows: TOP_FOUR_CANDIDATE_ROWS,
      departureRow: null,
    });

    const npParty = entities.primaryElection.parties.find((p) => p.party === "NP");
    expect(npParty).toBeDefined();
    const advancing = npParty!.candidates.filter((c) => c.stage === "general");
    const eliminated = npParty!.candidates.filter((c) => c.eliminated);
    // Exactly 4 advance (top-four by odds), all 6 others eliminated
    expect(advancing).toHaveLength(4);
    expect(advancing.map((c) => c.name)).toEqual(["Tom B", "Bernie W", "Jonathan K", "Dave B"]);
    expect(advancing.every((c) => !c.eliminated)).toBe(true);
    expect(eliminated).toHaveLength(6);
    expect(npParty!.candidates.filter((c) => c.stage === "runoff")).toHaveLength(0);

    const npUnified = entities.unifiedElection?.parties.find((p) => p.party === "NP");
    expect(npUnified).toBeDefined();
    expect(npUnified!.candidates.filter((c) => c.stage === "general")).toHaveLength(4);
    expect(npUnified!.candidates.filter((c) => c.eliminated)).toHaveLength(6);
  });

  test("binary primary: runoff and nominee stages unaffected, zero general", () => {
    const entities = buildDetailEntities({
      seatId: "TX-05",
      generalRow: {
        seat: "TX-05",
        district: "5",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Incumbent",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "runoff",
        primary_status_r: "complete",
        nominee_d: "Nominee D",
        nominee_r: "Nominee R",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-03-03",
        runoff_date: "2026-05-26",
      } as any,
      primaryRows: [
        {
          seat: "TX-05",
          party: "D",
          primary_id: "TX-05-D",
          status: "runoff",
          round: "primary",
          advance_count: 1,
          kalshi_primary_odds_map: "{}",
        },
      ] as any,
      runoffRows: [
        {
          party: "D",
          status: "runoff",
          runoff_candidate_1: "Runoff One",
          runoff_candidate_2: "Runoff Two",
          runoff_date: "2026-05-26",
        },
      ] as any,
      candidateRows: [
        { BallotpediaName: "Nominee D", Party: "D", Status: "general (nominated)", "Primary ID": "TX-05-D", RunoffID: "", KalshiBestPrimaryOdds: "80" },
        { BallotpediaName: "Runoff One", Party: "D", Status: "primary", "Primary ID": "TX-05-D", RunoffID: "r1", KalshiBestPrimaryOdds: "40" },
        { BallotpediaName: "Runoff Two", Party: "D", Status: "primary", "Primary ID": "TX-05-D", RunoffID: "r1", KalshiBestPrimaryOdds: "30" },
        { BallotpediaName: "Also Ran", Party: "D", Status: "primary", "Primary ID": "TX-05-D", RunoffID: "", KalshiBestPrimaryOdds: "10" },
      ] as any,
      departureRow: null,
    });

    const demParty = entities.primaryElection.parties.find((p) => p.party === "DEM");
    expect(demParty).toBeDefined();
    // Binary primary (advance_count=1): runoff pair get "runoff", nominee gets "nominee"
    const runoffStage = demParty!.candidates.filter((c) => c.stage === "runoff");
    const nomineeStage = demParty!.candidates.filter((c) => c.stage === "nominee");
    const generalStage = demParty!.candidates.filter((c) => c.stage === "general");
    expect(runoffStage).toHaveLength(2);
    expect(nomineeStage).toHaveLength(1);
    expect(generalStage).toHaveLength(0);
  });

  test("advanceCount propagated in primaryElection response", () => {
    const entities = buildDetailEntities({
      seatId: "CA-40",
      generalRow: {
        seat: "CA-40",
        district: "40",
        general_status: "contested",
        incumbent_party: "R",
        incumbent_name: "Young Kim",
        incumbent_status: "incumbent",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "upcoming",
        primary_status_r: "upcoming",
        nominee_d: "",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "2026-06-09",
        runoff_date: "",
      } as any,
      primaryRows: [
        {
          seat: "CA-40",
          party: "R",
          primary_id: "CA-40-R-ADV",
          status: "upcoming",
          round: "primary",
          advance_count: 2,
          kalshi_primary_odds_map: "{}",
        },
      ] as any,
      runoffRows: [] as any,
      candidateRows: [] as any,
      departureRow: null,
    });

    expect(entities.primaryElection.advanceCount).toBe(2);
  });

  test("open-seat fallback keeps incumbent name and never returns OPEN sentinel", () => {
    const entities = buildDetailEntities({
      seatId: "CA-11",
      generalRow: {
        seat: "CA-11",
        district: "11",
        general_status: "contested",
        incumbent_party: "",
        incumbent_name: "Nancy Pelosi",
        incumbent_status: "retiring",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "none",
        primary_status_r: "none",
        nominee_d: "",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "",
        runoff_date: "",
      } as any,
      primaryRows: [] as any,
      runoffRows: [] as any,
      candidateRows: [] as any,
      departureRow: null,
    });

    expect(entities.incumbencyAndControl.openSeat).toBe(true);
    expect(entities.incumbencyAndControl.incumbentIndividual).toBe("Nancy Pelosi");
    expect(entities.incumbencyAndControl.departureReason).toBe("unknown");
  });

  test("open-seat fallback uses departure name then unknown incumbent when incumbent_name is missing", () => {
    const withDepartureName = buildDetailEntities({
      seatId: "CA-12",
      generalRow: {
        seat: "CA-12",
        district: "12",
        general_status: "contested",
        incumbent_party: "",
        incumbent_name: "",
        incumbent_status: "retiring",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "none",
        primary_status_r: "none",
        nominee_d: "",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "",
        runoff_date: "",
      } as any,
      primaryRows: [] as any,
      runoffRows: [] as any,
      candidateRows: [] as any,
      departureRow: {
        seat: "CA-12",
        departure_reason: "retiring",
        departure_subreason: "",
        name: "Departed Incumbent",
        party: "D",
      } as any,
    });
    expect(withDepartureName.incumbencyAndControl.incumbentIndividual).toBe("Departed Incumbent");

    const withoutDepartureName = buildDetailEntities({
      seatId: "CA-13",
      generalRow: {
        seat: "CA-13",
        district: "13",
        general_status: "contested",
        incumbent_party: "",
        incumbent_name: "",
        incumbent_status: "retiring",
        kalshi_general_odds_map: "{}",
        general_election_race_ratings: "{}",
        dccc_target: "False",
        nrcc_target: "False",
        primary_status_d: "none",
        primary_status_r: "none",
        nominee_d: "",
        nominee_r: "",
        nominee_green: "",
        nominee_libertarian: "",
        primary_date: "",
        runoff_date: "",
      } as any,
      primaryRows: [] as any,
      runoffRows: [] as any,
      candidateRows: [] as any,
      departureRow: {
        seat: "CA-13",
        departure_reason: "retiring",
        departure_subreason: "",
        name: "",
        party: "D",
      } as any,
    });
    expect(withoutDepartureName.incumbencyAndControl.incumbentIndividual).toBe("Unknown incumbent");
    expect(withoutDepartureName.incumbencyAndControl.incumbentIndividual).not.toBe("OPEN");
  });
});
