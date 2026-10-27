import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from tests.raw_data import requires_raw_data

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_state_market_index.py"
spec = importlib.util.spec_from_file_location("build_state_market_index", MODULE_PATH)
build_state_market_index = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(build_state_market_index)


class BuildStateMarketIndexTests(unittest.TestCase):
    def test_infer_state_uses_title_ticker_and_series_hints(self):
        self.assertEqual(
            build_state_market_index.infer_state("KXTEST", "KXTEST-01", "Governor race in Arizona"),
            "AZ",
        )
        self.assertEqual(
            build_state_market_index.infer_state("KXTEST", "KXHOUSERACE-WA07-26-R", "Something"),
            "WA",
        )
        self.assertEqual(
            build_state_market_index.infer_state("KXGOVTXNOMD", "RANDOM", "Unknown title"),
            "TX",
        )

    def test_infer_seat_type_handles_core_categories(self):
        self.assertEqual(
            build_state_market_index.infer_seat_type("TX", "KXTXPRIMARY", "KXTXPRIMARY-11D26-ABCD", "Texas primary"),
            "US-REP",
        )
        self.assertEqual(
            build_state_market_index.infer_seat_type("WA", "KXHOUSERACE", "KXHOUSERACE-WA02-26-R", "House winner"),
            "US-REP",
        )
        self.assertEqual(
            build_state_market_index.infer_seat_type("OH", "KXSENATEOH", "KXSENATEOH-26", "Senate winner"),
            "US-SEN",
        )
        self.assertEqual(
            build_state_market_index.infer_seat_type("NC", "KXGOVNC", "KXGOVNC-26", "Governor winner"),
            "Statewide",
        )
        self.assertEqual(
            build_state_market_index.infer_seat_type("VA", "KXVAHOUSE", "KXVAHOUSE-26", "Virginia House of Delegates election"),
            "State-REP",
        )

    def test_election_type_and_seat_id_are_derived_consistently(self):
        self.assertEqual(
            build_state_market_index.infer_election_type("KXTXPRIMARY", "KXTXPRIMARY-11D26-ABCD", "Texas primary"),
            "2026 Primary (D)",
        )
        self.assertEqual(
            build_state_market_index.infer_election_type("KXTEST", "KXTEST-26", "General winner"),
            "2026 General",
        )
        self.assertEqual(
            build_state_market_index.infer_seat_id(
                "WA",
                "KXHOUSERACE",
                "KXHOUSERACE-WA02-26-R",
                "Washington House race",
                "US-REP",
            ),
            "WA-02",
        )
        self.assertEqual(
            build_state_market_index.infer_seat_id(
                "NC",
                "KXGOVNC",
                "KXGOVNC-26",
                "North Carolina governor winner",
                "Statewide",
            ),
            "NC-GOV",
        )
        self.assertEqual(
            build_state_market_index.infer_seat_id(
                "VT",
                "KXHOUSERACE",
                "KXHOUSERACE-VTAL-26-R",
                "Vermont at-large congressional district",
                "US-REP",
            ),
            "VT-AL",
        )


    def test_primary_party_inference_uses_series_and_sources(self):
        self.assertEqual(
            build_state_market_index.infer_election_type(
                "KXGOVMENOMD",
                "KXGOVMENOMD-26",
                "ME Nom",
                {"settlement_sources": []},
            ),
            "2026 Primary (D)",
        )
        self.assertEqual(
            build_state_market_index.infer_election_type(
                "KXGOVCONOMR",
                "KXGOVCONOMR-26",
                "Gov CO Nom R",
                {"settlement_sources": [{"name": "Republican Party"}]},
            ),
            "2026 Primary (R)",
        )

    def test_winner_market_fallback_includes_statewide_election_series(self):
        self.assertTrue(
            build_state_market_index.is_winner_market("IA Nom D", "KXGOVIANOMD", "KXGOVIANOMD-26")
        )
        self.assertTrue(
            build_state_market_index.is_winner_market("AZ Sec State", "KXSECSTATEAZ", "KXSECSTATEAZ-26")
        )


    @requires_raw_data
    def test_repo_snapshot_patterns_drive_state_and_seat_inference(self):
        cases = [
            {
                "series": Path("test_data/kalshi/series/series_KXINPRIMARY_Elections.json"),
                "market": Path("test_data/kalshi/market/market_KXINPRIMARY_KXINPRIMARY-05R26-VSPA.json"),
                "expected": {
                    "state": "IN",
                    "seatType": "US-REP",
                    "seatId": "IN-05",
                    "electionType": "2026 Primary (R)",
                },
            },
            {
                "series": Path("test_data/kalshi/series/series_KXILPRIMARY_Elections.json"),
                "market": Path("test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-05R26-KLAD.json"),
                "expected": {
                    "state": "IL",
                    "seatType": "US-REP",
                    "seatId": "IL-05",
                    "electionType": "2026 Primary (R)",
                },
            },
            {
                "series": Path("test_data/kalshi/series/series_KXAZ01D_Elections.json"),
                "market": Path("test_data/kalshi/market/market_KXAZ01D_KXAZ01D-25-ASHA.json"),
                "expected": {
                    "state": "AZ",
                    "seatType": "US-REP",
                    "seatId": "AZ-01",
                    "electionType": "2025 Primary (D)",
                },
            },
            {
                "series": Path("test_data/kalshi/series/series_KXHI01D_Elections.json"),
                "market": Path("test_data/kalshi/market/market_KXHI01D_KXHI01D-26-ECAS.json"),
                "expected": {
                    "state": "HI",
                    "seatType": "US-REP",
                    "seatId": "HI-01",
                    "electionType": "2026 Primary (D)",
                },
            },
        ]

        for case in cases:
            with self.subTest(search_anchor=case["market"].stem):
                series = json.loads(case["series"].read_text(encoding="utf-8"))
                market_payload = json.loads(case["market"].read_text(encoding="utf-8"))
                series_ticker = str(series["ticker"])
                market_ticker = str(market_payload["ticker"])
                title = build_state_market_index.build_market_context_title(series, market_payload)

                state = build_state_market_index.infer_state(series_ticker, market_ticker, title)
                self.assertEqual(state, case["expected"]["state"])

                seat_type = build_state_market_index.infer_seat_type(state, series_ticker, market_ticker, title)
                self.assertEqual(seat_type, case["expected"]["seatType"])

                seat_id = build_state_market_index.infer_seat_id(
                    state,
                    series_ticker,
                    market_ticker,
                    title,
                    seat_type,
                )
                self.assertEqual(seat_id, case["expected"]["seatId"])

                election_type = build_state_market_index.infer_election_type(
                    series_ticker,
                    market_ticker,
                    title,
                    series,
                )
                self.assertEqual(election_type, case["expected"]["electionType"])

    def test_build_primary_election_context_uses_child_event_ticker_as_canonical_key(self):
        primary = build_state_market_index.build_primary_election_context(
            {
                "ticker": "KXILPRIMARY-02D26-DMIL",
                "event_ticker": "KXILPRIMARY-02D26",
                "title": "Will Donna Miller be the Democratic nominee for IL-02?",
            },
            {
                "ticker": "KXILPRIMARY",
                "title": "Illinois Primary winners",
                "settlement_sources": [{"name": "Democratic Party"}, {"name": "Republican Party"}],
            },
        )
        self.assertIsNotNone(primary)
        assert primary is not None
        self.assertEqual(primary.event_ticker, "KXILPRIMARY-02D26")
        self.assertEqual(primary.parent_series_ticker, "KXILPRIMARY")
        self.assertEqual(primary.seat_id, "IL-02")
        self.assertEqual(primary.party, "D")


    @requires_raw_data
    def test_primary_series_contexts_stay_distinct_across_umbrella_and_direct_series(self):
        cases = [
            {
                'label': 'illinois umbrella series',
                'series_file': Path('test_data/kalshi/series/series_KXILPRIMARY_Elections.json'),
                'market_files': [
                    Path('test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-02D26-SMOO.json'),
                    Path('test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-05R26-KLAD.json'),
                    Path('test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-07D26-KCOL.json'),
                ],
                'expected_event_tickers': {'KXILPRIMARY-02D26', 'KXILPRIMARY-05R26', 'KXILPRIMARY-07D26'},
            },
            {
                'label': 'texas umbrella series',
                'series_file': Path('test_data/kalshi/series/series_KXTXPRIMARY_Elections.json'),
                'market_files': [
                    Path('test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-09R26-CDEL.json'),
                    Path('test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-16R26-MCHA.json'),
                    Path('test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-24D26-KBUR.json'),
                    Path('test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-35D26-MGAL.json'),
                ],
                'expected_event_tickers': {'KXTXPRIMARY-09R26', 'KXTXPRIMARY-16R26', 'KXTXPRIMARY-24D26', 'KXTXPRIMARY-35D26'},
            },
            {
                'label': 'direct district series',
                'series_file': Path('test_data/kalshi/series/series_KXAZ01D_Elections.json'),
                'market_files': [Path('test_data/kalshi/market/market_KXAZ01D_KXAZ01D-25-ASHA.json')],
                'expected_event_tickers': {'KXAZ01D-25'},
            },
        ]

        for case in cases:
            with self.subTest(case=case['label']):
                series = json.loads(case['series_file'].read_text(encoding='utf-8'))
                contexts = []
                for market_file in case['market_files']:
                    market_payload = json.loads(market_file.read_text(encoding='utf-8'))
                    primary = build_state_market_index.build_primary_election_context(market_payload, series)
                    self.assertIsNotNone(primary)
                    contexts.append(primary)

                event_tickers = {context.event_ticker for context in contexts if context is not None}
                normalized_keys = {context.normalized_contest_key for context in contexts if context is not None}
                self.assertEqual(event_tickers, case['expected_event_tickers'])
                self.assertEqual(len(normalized_keys), len(case['expected_event_tickers']))

    @requires_raw_data
    def test_main_groups_repo_snapshot_markets_by_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            market_dir = input_dir / "market"
            series_dir = input_dir / "series"
            output_file = root / "output.json"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            series_files = [
                Path("test_data/kalshi/series/series_KXAZ01D_Elections.json"),
                Path("test_data/kalshi/series/series_KXHI01D_Elections.json"),
                Path("test_data/kalshi/series/series_KXILPRIMARY_Elections.json"),
                Path("test_data/kalshi/series/series_KXINPRIMARY_Elections.json"),
            ]
            market_files = [
                Path("test_data/kalshi/market/market_KXAZ01D_KXAZ01D-25-ASHA.json"),
                Path("test_data/kalshi/market/market_KXHI01D_KXHI01D-26-ECAS.json"),
                Path("test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-05R26-KLAD.json"),
                Path("test_data/kalshi/market/market_KXINPRIMARY_KXINPRIMARY-05R26-VSPA.json"),
            ]

            for source in series_files:
                (series_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            for source in market_files:
                (market_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

            original_input = build_state_market_index.INPUT_DIR
            original_market = build_state_market_index.MARKET_INPUT_DIR
            original_series = build_state_market_index.SERIES_INPUT_DIR
            original_output = build_state_market_index.OUTPUT_FILE
            original_repo = build_state_market_index.REPO_ROOT
            try:
                build_state_market_index.REPO_ROOT = root
                build_state_market_index.INPUT_DIR = input_dir
                build_state_market_index.MARKET_INPUT_DIR = market_dir
                build_state_market_index.SERIES_INPUT_DIR = series_dir
                build_state_market_index.OUTPUT_FILE = output_file

                build_state_market_index.main()
            finally:
                build_state_market_index.REPO_ROOT = original_repo
                build_state_market_index.INPUT_DIR = original_input
                build_state_market_index.MARKET_INPUT_DIR = original_market
                build_state_market_index.SERIES_INPUT_DIR = original_series
                build_state_market_index.OUTPUT_FILE = original_output

            payload = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertIn("AZ", payload["stateMarkets"])
            self.assertIn("IN", payload["stateMarkets"])
            self.assertIn("IL", payload["stateMarkets"])
            self.assertIn("HI", payload["stateMarkets"])

            az_tickers = {market["marketTicker"] for market in payload["stateMarkets"]["AZ"]}
            in_tickers = {market["marketTicker"] for market in payload["stateMarkets"]["IN"]}

            self.assertIn("KXAZ01D-25-ASHA", az_tickers)
            self.assertIn("KXINPRIMARY-05R26-VSPA", in_tickers)
            self.assertFalse(any(ticker.startswith("KXAZ") for ticker in in_tickers))
            self.assertFalse(any(ticker.startswith("KXHI") for ticker in in_tickers))

    def test_entity_name_and_odds_are_derived_from_market_payload(self):
        self.assertEqual(
            build_state_market_index.infer_entity_name(
                {"custom_strike": {"Candidate": "Jane Doe"}, "yes_sub_title": "Fallback Name"},
                "KXTEST-26-JDOE",
            ),
            "Jane Doe",
        )
        self.assertEqual(
            build_state_market_index.parse_odds_percent({"last_price_dollars": "0.4250"}),
            42.5,
        )
        self.assertIsNone(build_state_market_index.parse_odds_percent({"last_price_dollars": ""}))

    def test_winner_market_filtering_rules(self):
        self.assertTrue(build_state_market_index.is_winner_market("Who will win the governor race?"))
        self.assertFalse(build_state_market_index.is_winner_market("Governor margin over 5 percent"))

    def test_main_builds_output_from_snapshot_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            market_dir = input_dir / "market"
            series_dir = input_dir / "series"
            output_file = root / "output.json"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXGOVAZNOMR.json").write_text(
                json.dumps({"ticker": "KXGOVAZNOMR", "title": "Arizona governor winner"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXGOVAZNOMR_KXGOVAZNOMR-26-ABCD.json").write_text(
                json.dumps({
                    "ticker": "KXGOVAZNOMR-26-ABCD",
                    "custom_strike": {"Candidate": "Alice Example"},
                    "last_price_dollars": "0.6100",
                }),
                encoding="utf-8",
            )

            original_input = build_state_market_index.INPUT_DIR
            original_market = build_state_market_index.MARKET_INPUT_DIR
            original_series = build_state_market_index.SERIES_INPUT_DIR
            original_output = build_state_market_index.OUTPUT_FILE
            original_repo = build_state_market_index.REPO_ROOT
            try:
                build_state_market_index.REPO_ROOT = root
                build_state_market_index.INPUT_DIR = input_dir
                build_state_market_index.MARKET_INPUT_DIR = market_dir
                build_state_market_index.SERIES_INPUT_DIR = series_dir
                build_state_market_index.OUTPUT_FILE = output_file

                build_state_market_index.main()
            finally:
                build_state_market_index.REPO_ROOT = original_repo
                build_state_market_index.INPUT_DIR = original_input
                build_state_market_index.MARKET_INPUT_DIR = original_market
                build_state_market_index.SERIES_INPUT_DIR = original_series
                build_state_market_index.OUTPUT_FILE = original_output

            payload = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["scannedFiles"], 1)
            self.assertEqual(payload["includedMarkets"], 1)
            self.assertIn("AZ", payload["stateMarkets"])
            market = payload["stateMarkets"]["AZ"][0]
            self.assertEqual(market["seatType"], "Statewide")
            self.assertEqual(market["seatId"], "AZ-GOV")
            self.assertEqual(market["entityName"], "Alice Example")
            self.assertEqual(market["oddsPercent"], 61.0)


if __name__ == "__main__":
    unittest.main()
