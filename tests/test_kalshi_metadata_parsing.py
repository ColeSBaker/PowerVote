import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import kalshi_metadata_parsing


class KalshiMetadataParsingTests(unittest.TestCase):
    def test_parses_direct_district_nominee_ticker(self):
        parsed = kalshi_metadata_parsing.parse_kalshi_election_metadata(
            event_ticker='KXAZ01D-25',
            market_ticker='KXAZ01D-25-ASHA',
            title='Will Amish Shah be the Democratic nominee for AZ-01?',
            rules_primary='If Amish Shah wins the nomination for the Democratic Party to contest the 2026 AZ-01 House seat, then the market resolves to Yes.',
        )
        self.assertEqual(parsed.state_code, 'AZ')
        self.assertEqual(parsed.district_code, '01')
        self.assertEqual(parsed.party, 'D')
        self.assertEqual(parsed.cycle_year, 2025)
        self.assertEqual(parsed.seat_id, 'AZ-01')
        self.assertEqual(parsed.office_family, 'US-REP')

    def test_parses_umbrella_primary_tickers(self):
        parsed = kalshi_metadata_parsing.parse_kalshi_election_metadata(
            event_ticker='KXINPRIMARY-05R26',
            market_ticker='KXINPRIMARY-05R26-VSPA',
            title='Will Victoria Spartz be the Republican nominee for IN-05?',
            rules_primary='If Victoria Spartz wins the nomination for the Republican Party to contest the 2026 IN-05 House seat, then the market resolves to Yes.',
        )
        self.assertEqual(parsed.state_code, 'IN')
        self.assertEqual(parsed.district_code, '05')
        self.assertEqual(parsed.party, 'R')
        self.assertEqual(parsed.cycle_year, 2026)
        self.assertEqual(parsed.seat_id, 'IN-05')

    def test_parses_at_large_variants(self):
        parsed = kalshi_metadata_parsing.parse_kalshi_election_metadata(
            event_ticker='KXHOUSERACE-VTAL-26',
            market_ticker='KXHOUSERACE-VTAL-26-R',
            title='Will Republican win the House race for VT-AL?',
            rules_primary='If the House member sworn in for VT-AL for the term beginning in 2027 is a member of the Republican Party, then the market resolves to Yes.',
        )
        self.assertEqual(parsed.state_code, 'VT')
        self.assertTrue(parsed.is_at_large)
        self.assertEqual(parsed.seat_id, 'VT-AL')
        self.assertEqual(parsed.office_family, 'US-REP')

    def test_event_ticker_precedence_beats_series_label_noise(self):
        parsed = kalshi_metadata_parsing.parse_kalshi_election_metadata(
            event_ticker='KXINPRIMARY-05R26',
            market_ticker='KXINPRIMARY-05R26-VSPA',
            series_ticker='KXILPRIMARY',
            series_title='Illinois house primary label noise',
            title='Will Victoria Spartz be the Republican nominee for IN-05?',
            rules_primary='If Victoria Spartz wins the nomination for the Republican Party to contest the 2026 IN-05 House seat, then the market resolves to Yes.',
        )
        self.assertEqual(parsed.seat_id, 'IN-05')
        self.assertEqual(parsed.state_code, 'IN')


    def test_parse_primary_election_event_enriches_child_event_with_parent_series_context(self):
        parsed = kalshi_metadata_parsing.parse_primary_election_event(
            event_ticker='KXILPRIMARY-02D26',
            parent_series_ticker='KXILPRIMARY',
            parent_series_title='Illinois Primary winners',
            settlement_source_names=['Democratic Party', 'Republican Party'],
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.parent_series_ticker, 'KXILPRIMARY')
        self.assertEqual(parsed.event_ticker, 'KXILPRIMARY-02D26')
        self.assertEqual(parsed.state_code, 'IL')
        self.assertEqual(parsed.seat_id, 'IL-02')
        self.assertEqual(parsed.party, 'D')
        self.assertEqual(parsed.election_kind, 'primary')


    def test_table_driven_primary_series_emit_distinct_normalized_contest_keys(self):
        cases = [
            {
                'label': 'illinois umbrella series',
                'parent_series_ticker': 'KXILPRIMARY',
                'parent_series_title': 'Illinois Primary winners',
                'settlement_source_names': ['Democratic Party', 'Republican Party'],
                'event_tickers': [
                    'KXILPRIMARY-02D26',
                    'KXILPRIMARY-05R26',
                    'KXILPRIMARY-07D26',
                ],
                'expected_seat_parties': {('IL-02', 'D'), ('IL-05', 'R'), ('IL-07', 'D')},
            },
            {
                'label': 'texas umbrella series',
                'parent_series_ticker': 'KXTXPRIMARY',
                'parent_series_title': 'Texas Primary winners',
                'settlement_source_names': ['Democratic Party', 'Republican Party'],
                'event_tickers': [
                    'KXTXPRIMARY-09R26',
                    'KXTXPRIMARY-16R26',
                    'KXTXPRIMARY-24D26',
                    'KXTXPRIMARY-35D26',
                ],
                'expected_seat_parties': {('TX-09', 'R'), ('TX-16', 'R'), ('TX-24', 'D'), ('TX-35', 'D')},
            },
            {
                'label': 'direct district series',
                'parent_series_ticker': 'KXAZ01D',
                'parent_series_title': 'Arizona District 1 Democratic nominee',
                'settlement_source_names': ['Democratic Party'],
                'event_tickers': ['KXAZ01D-25'],
                'expected_seat_parties': {('AZ-01', 'D')},
            },
        ]

        for case in cases:
            with self.subTest(case=case['label']):
                parsed_events = [
                    kalshi_metadata_parsing.parse_primary_election_event(
                        event_ticker=event_ticker,
                        parent_series_ticker=case['parent_series_ticker'],
                        parent_series_title=case['parent_series_title'],
                        settlement_source_names=case['settlement_source_names'],
                    )
                    for event_ticker in case['event_tickers']
                ]
                self.assertTrue(all(event is not None for event in parsed_events))
                normalized_keys = {event.normalized_contest_key for event in parsed_events if event is not None}
                self.assertEqual(len(normalized_keys), len(case['expected_seat_parties']))
                seat_parties = {(event.seat_id, event.party) for event in parsed_events if event is not None}
                self.assertEqual(seat_parties, case['expected_seat_parties'])

    def test_only_emits_statewide_without_district_or_office_evidence(self):
        parsed = kalshi_metadata_parsing.parse_kalshi_election_metadata(
            event_ticker='KXTEST-26',
            market_ticker='KXTEST-26-YES',
            title='Will someone win in Arizona?',
        )
        self.assertEqual(parsed.state_code, 'AZ')
        self.assertEqual(parsed.office_family, 'Statewide')
        self.assertIsNone(parsed.seat_id)


if __name__ == '__main__':
    unittest.main()
