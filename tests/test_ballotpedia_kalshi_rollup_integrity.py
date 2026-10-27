import sys
import unittest
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.kalshi import build_kalshi_contest_indexes, load_kalshi_us_rep_contests
from ballotpedia_rollup.kalshi_integrity import evaluate_kalshi_row_integrity
from ballotpedia_rollup.parser import parse_all
from tests.raw_data import requires_raw_data


def _numeric_map_sum(odds_map: dict) -> tuple[int, float]:
    numeric = []
    for value in (odds_map or {}).values():
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            continue
    return len(numeric), sum(numeric)


@requires_raw_data
class BallotpediaKalshiRollupIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        cls.general_rows, cls.primary_rows, cls.runoff_rows, _ = parse_all(fixture_dir)
        cls.contests = load_kalshi_us_rep_contests()
        cls.indexes = build_kalshi_contest_indexes(cls.contests)
        cls.valid_tickers = set(cls.indexes["by_ticker"].keys())

    @staticmethod
    def _entity_names_for_market_tickers(indexes: dict, market_tickers: list[str]) -> set[str]:
        entity_names: set[str] = set()
        for ticker in market_tickers:
            contest = indexes["by_ticker"].get(ticker) or {}
            for market in contest.get("markets") or []:
                if str(market.get("marketTicker") or "").strip() != str(ticker).strip():
                    continue
                entity = str(market.get("entityName") or "").strip()
                if entity:
                    entity_names.add(entity)
        return entity_names

    def test_rollup_linked_tickers_exist_in_kalshi_index(self):
        def assert_tickers_exist(tickers, context):
            for ticker in tickers:
                self.assertIn(ticker, self.valid_tickers, msg=f"{context}: missing Kalshi ticker {ticker}")

        for row in self.primary_rows + self.runoff_rows:
            contest = row.get("kalshi_contest") or {}
            assert_tickers_exist(contest.get("marketTickers") or [], f"primary/runoff row {row.get('primary_id')}")
            for tickers in (row.get("kalshi_candidate_market_map") or {}).values():
                assert_tickers_exist(tickers or [], f"candidate map {row.get('primary_id')}")

        for row in self.general_rows:
            for payload in (row.get("kalshi_general") or {}).get("contests") or []:
                assert_tickers_exist(payload.get("marketTickers") or [], f"general row {row.get('seat')}")
            assert_tickers_exist((row.get("kalshi_primary_d") or {}).get("marketTickers") or [], f"general row {row.get('seat')} D")
            assert_tickers_exist((row.get("kalshi_primary_r") or {}).get("marketTickers") or [], f"general row {row.get('seat')} R")

    def test_primary_and_runoff_round_alignment(self):
        for row in self.primary_rows + self.runoff_rows:
            contest = row.get("kalshi_contest") or {}
            expected_round = "runoff" if str(row.get("round") or "").lower() == "runoff" else "primary"
            if contest:
                self.assertEqual(contest.get("round"), expected_round, msg=f"Round mismatch: {row.get('primary_id')}")

    def test_kalshi_payload_shapes_are_structured(self):
        for row in self.primary_rows + self.runoff_rows:
            self.assertIsInstance(row.get("kalshi_contest"), dict)
            self.assertIsInstance(row.get("kalshi_candidate_market_map"), dict)
            self.assertIsInstance(row.get("kalshi_series_tickers"), list)
            self.assertIsInstance(row.get("kalshi_market_count"), int)
            self.assertIsInstance(row.get("kalshi_primary_odds_map"), dict)
            self.assertIsInstance(row.get("kalshi_runoff_odds_map"), dict)

        for row in self.general_rows:
            self.assertIsInstance(row.get("kalshi_general"), dict)
            self.assertIsInstance(row.get("kalshi_primary_d"), dict)
            self.assertIsInstance(row.get("kalshi_primary_r"), dict)
            self.assertIsInstance(row.get("kalshi_series_tickers"), list)
            self.assertIsInstance(row.get("kalshi_market_count"), int)
            self.assertIsInstance(row.get("kalshi_general_odds_map"), dict)

    def test_coverage_non_zero(self):
        primary_with_markets = sum(1 for row in self.primary_rows if int(row.get("kalshi_market_count") or 0) > 0)
        general_with_markets = sum(1 for row in self.general_rows if int(row.get("kalshi_market_count") or 0) > 0)
        self.assertGreater(primary_with_markets, 0)
        self.assertGreater(general_with_markets, 0)

    def test_general_odds_map_entities_and_sum_range(self):
        checked = 0
        for row in self.general_rows:
            odds_map = row.get("kalshi_general_odds_map") or {}
            if not odds_map:
                continue
            entity_names = self._entity_names_for_market_tickers(
                self.indexes,
                [
                    str(ticker).strip()
                    for contest_summary in (row.get("kalshi_general") or {}).get("contests") or []
                    for ticker in (contest_summary.get("marketTickers") or [])
                    if str(ticker).strip()
                ],
            )
            if not entity_names:
                self.fail(f"{row.get('seat')} has kalshi_general_odds_map but no resolvable general contest entities")
            for key in odds_map.keys():
                self.assertIn(key, entity_names, msg=f"{row.get('seat')} general odds key not in contest entities: {key}")
            count, total = _numeric_map_sum(odds_map)
            if count >= 2:
                checked += 1
                self.assertTrue(90.0 <= total <= 110.0, msg=f"{row.get('seat')} general odds sum={total}")
        self.assertGreater(checked, 0)

    def test_primary_odds_map_entities_and_sum_range(self):
        checked = 0
        for row in self.primary_rows:
            odds_map = row.get("kalshi_primary_odds_map") or {}
            contest = row.get("kalshi_contest") or {}
            if not odds_map or not contest:
                continue
            entity_names = self._entity_names_for_market_tickers(
                self.indexes,
                [
                    str(ticker).strip()
                    for ticker in (contest.get("marketTickers") or [])
                    if str(ticker).strip()
                ],
            )
            self.assertGreater(len(entity_names), 0, msg=f"{row.get('primary_id')} missing contest entities for odds-map check")
            for key in odds_map.keys():
                self.assertNotIn(key.upper(), {"D", "R"}, msg=f"{row.get('primary_id')} primary odds contains party key: {key}")
                self.assertIn(key, entity_names, msg=f"{row.get('primary_id')} primary odds key not in contest entities: {key}")
            count, total = _numeric_map_sum(odds_map)
            sum_status = str((row.get("kalshi_join_audit") or {}).get("sum_status") or "")
            if count >= 2 and sum_status == "ok":
                checked += 1
                self.assertTrue(90.0 <= total <= 110.0, msg=f"{row.get('primary_id')} primary odds sum={total}")
        self.assertGreater(checked, 0)

    def test_join_audit_contains_odds_sum_diagnostics(self):
        rows = self.general_rows + self.primary_rows + self.runoff_rows
        self.assertGreater(len(rows), 0)
        for row in rows:
            audit = row.get("kalshi_join_audit") or {}
            self.assertIn("odds_map_sum", audit)
            self.assertIn("sum_status", audit)
            self.assertIn(str(audit.get("sum_status") or ""), {"ok", "out_of_band", "insufficient_entries"})

    def test_general_join_audit_sum_status_matches_general_aggregate_status(self):
        checked = 0
        for row in self.general_rows:
            summaries = (row.get("kalshi_general") or {}).get("contests") or []
            statuses = set()
            for summary in summaries:
                tickers = [str(ticker).strip() for ticker in (summary.get("marketTickers") or []) if str(ticker).strip()]
                if not tickers:
                    continue
                contest = self.indexes["by_ticker"].get(tickers[0]) or {}
                status = str(contest.get("general_election_odds_sum_status") or "").strip()
                if status:
                    statuses.add(status)
            if not statuses:
                continue
            checked += 1
            self.assertEqual(len(statuses), 1, msg=f"{row.get('seat')} inconsistent aggregate statuses: {sorted(statuses)}")
            self.assertEqual(str((row.get("kalshi_join_audit") or {}).get("sum_status") or ""), next(iter(statuses)))
        self.assertGreater(checked, 0)

    def test_regression_az_general_rows_use_normalized_seat_lookup(self):
        targets = {"AZ-1", "AZ-2", "AZ-01", "AZ-02"}
        matched = 0
        for row in self.general_rows:
            seat = str(row.get("seat") or "")
            if seat not in targets:
                continue
            matched += 1
            strategy = str(row.get("kalshi_join_strategy") or "")
            self.assertNotIn("general=0", strategy, msg=f"{seat} general lookup should not miss")
            self.assertNotEqual(
                str((row.get("kalshi_join_audit") or {}).get("sum_status") or ""),
                "insufficient_entries",
                msg=f"{seat} should not be insufficient when D/R general party markets exist",
            )
            odds_map = row.get("kalshi_general_odds_map") or {}
            keys = {str(key).lower() for key in odds_map.keys()}
            self.assertIn("democratic party", keys)
            self.assertIn("republican party", keys)
        self.assertGreater(matched, 0)

    def test_primary_market_tickers_are_unique_across_primary_rows(self):
        ticker_to_rows: dict[str, list[str]] = defaultdict(list)
        for row in self.primary_rows:
            contest = row.get("kalshi_contest") or {}
            primary_id = str(row.get("primary_id") or "")
            for ticker in contest.get("marketTickers") or []:
                ticker_text = str(ticker).strip()
                if not ticker_text:
                    continue
                ticker_to_rows[ticker_text].append(primary_id)

        duplicates = {
            ticker: row_ids
            for ticker, row_ids in ticker_to_rows.items()
            if len(row_ids) > 1
        }
        self.assertEqual(
            {},
            duplicates,
            msg=f"Primary market ticker attached to multiple primary rows: {list(duplicates.items())[:20]}",
        )

    def test_primary_contest_party_lane_matches_row_party(self):
        failures = []
        for row in self.primary_rows:
            contest = row.get("kalshi_contest") or {}
            contest_party = str(contest.get("partyLane") or "").strip().upper()
            row_party = str(row.get("party") or "").strip().upper()
            if contest_party and row_party and contest_party != row_party:
                failures.append(
                    {
                        "primary_id": row.get("primary_id"),
                        "seat": row.get("seat"),
                        "row_party": row_party,
                        "contest_party": contest_party,
                        "strategy": row.get("kalshi_join_strategy"),
                    }
                )
        self.assertEqual([], failures, msg=f"Primary party-lane mismatch rows: {failures[:20]}")


    def test_shared_integrity_evaluator_matches_row_audit_status(self):
        checked = 0
        for row_type, rows in (("general", self.general_rows), ("primary", self.primary_rows), ("runoff", self.runoff_rows)):
            for row in rows:
                result = evaluate_kalshi_row_integrity(row, row_type=row_type)
                self.assertEqual(row.get("kalshi_integrity_passed"), result.passed)
                self.assertEqual(row.get("kalshi_integrity_status"), result.status)
                self.assertEqual(row.get("kalshi_integrity_issue_count"), len(result.issues))
                checked += 1
        self.assertGreater(checked, 0)

    def test_primary_rows_do_not_use_seat_round_fallback_strategy(self):
        # seat_round (no party specificity) is now legitimate for candidate_advance and
        # primary_party_combo contests — these are non-partisan by design and have no
        # party lane to match against.  Only flag partisan primary rows using the fallback.
        failures = []
        for row in self.primary_rows:
            if str(row.get("kalshi_join_strategy") or "").strip() == "seat_round":
                contest = row.get("kalshi_contest") or {}
                market_role = str(contest.get("marketRole") or "").lower()
                if market_role in {"candidate_advance", "primary_party_combo"}:
                    continue  # non-partisan advance contest — seat_round is correct
                failures.append(
                    {
                        "primary_id": row.get("primary_id"),
                        "seat": row.get("seat"),
                        "party": row.get("party"),
                    }
                )
        self.assertEqual([], failures, msg=f"Primary seat_round fallback rows: {failures[:20]}")


if __name__ == "__main__":
    unittest.main()
