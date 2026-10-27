import json
import re
import sys
import unicodedata
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.kalshi import build_kalshi_contest_indexes, load_kalshi_us_rep_contests
import build_candidate_rollup
from tests.raw_data import requires_raw_data

SEATS_JSON = REPO_ROOT / "apps" / "web" / "data" / "us-house-seats.json"
PRIMARY_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.csv"
RUNOFF_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-runoff-election-rollup.csv"
GENERAL_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-general-election-rollup.csv"
FINANCE_CSV = REPO_ROOT / "test_data" / "candidates" / "candidate_summary_2026.csv"


def _normalize_name(value: str | None) -> str:
    text = str(value or "").strip()
    # Decompose accented characters (é → e + combining accent) then drop non-ASCII,
    # so "Sánchez" and "Sanchez" both normalize to "SANCHEZ".
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_json_array(raw: str | None):
    if isinstance(raw, list):
        return raw
    text = str(raw or "").strip()
    if not text:
        return []
    return json.loads(text)


def _parse_json_object(raw: str | None):
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _numeric_map_sum(odds_map: dict) -> tuple[int, float]:
    numeric = []
    for value in (odds_map or {}).values():
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            continue
    return len(numeric), sum(numeric)


def _loose_name_match(left: str, right: str) -> bool:
    left_tokens = [token for token in left.split() if token]
    right_tokens = [token for token in right.split() if token]
    if not left_tokens or not right_tokens:
        return False
    if left == right:
        return True
    if left_tokens[-1] != right_tokens[-1]:
        return False
    if left_tokens[0][:1] == right_tokens[0][:1]:
        return True
    overlap = len(set(left_tokens) & set(right_tokens))
    union = len(set(left_tokens) | set(right_tokens))
    score = overlap / union if union else 0.0
    return score >= 0.6


class CandidateRollupKalshiIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidates = build_candidate_rollup.load_seat_candidates(SEATS_JSON)
        primary_rows = build_candidate_rollup.load_csv(PRIMARY_CSV)
        runoff_rows = build_candidate_rollup.load_csv(RUNOFF_CSV)
        general_rows = build_candidate_rollup.load_csv(GENERAL_CSV)
        finance_rows = build_candidate_rollup.load_csv(FINANCE_CSV)
        augmented = build_candidate_rollup.augment_candidates_with_ballotpedia_sources(
            candidates=candidates,
            primary_rows=primary_rows,
            runoff_rows=runoff_rows,
            general_rows=general_rows,
        )
        reconciled = build_candidate_rollup.reconcile_candidates(augmented, finance_rows)
        cls.rows = build_candidate_rollup.build_rollup(
            candidates=reconciled,
            primary_rows=primary_rows,
            runoff_rows=runoff_rows,
            general_rows=general_rows,
            finance_rows=finance_rows,
        )
        cls.contests = load_kalshi_us_rep_contests()
        cls.indexes = build_kalshi_contest_indexes(cls.contests)
        cls.primary_odds_map_by_id = {
            str(row.get("primary_id") or "").strip(): _parse_json_object(row.get("kalshi_primary_odds_map"))
            for row in primary_rows
            if str(row.get("primary_id") or "").strip()
        }
        cls.general_odds_map_by_seat = {
            str(row.get("seat") or "").strip(): _parse_json_object(row.get("kalshi_general_odds_map"))
            for row in general_rows
            if str(row.get("seat") or "").strip()
        }

    def test_contract_columns_exist(self):
        self.assertGreater(len(self.rows), 0)
        expected = {
            "KalshiSeries",
            "KalshiMarkets",
            "KalshiPrimaryMarkets",
            "KalshiRunoffMarkets",
            "KalshiGeneralMarkets",
            "KalshiBestPrimaryOdds",
            "KalshiBestRunoffOdds",
            "KalshiBestGeneralOdds",
            "KalshiPrimaryOddsMap",
            "KalshiGeneralOddsMap",
            "KalshiLinkStrategy",
            "KalshiLinkScore",
        }
        self.assertTrue(expected.issubset(set(self.rows[0].keys())))

    def test_candidate_market_tickers_are_unique_and_exist(self):
        for row in self.rows:
            markets = _parse_json_array(row.get("KalshiMarkets"))
            tickers = [str(item.get("marketTicker") or "") for item in markets if isinstance(item, dict)]
            deduped = [ticker for ticker in tickers if ticker]
            self.assertEqual(len(deduped), len(set(deduped)), msg=f"Duplicate Kalshi ticker in row {row.get('BallotpediaName')}")
            for ticker in deduped:
                self.assertIn(ticker, self.indexes["by_ticker"], msg=f"Unknown Kalshi ticker {ticker}")

    def test_round_alignment_for_split_market_arrays(self):
        round_map = {
            "KalshiPrimaryMarkets": "primary",
            "KalshiRunoffMarkets": "runoff",
            "KalshiGeneralMarkets": "general",
        }
        for row in self.rows:
            for field, expected_round in round_map.items():
                markets = _parse_json_array(row.get(field))
                for market in markets:
                    ticker = str(market.get("marketTicker") or "")
                    if not ticker:
                        continue
                    contest = self.indexes["by_ticker"].get(ticker)
                    self.assertIsNotNone(contest, msg=f"{field} contains unknown ticker {ticker}")
                    if contest is None:
                        continue
                    self.assertEqual(
                        str(contest.get("round") or "").lower(),
                        expected_round,
                        msg=f"{field} round mismatch on {row.get('BallotpediaName')} ticker={ticker}",
                    )

    def test_combined_market_array_matches_union_of_split_arrays(self):
        for row in self.rows:
            combined = {
                str(item.get("marketTicker") or "")
                for item in _parse_json_array(row.get("KalshiMarkets"))
                if isinstance(item, dict) and str(item.get("marketTicker") or "")
            }
            split = set()
            for field in ("KalshiPrimaryMarkets", "KalshiRunoffMarkets", "KalshiGeneralMarkets"):
                split.update(
                    str(item.get("marketTicker") or "")
                    for item in _parse_json_array(row.get(field))
                    if isinstance(item, dict) and str(item.get("marketTicker") or "")
                )
            self.assertEqual(combined, split, msg=f"Split/combined mismatch for {row.get('BallotpediaName')}")

    @requires_raw_data
    def test_candidate_named_markets_align_to_candidate_identity(self):
        rows_with_markets = 0
        for row in self.rows:
            all_names = {
                _normalize_name(row.get("BallotpediaName")),
                *[_normalize_name(name) for name in _parse_json_array(row.get("FilingName"))],
                *[_normalize_name(name) for name in _parse_json_array(row.get("KalshiName"))],
            }
            all_names = {name for name in all_names if name}
            markets = _parse_json_array(row.get("KalshiMarkets"))
            if markets:
                rows_with_markets += 1
            for market in markets:
                ticker = str(market.get("marketTicker") or "")
                contest = self.indexes["by_ticker"].get(ticker)
                if contest is None:
                    continue
                entity = _normalize_name(market.get("entityName"))
                if not entity:
                    continue
                overlap = any(_loose_name_match(entity, name) for name in all_names)
                self.assertTrue(
                    overlap,
                    msg=f"Candidate/entity mismatch row={row.get('BallotpediaName')} ticker={ticker} entity={entity}",
                )
        self.assertGreater(rows_with_markets, 0)

    def test_general_candidate_markets_exclude_party_winner(self):
        for row in self.rows:
            for market in _parse_json_array(row.get("KalshiGeneralMarkets")):
                ticker = str(market.get("marketTicker") or "")
                contest = self.indexes["by_ticker"].get(ticker)
                if contest is None:
                    continue
                self.assertEqual(str(contest.get("market_role") or "").lower(), "candidate_winner")

    def test_best_general_odds_requires_candidate_market_match(self):
        for row in self.rows:
            general_markets = _parse_json_array(row.get("KalshiGeneralMarkets"))
            best_general_odds = row.get("KalshiBestGeneralOdds")
            if not general_markets:
                self.assertIn(best_general_odds, (None, ""))

    def test_odds_maps_match_source_rollups(self):
        for row in self.rows:
            seat = str(row.get("2026 Seat") or "").strip()
            primary_id = str(row.get("Primary ID") or "").strip()
            self.assertEqual(
                row.get("KalshiGeneralOddsMap") or {},
                self.general_odds_map_by_seat.get(seat, {}),
                msg=f"General odds map mismatch for seat {seat}",
            )
            if primary_id:
                self.assertEqual(
                    row.get("KalshiPrimaryOddsMap") or {},
                    self.primary_odds_map_by_id.get(primary_id, {}),
                    msg=f"Primary odds map mismatch for primary {primary_id}",
                )

    def test_candidate_odds_maps_sum_range(self):
        flag_by_field = {
            "KalshiPrimaryOddsMap": "KalshiPrimaryOddsMapOutOfBand",
            "KalshiGeneralOddsMap": "KalshiGeneralOddsMapOutOfBand",
        }
        for row in self.rows:
            for field in ("KalshiGeneralOddsMap", "KalshiPrimaryOddsMap"):
                if row.get(flag_by_field[field]):
                    continue
                count, total = _numeric_map_sum(row.get(field) or {})
                if count >= 2:
                    self.assertTrue(
                        90.0 <= total <= 110.0,
                        msg=f"{row.get('2026 Seat')} {row.get('BallotpediaName')} {field} sum={total}",
                    )


if __name__ == "__main__":
    unittest.main()
