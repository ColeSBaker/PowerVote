import importlib.util
import json
import sys
import shutil
import uuid
import unittest
from pathlib import Path
from tests.raw_data import requires_raw_data

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_us_house_market_index.py"
spec = importlib.util.spec_from_file_location("build_us_house_market_index", MODULE_PATH)
build_us_house_market_index = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(build_us_house_market_index)


def _workspace_temp_dir() -> Path:
    root = REPO_ROOT / "tmp_test_runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"build_house_index_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class BuildUsHouseMarketIndexTests(unittest.TestCase):
    def test_infers_primary_election_type_and_cycle_from_primary_ticker(self):
        market_payload = {
            "rules_primary": "If Jane Doe wins the nomination for the Democratic Party to contest the 2026 OH-04 House seat, then the market resolves to Yes.",
        }
        self.assertEqual(
            build_us_house_market_index.infer_cycle_year("KXOHPRIMARY-04D26-JDOE"),
            2026,
        )
        self.assertEqual(
            build_us_house_market_index.infer_election_type(
                market_payload,
                "Will Jane Doe be the Democratic nominee for OH-04?",
                "",
                "Jane Doe",
            ),
            "primary",
        )

    def test_build_market_record_marks_primary_contracts(self):
        seat_lookup = {
            "OH-04": {
                "seatId": "OH-04",
                "stateCode": "OH",
                "districtNumber": 4,
                "districtCode": "4",
            }
        }
        market_payload = {
            "ticker": "KXOHPRIMARY-04D26-JDOE",
            "event_ticker": "KXOHPRIMARY-04D26",
            "title": "Will Jane Doe be the Democratic nominee for OH-04?",
            "yes_sub_title": "Jane Doe",
            "rules_primary": "If Jane Doe wins the nomination for the Democratic Party to contest the 2026 OH-04 House seat, then the market resolves to Yes.",
            "last_price_dollars": "0.6100",
            "status": "active",
        }
        seat_id, record = build_us_house_market_index.build_market_record(market_payload, None, seat_lookup)
        self.assertEqual(seat_id, "OH-04")
        self.assertEqual(record["electionType"], "primary")
        self.assertEqual(record["electionCycle"], 2026)
        self.assertEqual(record["marketType"], "candidate_nominee")
        self.assertEqual(record["eventTicker"], "KXOHPRIMARY-04D26")
        self.assertIn("OH-04", record["electionLabel"])


    @requires_raw_data
    def test_table_driven_primary_series_emit_distinct_house_election_identities(self):
        cases = [
            {
                'label': 'illinois umbrella series',
                'series_file': REPO_ROOT / 'test_data/kalshi/series/series_KXILPRIMARY_Elections.json',
                'market_files': [
                    REPO_ROOT / 'test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-02D26-SMOO.json',
                    REPO_ROOT / 'test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-05R26-KLAD.json',
                    REPO_ROOT / 'test_data/kalshi/market/market_KXILPRIMARY_KXILPRIMARY-07D26-KCOL.json',
                ],
                'expected_seat_ids': {'IL-02', 'IL-05', 'IL-07'},
                'expected_event_tickers': {'KXILPRIMARY-02D26', 'KXILPRIMARY-05R26', 'KXILPRIMARY-07D26'},
            },
            {
                'label': 'texas umbrella series',
                'series_file': REPO_ROOT / 'test_data/kalshi/series/series_KXTXPRIMARY_Elections.json',
                'market_files': [
                    REPO_ROOT / 'test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-09R26-CDEL.json',
                    REPO_ROOT / 'test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-16R26-MCHA.json',
                    REPO_ROOT / 'test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-24D26-KBUR.json',
                    REPO_ROOT / 'test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-35D26-MGAL.json',
                ],
                'expected_seat_ids': {'TX-09', 'TX-16', 'TX-24', 'TX-35'},
                'expected_event_tickers': {'KXTXPRIMARY-09R26', 'KXTXPRIMARY-16R26', 'KXTXPRIMARY-24D26', 'KXTXPRIMARY-35D26'},
            },
            {
                'label': 'direct district series',
                'series_file': REPO_ROOT / 'test_data/kalshi/series/series_KXAZ01D_Elections.json',
                'market_files': [REPO_ROOT / 'test_data/kalshi/market/market_KXAZ01D_KXAZ01D-25-ASHA.json'],
                'expected_seat_ids': {'AZ-01'},
                'expected_event_tickers': {'KXAZ01D-25'},
            },
        ]

        for case in cases:
            with self.subTest(case=case['label']):
                series_payload = json.loads(case['series_file'].read_text(encoding='utf-8'))
                seat_lookup = {
                    seat_id: {
                        'seatId': seat_id,
                        'stateCode': seat_id.split('-')[0],
                        'districtNumber': 0 if seat_id.endswith('AL') else int(seat_id.split('-')[1]),
                        'districtCode': seat_id.split('-')[1],
                    }
                    for seat_id in case['expected_seat_ids']
                }

                built_records = []
                for market_file in case['market_files']:
                    market_payload = json.loads(market_file.read_text(encoding='utf-8'))
                    built = build_us_house_market_index.build_market_record(market_payload, series_payload, seat_lookup)
                    self.assertIsNotNone(built)
                    built_records.append(built)

                seat_ids = {seat_id for seat_id, _ in built_records if seat_id is not None}
                event_tickers = {record['eventTicker'] for _, record in built_records if record.get('eventTicker')}
                normalized_keys = {record['normalizedContestKey'] for _, record in built_records if record.get('normalizedContestKey')}
                self.assertEqual(seat_ids, case['expected_seat_ids'])
                self.assertEqual(event_tickers, case['expected_event_tickers'])
                self.assertEqual(len(normalized_keys), len(case['expected_event_tickers']))

    @requires_raw_data
    def test_build_market_record_emits_distinct_normalized_keys_for_same_series_primary_contests(self):
        series_payload = json.loads(
            (REPO_ROOT / 'test_data/kalshi/series/series_KXTXPRIMARY_Elections.json').read_text(encoding='utf-8')
        )
        seat_lookup = {
            'TX-24': {
                'seatId': 'TX-24',
                'stateCode': 'TX',
                'districtNumber': 24,
                'districtCode': '24',
            },
            'TX-35': {
                'seatId': 'TX-35',
                'stateCode': 'TX',
                'districtNumber': 35,
                'districtCode': '35',
            },
        }

        built_records = []
        for market_file in (
            REPO_ROOT / 'test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-24D26-KBUR.json',
            REPO_ROOT / 'test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-35D26-MGAL.json',
            REPO_ROOT / 'test_data/kalshi/market/market_KXTXPRIMARY_KXTXPRIMARY-35R26-JCOR.json',
        ):
            market_payload = json.loads(market_file.read_text(encoding='utf-8'))
            built = build_us_house_market_index.build_market_record(market_payload, series_payload, seat_lookup)
            self.assertIsNotNone(built)
            built_records.append(built)

        normalized_keys = {record['normalizedContestKey'] for _, record in built_records}
        self.assertEqual(
            normalized_keys,
            {'US-REP:TX-24:2026:D', 'US-REP:TX-35:2026:D', 'US-REP:TX-35:2026:R'},
        )

    @requires_raw_data
    def test_generated_house_market_index_preserves_multiple_primary_contests_per_state_series(self):
        root = _workspace_temp_dir()
        try:
            output_file = root / 'us-house-market-index.json'
            payload = build_us_house_market_index.build_us_house_market_index(output_file=output_file)

            districts = {district['seatId']: district for district in payload['districts']}

            tx_35_primary_keys = {
                market['normalizedContestKey']
                for market in districts['TX-35']['markets']
                if market['electionType'] == 'primary'
            }
            self.assertEqual(tx_35_primary_keys, {'US-REP:TX-35:2026:D', 'US-REP:TX-35:2026:R'})

            tx_33_primary_keys = {
                market['normalizedContestKey']
                for market in districts['TX-33']['markets']
                if market['electionType'] == 'primary'
            }
            self.assertEqual(tx_33_primary_keys, {'US-REP:TX-33:2026:D', 'US-REP:TX-33:2026:R'})

            mi_13_primary_keys = {
                market['normalizedContestKey']
                for market in districts['MI-13']['markets']
                if market['electionType'] == 'primary'
            }
            self.assertEqual(mi_13_primary_keys, {'US-REP:MI-13:2026:D'})
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_build_index_writes_primary_metadata(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            seat_index_file = root / "us-house-seats.json"
            output_file = root / "us-house-market-index.json"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            seat_index_file.write_text(json.dumps({
                "seats": [{
                    "seatId": "OH-04",
                    "stateCode": "OH",
                    "districtNumber": 4,
                    "districtCode": "4",
                    "displayName": "Congressional District 4",
                    "districtLabel": "District 4",
                }]
            }), encoding="utf-8")

            (market_dir / "market_KXOHPRIMARY_KXOHPRIMARY-04D26-JDOE.json").write_text(
                json.dumps({
                    "ticker": "KXOHPRIMARY-04D26-JDOE",
                    "event_ticker": "KXOHPRIMARY-04D26",
                    "title": "Will Jane Doe be the Democratic nominee for OH-04?",
                    "yes_sub_title": "Jane Doe",
                    "rules_primary": "If Jane Doe wins the nomination for the Democratic Party to contest the 2026 OH-04 House seat, then the market resolves to Yes.",
                    "last_price_dollars": "0.6100",
                    "status": "active",
                }),
                encoding="utf-8",
            )

            payload = build_us_house_market_index.build_us_house_market_index(
                market_input_dir=market_dir,
                series_input_dir=series_dir,
                seat_index_file=seat_index_file,
                output_file=output_file,
            )

            self.assertEqual(payload["matchedMarkets"], 1)
            record = payload["districts"][0]["markets"][0]
            self.assertEqual(record["electionType"], "primary")
            self.assertEqual(record["electionCycle"], 2026)
            self.assertEqual(record["eventTicker"], "KXOHPRIMARY-04D26")
            self.assertIsNotNone(record["electionLabel"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    @requires_raw_data
    def test_index_rows_include_explicit_market_role_lane(self):
        root = _workspace_temp_dir()
        try:
            output_file = root / "us-house-market-index.json"
            payload = build_us_house_market_index.build_us_house_market_index(output_file=output_file)
            markets = [m for district in payload.get("districts", []) for m in district.get("markets", [])]
            self.assertGreater(len(markets), 0)
            for market in markets:
                self.assertIn("marketRole", market)
                self.assertIn(market["marketRole"], {"candidate_nominee", "candidate_winner", "party_winner", "candidate_advance"})
                # backwards-compat alias should remain available
                self.assertEqual(market.get("marketType"), market.get("marketRole"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_strict_mode_raises_on_integrity_violations(self):
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            seat_index_file = root / "us-house-seats.json"
            output_file = root / "us-house-market-index.json"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            seat_index_file.write_text(
                json.dumps(
                    {
                        "seats": [
                            {
                                "seatId": "TX-15",
                                "stateCode": "TX",
                                "districtNumber": 15,
                                "districtCode": "15",
                                "displayName": "Texas District 15",
                                "districtLabel": "District 15",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (series_dir / "series_HOUSETX15_Elections.json").write_text(
                json.dumps({"ticker": "HOUSETX15", "title": "Texas District 15 House Race"}),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSETX15_HOUSETX15-26-ALIC.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSETX15-26-ALIC",
                        "event_ticker": "HOUSETX15",
                        "title": "Will Alice Adams win TX-15?",
                        "yes_sub_title": "Alice Adams",
                        "status": "active",
                        "updated_time": "2026-01-01T00:00:00Z",
                        "last_price_dollars": "0.10",
                    }
                ),
                encoding="utf-8",
            )
            (market_dir / "market_HOUSETX15_HOUSETX15-26-BOBB.json").write_text(
                json.dumps(
                    {
                        "ticker": "HOUSETX15-26-BOBB",
                        "event_ticker": "HOUSETX15",
                        "title": "Will Bob Baker win TX-15?",
                        "yes_sub_title": "Bob Baker",
                        "status": "active",
                        "updated_time": "2026-01-01T00:00:00Z",
                        "last_price_dollars": "0.10",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(build_us_house_market_index.HouseMarketIndexError):
                build_us_house_market_index.build_us_house_market_index(
                    market_input_dir=market_dir,
                    series_input_dir=series_dir,
                    seat_index_file=seat_index_file,
                    output_file=output_file,
                    strict=True,
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
