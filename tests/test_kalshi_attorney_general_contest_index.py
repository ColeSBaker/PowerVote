from __future__ import annotations

import json
import re
import shutil
import sys
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi.kalshi_attorney_general_mapping import (
    build_kalshi_us_ag_contest_index,
    build_kalshi_us_ag_contest_rows,
)


def _workspace_temp_dir() -> Path:
    root = REPO_ROOT / "tmp_test_runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"kalshi_us_ag_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_market(directory: Path, payload: dict) -> None:
    ticker = payload["ticker"]
    (directory / f"market_{ticker}_{ticker}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Shared fixture payloads
# ---------------------------------------------------------------------------

KXATTYGENAR_R = {
    "ticker": "KXATTYGENAR-26-R",
    "event_ticker": "KXATTYGENAR-26",
    "title": "Will the Republican party win the Attorney General race in Arkansas?",
    "yes_sub_title": "Republican party",
    "subtitle": ":: Current incumbent: Tim Griffin",
    "custom_strike": {"Party": "Republican"},
    "rules_primary": "If a representative of the Republican party is sworn in as the Attorney General of Arkansas for the term beginning in 2027, then the market resolves to Yes.",
    "last_price_dollars": "0.9700",
    "status": "active",
}

KXATTYGENAR_D = {
    "ticker": "KXATTYGENAR-26-D",
    "event_ticker": "KXATTYGENAR-26",
    "title": "Will the Democratic party win the Attorney General race in Arkansas?",
    "yes_sub_title": "Democratic party",
    "subtitle": ":: Current incumbent: Tim Griffin",
    "custom_strike": {"Party": "Democrat"},
    "rules_primary": "If a representative of the Democratic party is sworn in as the Attorney General of Arkansas for the term beginning in 2027, then the market resolves to Yes.",
    "last_price_dollars": "0.0300",
    "status": "active",
}

KXATTYGENFL_R = {
    "ticker": "KXATTYGENFL-26-R",
    "event_ticker": "KXATTYGENFL-26",
    "title": "Will the Republican party win the Attorney General race in Florida?",
    "yes_sub_title": "Republican party",
    "subtitle": ":: Current incumbent: Ashley Moody",
    "custom_strike": {"Party": "Republican"},
    "rules_primary": "If a representative of the Republican party is sworn in as the Attorney General of Florida for the term beginning in 2027, then the market resolves to Yes.",
    "last_price_dollars": "0.8200",
    "status": "active",
}

# A non-AG market that should be excluded
KXGOVAK_CAND = {
    "ticker": "KXGOVAK-26-ACRU",
    "event_ticker": "KXGOVAK-26",
    "title": "Who will win the governorship in Alaska?",
    "yes_sub_title": "Adam Crum",
    "subtitle": ":: Republican",
    "custom_strike": {"Candidate": "Adam Crum"},
    "rules_primary": "If Adam Crum is sworn in as the governor of Alaska...",
    "last_price_dollars": "0.0200",
    "status": "active",
}

# A meta market that should be excluded
KXCLOSESTAG = {
    "ticker": "KXCLOSESTAGSWEEP-26",
    "event_ticker": "KXCLOSESTAGSWEEP-26",
    "title": "Which party will sweep the closest AG races?",
    "yes_sub_title": "Republican",
    "subtitle": "",
    "rules_primary": "...",
    "last_price_dollars": "0.5000",
    "status": "active",
}


class KalshiAGContestIndexUnitTests(unittest.TestCase):
    """Unit tests for Kalshi Attorney General contest row extraction."""

    def test_party_winner_market_type_detected(self):
        """KXATTYGEN party markets are classified as party_winner."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)
        _write_market(market_dir, KXATTYGENAR_D)

        contests, violations, summary = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        self.assertGreater(len(contests), 0)
        for contest in contests:
            self.assertEqual(contest["market_type"], "party_winner")
        shutil.rmtree(tmp, ignore_errors=True)

    def test_state_extraction_from_ticker(self):
        """KXATTYGENAR -> AR, KXATTYGENFL -> FL."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)
        _write_market(market_dir, KXATTYGENFL_R)

        contests, violations, summary = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        states = {c["state"] for c in contests}
        self.assertIn("AR", states)
        self.assertIn("FL", states)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_seat_id_format_is_state_dash_ag(self):
        """Seat IDs should be formatted as {STATE}-AG."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)
        _write_market(market_dir, KXATTYGENFL_R)

        contests, _, _ = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        for contest in contests:
            self.assertRegex(contest["seat_id"], r"^[A-Z]{2}-AG$")
        shutil.rmtree(tmp, ignore_errors=True)

    def test_contest_id_prefix_is_us_ag(self):
        """Contest IDs should start with US-AG:."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)

        contests, _, _ = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        for contest in contests:
            self.assertTrue(contest["contest_id"].startswith("US-AG:"))
        shutil.rmtree(tmp, ignore_errors=True)

    def test_office_field_is_ag(self):
        """All contests should have office='AG'."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)

        contests, _, _ = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        for contest in contests:
            self.assertEqual(contest["office"], "AG")
        shutil.rmtree(tmp, ignore_errors=True)

    def test_cycle_year_extracted(self):
        """Cycle year 2026 should be extracted from -26- in tickers."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)

        contests, _, _ = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        for contest in contests:
            self.assertEqual(contest["cycle_year"], 2026)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_governor_markets_excluded_from_ag_index(self):
        """Governor markets should not appear in AG index."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXGOVAK_CAND)

        contests, violations, summary = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        self.assertEqual(len(contests), 0)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_meta_market_excluded(self):
        """Meta/sweep markets should be excluded."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXCLOSESTAG)

        contests, violations, summary = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        self.assertEqual(len(contests), 0)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_party_extraction_from_ticker_suffix(self):
        """Party -R/-D suffix should be extracted correctly."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)
        _write_market(market_dir, KXATTYGENAR_D)

        contests, _, _ = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        parties = {c["party"] for c in contests}
        self.assertIn("R", parties)
        self.assertIn("D", parties)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_odds_percent_calculated(self):
        """Odds should be last_price_dollars * 100."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        _write_market(market_dir, KXATTYGENAR_R)

        contests, _, _ = build_kalshi_us_ag_contest_rows(
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
        )

        self.assertEqual(len(contests), 1)
        market = contests[0]["markets"][0]
        self.assertAlmostEqual(market["oddsPercent"], 97.0)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_full_artifact_generation(self):
        """Full orchestrator should write all expected output files."""
        tmp = _workspace_temp_dir()
        market_dir = tmp / "markets"
        series_dir = tmp / "series"
        out_dir = tmp / "output"
        market_dir.mkdir(parents=True, exist_ok=True)
        series_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        _write_market(market_dir, KXATTYGENAR_R)
        _write_market(market_dir, KXATTYGENAR_D)
        _write_market(market_dir, KXATTYGENFL_R)

        # Write empty Ballotpedia CSVs for candidate matching
        for name in (
            "ballotpedia-attorney-general-primary-election-rollup.csv",
            "ballotpedia-attorney-general-runoff-election-rollup.csv",
            "ballotpedia-attorney-general-general-election-rollup.csv",
        ):
            (out_dir / name).write_text("", encoding="utf-8")

        output_index_json = out_dir / "kalshi-us-attorney-general-contest-index.json"
        output_index_csv = out_dir / "kalshi-us-attorney-general-contest-index.csv"
        output_violations_csv = out_dir / "kalshi-us-attorney-general-contest-integrity-violations.csv"
        output_violations_json = out_dir / "kalshi-us-attorney-general-contest-integrity-violations.json"
        output_candidate_winner_json = out_dir / "kalshi-attorney-general-candidate-winner.json"
        output_candidate_winner_csv = out_dir / "kalshi-attorney-general-candidate-winner.csv"
        output_party_winner_json = out_dir / "kalshi-attorney-general-party-winner.json"
        output_party_winner_csv = out_dir / "kalshi-attorney-general-party-winner.csv"
        output_candidate_nominee_json = out_dir / "kalshi-attorney-general-candidate-nominee.json"
        output_candidate_nominee_csv = out_dir / "kalshi-attorney-general-candidate-nominee.csv"
        output_excluded_csv = out_dir / "kalshi-attorney-general-excluded-markets.csv"
        output_unmapped_csv = out_dir / "kalshi-attorney-general-unmapped-markets.csv"
        output_ambiguous_csv = out_dir / "kalshi-attorney-general-ambiguous-markets.csv"
        output_coverage_json = out_dir / "kalshi-attorney-general-coverage-summary.json"
        output_match_report_json = out_dir / "kalshi-attorney-general-candidate-match-report.json"
        output_match_report_csv = out_dir / "kalshi-attorney-general-candidate-match-report.csv"

        payload = build_kalshi_us_ag_contest_index(
            output_json=output_index_json,
            output_csv=output_index_csv,
            output_violations_csv=output_violations_csv,
            output_violations_json=output_violations_json,
            output_candidate_winner_json=output_candidate_winner_json,
            output_candidate_winner_csv=output_candidate_winner_csv,
            output_party_winner_json=output_party_winner_json,
            output_party_winner_csv=output_party_winner_csv,
            output_candidate_nominee_json=output_candidate_nominee_json,
            output_candidate_nominee_csv=output_candidate_nominee_csv,
            output_excluded_csv=output_excluded_csv,
            output_unmapped_csv=output_unmapped_csv,
            output_ambiguous_csv=output_ambiguous_csv,
            output_coverage_json=output_coverage_json,
            output_candidate_match_report_json=output_match_report_json,
            output_candidate_match_report_csv=output_match_report_csv,
            ballotpedia_primary_csv=out_dir / "ballotpedia-attorney-general-primary-election-rollup.csv",
            ballotpedia_runoff_csv=out_dir / "ballotpedia-attorney-general-runoff-election-rollup.csv",
            ballotpedia_general_csv=out_dir / "ballotpedia-attorney-general-general-election-rollup.csv",
            market_dirs=(market_dir,),
            series_dirs=(series_dir,),
            strict=False,
        )

        # Verify key outputs exist
        self.assertTrue(output_index_json.exists())
        self.assertTrue(output_index_csv.exists())
        self.assertTrue(output_violations_json.exists())
        self.assertTrue(output_candidate_winner_json.exists())
        self.assertTrue(output_party_winner_json.exists())
        self.assertTrue(output_coverage_json.exists())
        self.assertTrue(output_match_report_json.exists())

        # Verify contest index structure
        index_data = json.loads(output_index_json.read_text(encoding="utf-8"))
        self.assertIn("contests", index_data)
        self.assertIn("summary", index_data)
        self.assertGreater(len(index_data["contests"]), 0)

        # Verify coverage summary
        coverage = json.loads(output_coverage_json.read_text(encoding="utf-8"))
        self.assertIn("counts", coverage)
        self.assertGreater(coverage["counts"]["party_winner_contests"], 0)

        shutil.rmtree(tmp, ignore_errors=True)


class KalshiAGSharedHelpersTests(unittest.TestCase):
    """Tests for kalshi_ag_shared module."""

    def test_extract_state_from_ticker(self):
        from kalshi.kalshi_ag_shared import extract_state_from_ticker

        self.assertEqual(extract_state_from_ticker("KXATTYGENAR-26-R"), "AR")
        self.assertEqual(extract_state_from_ticker("KXATTYGENFL-26-R"), "FL")
        self.assertEqual(extract_state_from_ticker("KXATTYGENAZ-26-D"), "AZ")
        self.assertIsNone(extract_state_from_ticker("KXGOVAK-26"))
        self.assertIsNone(extract_state_from_ticker("RANDOM-TICKER"))

    def test_is_ag_market(self):
        from kalshi.kalshi_ag_shared import is_ag_market

        self.assertTrue(is_ag_market("KXATTYGENAR-26-R", ""))
        self.assertTrue(is_ag_market("RANDOM", "Attorney General race in Florida"))
        self.assertFalse(is_ag_market("KXGOVAK-26", "Governor of Alaska"))
        self.assertFalse(is_ag_market("RANDOM", "Random market title"))

    def test_infer_market_type_party_winner(self):
        from kalshi.kalshi_ag_shared import infer_market_type

        self.assertEqual(
            infer_market_type(
                "KXATTYGENAR-26-R",
                "Will the Republican party win the Attorney General race?",
            ),
            "party_winner",
        )

    def test_infer_round_defaults_to_general(self):
        from kalshi.kalshi_ag_shared import infer_round

        self.assertEqual(infer_round("KXATTYGENAR-26-R"), "general")

    def test_extract_party_suffix(self):
        from kalshi.kalshi_ag_shared import extract_party_suffix

        self.assertEqual(extract_party_suffix("KXATTYGENAR-26-R"), "R")
        self.assertEqual(extract_party_suffix("KXATTYGENAR-26-D"), "D")
        self.assertIsNone(extract_party_suffix("KXATTYGENAR-26"))

    def test_is_non_seat_market(self):
        from kalshi.kalshi_ag_shared import is_non_seat_market

        self.assertTrue(is_non_seat_market("KXCLOSESTAGRACE-26"))
        self.assertFalse(is_non_seat_market("KXATTYGENAR-26-R"))


if __name__ == "__main__":
    unittest.main()
