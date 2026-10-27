import sys
import json
import shutil
import uuid
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.kalshi import (
    build_kalshi_us_rep_contest_index,
    build_kalshi_us_rep_contest_rows,
    validate_kalshi_us_rep_contests,
)
from tests.raw_data import requires_raw_data


def _workspace_temp_dir() -> Path:
    root = REPO_ROOT / "tmp_test_runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"kalshi_us_rep_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class KalshiUsRepContestIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contests, cls.violations, cls.summary = build_kalshi_us_rep_contest_rows()
        cls.market_to_contest = {}
        for contest in cls.contests:
            for ticker in contest.get("market_tickers") or []:
                cls.market_to_contest[ticker] = contest

    @requires_raw_data
    def test_contest_rows_have_unique_market_tickers(self):
        self.assertGreater(len(self.contests), 0)
        seen = set()
        for contest in self.contests:
            for ticker in contest.get("market_tickers") or []:
                self.assertNotIn(ticker, seen, msg=f"Duplicate market ticker in canonical index: {ticker}")
                seen.add(ticker)

    def test_primary_contests_do_not_have_party_key_mismatch(self):
        for contest in self.contests:
            if str(contest.get("round") or "").lower() != "primary":
                continue
            party_lane = str(contest.get("party_lane") or "").upper()
            key = str(contest.get("normalized_contest_key") or "").upper()
            if party_lane in {"D", "R"}:
                self.assertTrue(
                    key.endswith(f":{party_lane}"),
                    msg=f"Primary contest key mismatch: seat={contest.get('seat')} key={key} party={party_lane}",
                )

    def test_contest_rows_have_valid_house_shape(self):
        valid_rounds = {"primary", "runoff", "general"}
        valid_roles = {"candidate_nominee", "candidate_winner", "party_winner", "candidate_advance"}
        for contest in self.contests:
            seat = str(contest.get("seat") or "")
            self.assertRegex(seat, r"^[A-Z]{2}-(AL|\d{2})$")
            self.assertIn(contest.get("round"), valid_rounds)
            self.assertIn(contest.get("market_role"), valid_roles)
            self.assertGreaterEqual(int(contest.get("market_count") or 0), 1)

    def test_series_metadata_present(self):
        for contest in self.contests:
            series_tickers = contest.get("series_tickers") or []
            self.assertGreater(len(series_tickers), 0, msg=f"Missing series_tickers on {contest.get('contest_id')}")
            for market in contest.get("markets") or []:
                self.assertTrue(str(market.get("seriesTicker") or "").strip())

    @requires_raw_data
    def test_regression_primary_party_anchors(self):
        anchors = {
            "KXAZ01R-26-TGRA": "R",
            "KXAZ5R-26-TGRA": "R",
            "KXCO03R-26-JHUR": "R",
        }
        for ticker, expected_party in anchors.items():
            contest = self.market_to_contest.get(ticker)
            self.assertIsNotNone(contest, msg=f"Missing anchor ticker in contest index: {ticker}")
            if contest is None:
                continue
            self.assertEqual(contest.get("party_lane"), expected_party)
            self.assertEqual(str(contest.get("round") or "").lower(), "primary")

    def test_uuid_custom_strike_does_not_become_entity_name(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_HOUSETX15_Elections.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSETX15",
                        "title": "Texas District 15 House Race",
                        "last_updated_ts": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSETX15_HOUSETX15-D-26.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSETX15-D-26",
                        "event_ticker": "HOUSETX15",
                        "title": "Which party will win TX-15?",
                        "yes_sub_title": "Democratic",
                        "status": "active",
                        "updated_time": "2026-01-01T00:00:00Z",
                        "last_price_dollars": "0.51",
                        "custom_strike": {
                            "political_party": "9244c562-e545-4f6e-b106-867d2ec95f47",
                        },
                    }
                ),
                encoding="utf-8",
            )

            contests, violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            self.assertEqual(len(violations), 0)
            self.assertEqual(len(contests), 1)
            market = contests[0]["markets"][0]
            self.assertEqual(market["entityName"], "Democratic")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_primary_ticker_r_26_and_d_26_infer_correct_party_lane(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXAZ01R_Elections.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAZ01R",
                        "title": "Arizona District 1 Republican nominee",
                    }
                ),
                encoding="utf-8",
            )
            (series_dir / "series_KXAZ01D_Elections.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAZ01D",
                        "title": "Arizona District 1 Democratic nominee",
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_KXAZ01R_KXAZ01R-26-TGRA.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAZ01R-26-TGRA",
                        "event_ticker": "KXAZ01R-26",
                        "title": "Will Tom Graham win the AZ-01 Republican primary?",
                        "yes_sub_title": "Tom Graham",
                        "status": "active",
                        "updated_time": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_KXAZ01D_KXAZ01D-26-JDOE.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAZ01D-26-JDOE",
                        "event_ticker": "KXAZ01D-26",
                        "title": "Will Jane Doe win the AZ-01 Democratic primary?",
                        "yes_sub_title": "Jane Doe",
                        "status": "active",
                        "updated_time": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            contests, _violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            by_ticker = {
                market["marketTicker"]: contest
                for contest in contests
                for market in contest.get("markets") or []
            }
            self.assertEqual(by_ticker["KXAZ01R-26-TGRA"]["party_lane"], "R")
            self.assertEqual(by_ticker["KXAZ01D-26-JDOE"]["party_lane"], "D")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_merged_sources_select_freshest_market_by_updated_time(self):
        root = _workspace_temp_dir()
        try:
            legacy_market = root / "legacy_market"
            new_market = root / "new_market"
            series_dir = root / "series"
            legacy_market.mkdir(parents=True)
            new_market.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXOH04_Elections.json").write_text(
                json.dumps({"ticker": "KXOH04", "title": "Ohio District 4 House Race"}),
                encoding="utf-8",
            )
            stale = {
                "ticker": "KXOH04-26-JDOE",
                "event_ticker": "KXOH04-26",
                "title": "Will Jane Doe win OH-04?",
                "yes_sub_title": "Jane Doe",
                "status": "closed",
                "updated_time": "2026-01-01T00:00:00Z",
                "last_price_dollars": "0.11",
            }
            fresh = dict(stale)
            fresh.update(
                {
                    "status": "active",
                    "updated_time": "2026-02-01T00:00:00Z",
                    "last_price_dollars": "0.77",
                }
            )
            (legacy_market / "market_KXOH04_KXOH04-26-JDOE.json").write_text(json.dumps(stale), encoding="utf-8")
            (new_market / "market_KXOH04_KXOH04-26-JDOE.json").write_text(json.dumps(fresh), encoding="utf-8")

            contests, _violations, summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(legacy_market, new_market),
                series_dirs=(series_dir,),
            )
            self.assertEqual(summary.get("selected_markets"), 1)
            self.assertEqual(len(contests), 1)
            only_market = contests[0]["markets"][0]
            self.assertEqual(only_market["status"], "active")
            self.assertEqual(only_market["oddsPercent"], 77.0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_strict_validator_flags_uuid_entity_rows(self):
        contests = [
            {
                "seat": "TX-15",
                "round": "general",
                "market_role": "party_winner",
                "market_tickers": ["HOUSETX15-D-26"],
                "markets": [
                    {
                        "marketTicker": "HOUSETX15-D-26",
                        "entityName": "9244c562-e545-4f6e-b106-867d2ec95f47",
                    }
                ],
                "odds_map_sum_status": "ok",
            }
        ]
        violations = validate_kalshi_us_rep_contests(contests, [])
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["type"], "uuid_entity_name")

    def test_general_party_markets_share_election_aggregate_odds_status(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_HOUSETX15_Elections.json").write_text(
                json.dumps({"ticker": "HOUSETX15", "title": "Texas District 15 House Race"}),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSETX15_HOUSETX15-D-26.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSETX15-D-26",
                        "event_ticker": "HOUSETX15",
                        "title": "Which party will win TX-15?",
                        "yes_sub_title": "Democratic",
                        "status": "active",
                        "updated_time": "2026-01-01T00:00:00Z",
                        "last_price_dollars": "0.51",
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSETX15_HOUSETX15-R-26.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSETX15-R-26",
                        "event_ticker": "HOUSETX15",
                        "title": "Which party will win TX-15?",
                        "yes_sub_title": "Republican",
                        "status": "active",
                        "updated_time": "2026-01-01T00:00:00Z",
                        "last_price_dollars": "0.49",
                    }
                ),
                encoding="utf-8",
            )

            contests, _violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            general_rows = [row for row in contests if str(row.get("round") or "").lower() == "general"]
            self.assertEqual(len(general_rows), 2)
            for row in general_rows:
                self.assertEqual(row.get("general_election_market_count"), 2)
                self.assertEqual(str(row.get("odds_map_sum_status") or ""), "ok")
                self.assertEqual(str(row.get("general_election_odds_sum_status") or ""), "ok")
                self.assertEqual(sorted(row.get("general_election_market_tickers") or []), ["HOUSETX15-D-26", "HOUSETX15-R-26"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_general_aggregate_includes_mixed_party_and_candidate_winner_lanes(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_HOUSETX28_Elections.json").write_text(
                json.dumps({"ticker": "HOUSETX28", "title": "Texas District 28 House Race"}),
                encoding="utf-8",
            )
            fixtures = [
                ("HOUSETX28-D-26", "Democratic", "0.44"),
                ("HOUSETX28-R-26", "Republican", "0.40"),
                ("HOUSETX28-26-ALIC", "Alice Adams", "0.16"),
            ]
            for ticker, entity, price in fixtures:
                (market_dir / f"market_HOUSETX28_{ticker}.json").write_text(
                    json.dumps(
                        {
                            "ticker": ticker,
                            "event_ticker": "HOUSETX28",
                            "title": "Who will win TX-28?",
                            "yes_sub_title": entity,
                            "status": "active",
                            "updated_time": "2026-01-01T00:00:00Z",
                            "last_price_dollars": price,
                        }
                    ),
                    encoding="utf-8",
                )

            contests, _violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            general_rows = [row for row in contests if str(row.get("round") or "").lower() == "general"]
            self.assertGreaterEqual(len(general_rows), 2)
            expected_tickers = sorted([item[0] for item in fixtures])
            for row in general_rows:
                self.assertEqual(sorted(row.get("general_election_market_tickers") or []), expected_tickers)
                self.assertEqual(int(row.get("general_election_market_count") or 0), 3)
                self.assertIn("Democratic", row.get("general_election_odds_map") or {})
                self.assertIn("Republican", row.get("general_election_odds_map") or {})
                self.assertIn("Alice Adams", row.get("general_election_odds_map") or {})
                self.assertEqual(str(row.get("odds_map_sum_status") or ""), "ok")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_emits_candidate_name_mapping_rollups_and_report(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_HOUSEAKAL_Elections.json").write_text(
                json.dumps({"ticker": "HOUSEAKAL", "title": "Alaska At-large House race"}),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSEAKAL_HOUSEAKAL-26-MEXA.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSEAKAL-26-MEXA",
                        "event_ticker": "HOUSEAKAL-26",
                        "title": "Will Mary Example win Alaska At-large House race?",
                        "yes_sub_title": "Mary Example",
                        "status": "active",
                        "updated_time": "2026-02-01T00:00:00Z",
                        "last_price_dollars": "0.61",
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSEAKAL_HOUSEAKAL-NOMD-26-MEXA.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSEAKAL-NOMD-26-MEXA",
                        "event_ticker": "HOUSEAKAL-NOMD-26",
                        "title": "Will Mary Example be the Democratic nominee in Alaska At-large?",
                        "yes_sub_title": "Mary Example",
                        "status": "active",
                        "updated_time": "2026-02-01T00:00:00Z",
                        "last_price_dollars": "0.61",
                    }
                ),
                encoding="utf-8",
            )

            primary_csv = root / "primary.csv"
            runoff_csv = root / "runoff.csv"
            general_csv = root / "general.csv"
            primary_csv.write_text(
                "\n".join(
                    [
                        "seat,party,candidates",
                        'AK-AL,D,"[""Mary Example""]"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            runoff_csv.write_text("seat,party,candidates\n", encoding="utf-8")
            general_csv.write_text(
                "\n".join(
                    [
                        "seat,nominee_d,nominee_r,nominee_green,nominee_libertarian,other_general_candidates",
                        'AK-AL,Mary Example,,,,[]',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = build_kalshi_us_rep_contest_index(
                output_json=root / "index.json",
                output_csv=root / "index.csv",
                output_violations_csv=root / "violations.csv",
                output_violations_json=root / "violations.json",
                output_candidate_winner_json=root / "winner.json",
                output_candidate_winner_csv=root / "winner.csv",
                output_candidate_nominee_json=root / "nominee.json",
                output_candidate_nominee_csv=root / "nominee.csv",
                output_candidate_match_report_json=root / "report.json",
                output_candidate_match_report_csv=root / "report.csv",
                ballotpedia_primary_csv=primary_csv,
                ballotpedia_runoff_csv=runoff_csv,
                ballotpedia_general_csv=general_csv,
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                strict=True,
            )
            artifacts = payload.get("artifacts") or {}
            self.assertTrue(Path(str(artifacts.get("candidate_winner_csv") or "")).exists())
            self.assertTrue(Path(str(artifacts.get("candidate_nominee_csv") or "")).exists())
            self.assertTrue(Path(str(artifacts.get("candidate_match_report_json") or "")).exists())

            with (root / "winner.csv").open("r", encoding="utf-8") as handle:
                header = handle.readline().strip().split(",")
            for field in (
                "kalshi_candidate_name",
                "ballotpedia_candidate_name",
                "ballotpedia_match_status",
                "ballotpedia_match_strategy",
                "ballotpedia_match_score",
                "ballotpedia_match_source",
                "ballotpedia_candidate_pool_key",
            ):
                self.assertIn(field, header)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_strict_mode_blocks_high_impact_candidate_matching_unresolved(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_HOUSEAKAL_Elections.json").write_text(
                json.dumps({"ticker": "HOUSEAKAL", "title": "Alaska At-large House race"}),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSEAKAL_HOUSEAKAL-26-UNKN.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSEAKAL-26-UNKN",
                        "event_ticker": "HOUSEAKAL-26",
                        "title": "Will Unknown Person win Alaska At-large House race?",
                        "yes_sub_title": "Unknown Person",
                        "status": "active",
                        "updated_time": "2026-02-01T00:00:00Z",
                        "last_price_dollars": "0.03",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                build_kalshi_us_rep_contest_index(
                    output_json=root / "index.json",
                    output_csv=root / "index.csv",
                    output_violations_csv=root / "violations.csv",
                    output_violations_json=root / "violations.json",
                    output_candidate_winner_json=root / "winner.json",
                    output_candidate_winner_csv=root / "winner.csv",
                    output_candidate_nominee_json=root / "nominee.json",
                    output_candidate_nominee_csv=root / "nominee.csv",
                    output_candidate_match_report_json=root / "report.json",
                    output_candidate_match_report_csv=root / "report.csv",
                    market_dirs=(market_dir,),
                    series_dirs=(series_dir,),
                    strict=True,
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_strict_mode_allows_low_impact_unresolved_candidate_matching(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_HOUSEAKAL_Elections.json").write_text(
                json.dumps({"ticker": "HOUSEAKAL", "title": "Alaska At-large House race"}),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSEAKAL_HOUSEAKAL-26-UNKN.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSEAKAL-26-UNKN",
                        "event_ticker": "HOUSEAKAL-26",
                        "title": "Will Unknown Person win Alaska At-large House race?",
                        "yes_sub_title": "Unknown Person",
                        "status": "active",
                        "updated_time": "2026-02-01T00:00:00Z",
                        "last_price_dollars": "0.02",
                    }
                ),
                encoding="utf-8",
            )
            payload = build_kalshi_us_rep_contest_index(
                output_json=root / "index.json",
                output_csv=root / "index.csv",
                output_violations_csv=root / "violations.csv",
                output_violations_json=root / "violations.json",
                output_candidate_winner_json=root / "winner.json",
                output_candidate_winner_csv=root / "winner.csv",
                output_candidate_nominee_json=root / "nominee.json",
                output_candidate_nominee_csv=root / "nominee.csv",
                output_candidate_match_report_json=root / "report.json",
                output_candidate_match_report_csv=root / "report.csv",
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                strict=True,
            )
            self.assertTrue(Path(str(payload.get("artifacts", {}).get("candidate_match_report_json") or "")).exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)


    def test_ca04_primary_advance_market_is_candidate_advance(self):
        """KXCA04PRIMARY markets are candidate_advance with advance_count=2, no violations."""
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXCA04PRIMARY_Elections.json").write_text(
                json.dumps({"ticker": "KXCA04PRIMARY", "title": "CA-04 2026 primary advance"}),
                encoding="utf-8",
            )
            for ticker_suffix, entity in [("EJON", "Eric Jones"), ("JDOE", "Jane Doe"), ("BSMI", "Bob Smith")]:
                (market_dir / f"market_KXCA04PRIMARY_KXCA04PRIMARY-26-{ticker_suffix}.json").write_text(
                    json.dumps(
                        {
                            "ticker": f"KXCA04PRIMARY-26-{ticker_suffix}",
                            "event_ticker": "KXCA04PRIMARY-26",
                            "title": "Who will advance from the 2026 CA-04 primary?",
                            "yes_sub_title": entity,
                            "rules_primary": f"If {entity} advances in the 2026 CA-04 primary, then the market resolves to Yes.",
                            "status": "active",
                            "updated_time": "2026-01-01T00:00:00Z",
                            "last_price_dollars": "0.35",
                        }
                    ),
                    encoding="utf-8",
                )

            contests, violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            ca04_contests = [c for c in contests if c.get("seat") == "CA-04"]
            self.assertGreater(len(ca04_contests), 0, "CA-04 contest should be indexed")
            for c in ca04_contests:
                self.assertEqual(c.get("market_role"), "candidate_advance",
                                 f"Expected candidate_advance but got {c.get('market_role')}")
                self.assertEqual(c.get("advance_count"), 2)
                self.assertEqual(str(c.get("round") or "").lower(), "primary")
            # No primary_party_key_mismatch violations — advance markets have no party lane
            party_mismatch = [v for v in violations if v.get("type") == "primary_party_key_mismatch"]
            self.assertEqual(len(party_mismatch), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_ca40_primary_advance_with_party_subtitle(self):
        """KXCA40PRIMARYADVANCE with :: Republican subtitle is candidate_advance, advance_count=2."""
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXCA40PRIMARYADVANCE_Elections.json").write_text(
                json.dumps({"ticker": "KXCA40PRIMARYADVANCE", "title": "CA-40 2026 primary advance"}),
                encoding="utf-8",
            )
            for ticker_suffix, entity, price in [("YKIM", "Young Kim", "0.62"), ("JDOE", "Jane Doe", "0.55")]:
                (market_dir / f"market_KXCA40PRIMARYADVANCE_KXCA40PRIMARYADVANCE-26-{ticker_suffix}.json").write_text(
                    json.dumps(
                        {
                            "ticker": f"KXCA40PRIMARYADVANCE-26-{ticker_suffix}",
                            "event_ticker": "KXCA40PRIMARYADVANCE-26",
                            "title": "Who will advance in the CA-40 top 2 primary election?",
                            "yes_sub_title": entity,
                            "subtitle": ":: Republican",
                            "rules_primary": f"If {entity} advances in the CA-40 top 2 primary election in 2026, then the market resolves to Yes.",
                            "status": "active",
                            "updated_time": "2026-01-01T00:00:00Z",
                            "last_price_dollars": price,
                        }
                    ),
                    encoding="utf-8",
                )

            contests, violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            ca40_contests = [c for c in contests if c.get("seat") == "CA-40"]
            self.assertGreater(len(ca40_contests), 0, "CA-40 contest should be indexed")
            for c in ca40_contests:
                self.assertEqual(c.get("market_role"), "candidate_advance")
                self.assertEqual(c.get("advance_count"), 2)
                self.assertEqual(str(c.get("round") or "").lower(), "primary")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_wa07_primary_advance_generic_state_detection(self):
        """KXWA07PRIMARY is detected generically — WA seats work the same as CA."""
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXWA07PRIMARY_Elections.json").write_text(
                json.dumps({"ticker": "KXWA07PRIMARY", "title": "WA-07 2026 primary advance"}),
                encoding="utf-8",
            )
            for ticker_suffix, entity in [("PELL", "Pramila Jayapal"), ("CHAL", "Challenger Smith")]:
                (market_dir / f"market_KXWA07PRIMARY_KXWA07PRIMARY-26-{ticker_suffix}.json").write_text(
                    json.dumps(
                        {
                            "ticker": f"KXWA07PRIMARY-26-{ticker_suffix}",
                            "event_ticker": "KXWA07PRIMARY-26",
                            "title": "Who will advance from the 2026 WA-07 primary?",
                            "yes_sub_title": entity,
                            "rules_primary": f"If {entity} advances in the 2026 WA-07 primary, then the market resolves to Yes.",
                            "status": "active",
                            "updated_time": "2026-01-01T00:00:00Z",
                            "last_price_dollars": "0.50",
                        }
                    ),
                    encoding="utf-8",
                )

            contests, violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            wa07_contests = [c for c in contests if c.get("seat") == "WA-07"]
            self.assertGreater(len(wa07_contests), 0, "WA-07 contest should be indexed")
            for c in wa07_contests:
                self.assertEqual(c.get("market_role"), "candidate_advance")
                self.assertEqual(c.get("advance_count"), 2)
                self.assertEqual(str(c.get("round") or "").lower(), "primary")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_advance_sum_out_of_band_emits_violation(self):
        """Markets whose yes_price sum is outside [160, 240] emit advance_sum_out_of_band."""
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXCA04PRIMARY_Elections.json").write_text(
                json.dumps({"ticker": "KXCA04PRIMARY", "title": "CA-04 2026 primary advance"}),
                encoding="utf-8",
            )
            # Three candidates each at 90% → sum = 270% > 240% upper bound for top-two
            for ticker_suffix, entity in [("AAAA", "Alice A"), ("BBBB", "Bob B"), ("CCCC", "Carol C")]:
                (market_dir / f"market_KXCA04PRIMARY_KXCA04PRIMARY-26-{ticker_suffix}.json").write_text(
                    json.dumps(
                        {
                            "ticker": f"KXCA04PRIMARY-26-{ticker_suffix}",
                            "event_ticker": "KXCA04PRIMARY-26",
                            "title": "Who will advance from the 2026 CA-04 primary?",
                            "yes_sub_title": entity,
                            "rules_primary": f"If {entity} advances in the 2026 CA-04 primary, then the market resolves to Yes.",
                            "status": "active",
                            "updated_time": "2026-01-01T00:00:00Z",
                            "last_price_dollars": "0.90",
                        }
                    ),
                    encoding="utf-8",
                )

            _contests, violations, _summary = build_kalshi_us_rep_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
            )
            advance_violations = [v for v in violations if v.get("type") == "advance_sum_out_of_band"]
            self.assertEqual(len(advance_violations), 1, f"Expected 1 advance_sum_out_of_band violation, got: {violations}")
            v = advance_violations[0]
            self.assertEqual(v.get("advance_count"), 2)
            self.assertAlmostEqual(float(v.get("observed_sum") or 0), 270.0, places=0)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
