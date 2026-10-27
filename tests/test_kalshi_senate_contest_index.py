from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kalshi.kalshi_senate_mapping import build_kalshi_us_senate_contest_index, build_kalshi_us_senate_contest_rows


def _workspace_temp_dir() -> Path:
    root = REPO_ROOT / "tmp_test_runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"kalshi_us_sen_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class KalshiUsSenateContestIndexTests(unittest.TestCase):
    def test_maps_regular_2026_primary_to_class_2(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXSENATEALD_Politics.json").write_text(
                json.dumps({"ticker": "KXSENATEALD", "title": "Alabama Democratic Senate nominee"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXSENATEALD_KXSENATEALD-26-DLAR.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXSENATEALD-26-DLAR",
                        "event_ticker": "KXSENATEALD-26",
                        "title": "Will Dakarai Larriett be the Democratic nominee for the Senate in Alabama?",
                        "rules_primary": "If Dakarai Larriett wins the nomination for the Democratic Party to contest the 2026 Senate Alabama Senate seat, then the market resolves to Yes.",
                        "status": "active",
                        "last_price_dollars": "0.28",
                    }
                ),
                encoding="utf-8",
            )

            contests, violations, _summary = build_kalshi_us_senate_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(violations, [])
            self.assertEqual(len(contests), 1)
            contest = contests[0]
            self.assertEqual(contest["seat_id"], "AL-SEN-C2")
            self.assertEqual(contest["round"], "primary")
            self.assertEqual(contest["party"], "D")
            self.assertEqual(contest["market_type"], "candidate_nominee")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prefix_override_maps_special_ohio_primary(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXSENATEOHSR_Politics.json").write_text(
                json.dumps({"ticker": "KXSENATEOHSR", "title": "Ohio Republican Senate nominee"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXSENATEOHSR_KXSENATEOHSR-26-VR.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXSENATEOHSR-26-VR",
                        "event_ticker": "KXSENATEOHSR-26",
                        "title": "Will Vivek Ramaswamy be the Republican nominee for the Senate in Ohio?",
                        "rules_primary": "If Vivek Ramaswamy wins the nomination for the Republican Party to contest the 2026 Class III (special election) Ohio Senate seat, then the market resolves to Yes.",
                        "status": "active",
                        "last_price_dollars": "0.02",
                    }
                ),
                encoding="utf-8",
            )

            contests, violations, _summary = build_kalshi_us_senate_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={
                    "ticker_overrides": {},
                    "ticker_prefix_overrides": {
                        "KXSENATEOHSR-26-": {
                            "seat_id": "OH-SEN-C3-SPL",
                            "round": "primary",
                            "party": "R",
                            "market_type": "candidate_nominee",
                        }
                    },
                },
            )
            self.assertEqual(violations, [])
            self.assertEqual(len(contests), 1)
            self.assertEqual(contests[0]["seat_id"], "OH-SEN-C3-SPL")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_non_outcome_senate_market_is_excluded(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXTXSENATEDEMTURNOUT_Politics.json").write_text(
                json.dumps({"ticker": "KXTXSENATEDEMTURNOUT", "title": "Texas Senate Democratic turnout"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXTXSENATEDEMTURNOUT_KXTXSENATEDEMTURNOUT-26.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXTXSENATEDEMTURNOUT-26-23",
                        "event_ticker": "KXTXSENATEDEMTURNOUT-26",
                        "title": "Will turnout be above threshold in Texas Senate Democratic primary?",
                        "rules_primary": "If turnout exceeds threshold then resolves Yes.",
                        "status": "active",
                        "last_price_dollars": "0.10",
                    }
                ),
                encoding="utf-8",
            )

            contests, violations, _summary = build_kalshi_us_senate_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(contests, [])
            self.assertEqual(violations, [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_general_candidate_winner_market_is_classified(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXAKSENATE_Elections.json").write_text(
                json.dumps({"ticker": "KXAKSENATE", "title": "Alaska Senate race winner"}),
                encoding="utf-8",
            )
            ticker = "KXAKSENATE-26NOV03-DSUL"
            (market_dir / f"market_KXAKSENATE_{ticker}.json").write_text(
                json.dumps(
                    {
                        "ticker": ticker,
                        "event_ticker": "KXAKSENATE-26NOV03",
                        "title": "Will Dan Sullivan win the 2026 Alaska Senate race?",
                        "subtitle": ":: Current incumbent, Republican",
                        "rules_primary": "If Dan Sullivan wins the 2026 Alaska Senate election, then the market resolves to Yes.",
                        "yes_sub_title": "Dan Sullivan",
                        "status": "active",
                        "last_price_dollars": "0.44",
                    }
                ),
                encoding="utf-8",
            )

            contests, violations, _summary = build_kalshi_us_senate_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(violations, [])
            self.assertEqual(len(contests), 1)
            contest = contests[0]
            self.assertEqual(contest["seat_id"], "AK-SEN-C2")
            self.assertEqual(contest["round"], "general")
            self.assertEqual(contest["market_type"], "candidate_winner")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_general_party_winner_market_is_classified(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_SENATEAK_Elections.json").write_text(
                json.dumps({"ticker": "SENATEAK", "title": "Alaska Senate party winner"}),
                encoding="utf-8",
            )
            ticker = "SENATEAK-26-R"
            (market_dir / f"market_SENATEAK_{ticker}.json").write_text(
                json.dumps(
                    {
                        "ticker": ticker,
                        "event_ticker": "SENATEAK-26",
                        "title": "Will Republicans win the Senate race in Alaska?",
                        "rules_primary": "If a representative of the Republican party is sworn in as a Senator of Alaska for the term beginning in 2027, then the market resolves to Yes.",
                        "yes_sub_title": "Republican party",
                        "status": "active",
                        "last_price_dollars": "0.44",
                    }
                ),
                encoding="utf-8",
            )

            contests, violations, _summary = build_kalshi_us_senate_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(violations, [])
            self.assertEqual(len(contests), 1)
            contest = contests[0]
            self.assertEqual(contest["seat_id"], "AK-SEN-C2")
            self.assertEqual(contest["round"], "general")
            self.assertEqual(contest["market_type"], "party_winner")
            self.assertEqual(contest["party"], "R")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_non_seat_general_market_is_excluded_with_reason(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXDSENATESEATS_Elections.json").write_text(
                json.dumps({"ticker": "KXDSENATESEATS", "title": "How many Senate seats Democrats win"}),
                encoding="utf-8",
            )
            ticker = "KXDSENATESEATS-27-50"
            (market_dir / f"market_KXDSENATESEATS_{ticker}.json").write_text(
                json.dumps(
                    {
                        "ticker": ticker,
                        "event_ticker": "KXDSENATESEATS-27",
                        "title": "Will Democrats win 50 or more Senate seats in 2026?",
                        "rules_primary": "If Democrats win 50 or more Senate seats then resolves to Yes.",
                        "yes_sub_title": "50+ seats",
                        "status": "active",
                        "last_price_dollars": "0.35",
                    }
                ),
                encoding="utf-8",
            )

            contests, violations, summary = build_kalshi_us_senate_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(contests, [])
            self.assertEqual(violations, [])
            excluded = summary.get("excluded_markets") or []
            self.assertEqual(len(excluded), 1)
            self.assertEqual(excluded[0].get("market_ticker"), ticker)
            self.assertEqual(excluded[0].get("exclusion_reason"), "non_seat_market")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_writes_market_type_rollup_artifacts(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXAKSENATE_Elections.json").write_text(
                json.dumps({"ticker": "KXAKSENATE", "title": "Alaska Senate race winner"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXAKSENATE_KXAKSENATE-26NOV03-DSUL.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAKSENATE-26NOV03-DSUL",
                        "event_ticker": "KXAKSENATE-26NOV03",
                        "title": "Will Dan Sullivan win the 2026 Alaska Senate race?",
                        "rules_primary": "If Dan Sullivan wins the 2026 Alaska Senate election, then the market resolves to Yes.",
                        "yes_sub_title": "Dan Sullivan",
                        "status": "active",
                        "last_price_dollars": "0.44",
                    }
                ),
                encoding="utf-8",
            )

            payload = build_kalshi_us_senate_contest_index(
                output_json=root / "index.json",
                output_csv=root / "index.csv",
                output_violations_csv=root / "violations.csv",
                output_violations_json=root / "violations.json",
                output_candidate_winner_json=root / "candidate_winner.json",
                output_candidate_winner_csv=root / "candidate_winner.csv",
                output_party_winner_json=root / "party_winner.json",
                output_party_winner_csv=root / "party_winner.csv",
                output_candidate_nominee_json=root / "candidate_nominee.json",
                output_candidate_nominee_csv=root / "candidate_nominee.csv",
                output_excluded_csv=root / "excluded.csv",
                output_unmapped_csv=root / "unmapped.csv",
                output_ambiguous_csv=root / "ambiguous.csv",
                output_coverage_json=root / "coverage.json",
                output_candidate_match_report_json=root / "candidate_match_report.json",
                output_candidate_match_report_csv=root / "candidate_match_report.csv",
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
                strict=True,
                enforce_required_sample_tickers=False,
            )
            artifacts = payload.get("artifacts") or {}
            candidate_winner_csv = Path(str(artifacts.get("candidate_winner_csv") or ""))
            candidate_winner_json = Path(str(artifacts.get("candidate_winner_json") or ""))
            candidate_match_report_json = Path(str(artifacts.get("candidate_match_report_json") or ""))
            self.assertTrue(candidate_winner_csv.exists())
            self.assertTrue(candidate_winner_json.exists())
            self.assertTrue(candidate_match_report_json.exists())
            self.assertIn("excluded_csv", artifacts)
            self.assertIn("coverage_json", artifacts)
            with candidate_winner_csv.open("r", encoding="utf-8") as handle:
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

    def test_strict_mode_fails_closed_when_mapping_unresolved(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXSENATETX_MISC_Politics.json").write_text(
                json.dumps({"ticker": "KXSENATETX", "title": "Texas Senate nomination market"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXSENATETX_KXSENATETX-26.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXSENATETX-26-FOO",
                        "event_ticker": "KXSENATETX-26",
                        "title": "Will someone be Senate nominee?",
                        "rules_primary": "If someone wins the nomination for Senate then resolves Yes.",
                        "status": "active",
                        "last_price_dollars": "0.55",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                build_kalshi_us_senate_contest_index(
                    output_json=root / "index.json",
                    output_csv=root / "index.csv",
                    output_violations_csv=root / "violations.csv",
                    output_violations_json=root / "violations.json",
                    output_candidate_winner_json=root / "candidate_winner.json",
                    output_candidate_winner_csv=root / "candidate_winner.csv",
                    output_party_winner_json=root / "party_winner.json",
                    output_party_winner_csv=root / "party_winner.csv",
                    output_candidate_nominee_json=root / "candidate_nominee.json",
                    output_candidate_nominee_csv=root / "candidate_nominee.csv",
                    output_excluded_csv=root / "excluded.csv",
                    output_unmapped_csv=root / "unmapped.csv",
                    output_ambiguous_csv=root / "ambiguous.csv",
                    output_coverage_json=root / "coverage.json",
                    output_candidate_match_report_json=root / "candidate_match_report.json",
                    output_candidate_match_report_csv=root / "candidate_match_report.csv",
                    market_dirs=(market_dir,),
                    series_dirs=(series_dir,),
                    override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
                    strict=True,
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_required_general_sample_gate_blocks_when_missing(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)

            (series_dir / "series_KXAKSENATE_Elections.json").write_text(
                json.dumps({"ticker": "KXAKSENATE", "title": "Alaska Senate race winner"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXAKSENATE_KXAKSENATE-26NOV03-DSUL.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAKSENATE-26NOV03-DSUL",
                        "event_ticker": "KXAKSENATE-26NOV03",
                        "title": "Will Dan Sullivan win the 2026 Alaska Senate race?",
                        "rules_primary": "If Dan Sullivan wins the 2026 Alaska Senate election, then the market resolves to Yes.",
                        "status": "active",
                        "last_price_dollars": "0.44",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                build_kalshi_us_senate_contest_index(
                    output_json=root / "index.json",
                    output_csv=root / "index.csv",
                    output_violations_csv=root / "violations.csv",
                    output_violations_json=root / "violations.json",
                    output_candidate_winner_json=root / "candidate_winner.json",
                    output_candidate_winner_csv=root / "candidate_winner.csv",
                    output_party_winner_json=root / "party_winner.json",
                    output_party_winner_csv=root / "party_winner.csv",
                    output_candidate_nominee_json=root / "candidate_nominee.json",
                    output_candidate_nominee_csv=root / "candidate_nominee.csv",
                    output_excluded_csv=root / "excluded.csv",
                    output_unmapped_csv=root / "unmapped.csv",
                    output_ambiguous_csv=root / "ambiguous.csv",
                    output_coverage_json=root / "coverage.json",
                    output_candidate_match_report_json=root / "candidate_match_report.json",
                    output_candidate_match_report_csv=root / "candidate_match_report.csv",
                    market_dirs=(market_dir,),
                    series_dirs=(series_dir,),
                    override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
                    strict=True,
                    enforce_required_sample_tickers=True,
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_strict_mode_blocks_high_impact_candidate_matching_unresolved(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)
            (series_dir / "series_KXAKSENATE_Elections.json").write_text(
                json.dumps({"ticker": "KXAKSENATE", "title": "Alaska Senate race winner"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXAKSENATE_KXAKSENATE-26NOV03-SHIL.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAKSENATE-26NOV03-SHIL",
                        "event_ticker": "KXAKSENATE-26NOV03",
                        "title": "Will Sid Hill win the 2026 Alaska Senate race?",
                        "rules_primary": "If Sid Hill wins the 2026 Alaska Senate election, then the market resolves to Yes.",
                        "yes_sub_title": "Sid Hill",
                        "status": "active",
                        "last_price_dollars": "0.03",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                build_kalshi_us_senate_contest_index(
                    output_json=root / "index.json",
                    output_csv=root / "index.csv",
                    output_violations_csv=root / "violations.csv",
                    output_violations_json=root / "violations.json",
                    output_candidate_winner_json=root / "candidate_winner.json",
                    output_candidate_winner_csv=root / "candidate_winner.csv",
                    output_party_winner_json=root / "party_winner.json",
                    output_party_winner_csv=root / "party_winner.csv",
                    output_candidate_nominee_json=root / "candidate_nominee.json",
                    output_candidate_nominee_csv=root / "candidate_nominee.csv",
                    output_excluded_csv=root / "excluded.csv",
                    output_unmapped_csv=root / "unmapped.csv",
                    output_ambiguous_csv=root / "ambiguous.csv",
                    output_coverage_json=root / "coverage.json",
                    output_candidate_match_report_json=root / "candidate_match_report.json",
                    output_candidate_match_report_csv=root / "candidate_match_report.csv",
                    market_dirs=(market_dir,),
                    series_dirs=(series_dir,),
                    override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
                    strict=True,
                    enforce_required_sample_tickers=False,
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_strict_mode_allows_low_impact_unresolved_candidate_matching(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            series_dir = root / "series"
            market_dir.mkdir(parents=True)
            series_dir.mkdir(parents=True)
            (series_dir / "series_KXAKSENATE_Elections.json").write_text(
                json.dumps({"ticker": "KXAKSENATE", "title": "Alaska Senate race winner"}),
                encoding="utf-8",
            )
            (market_dir / "market_KXAKSENATE_KXAKSENATE-26NOV03-SHIL.json").write_text(
                json.dumps(
                    {
                        "ticker": "KXAKSENATE-26NOV03-SHIL",
                        "event_ticker": "KXAKSENATE-26NOV03",
                        "title": "Will Sid Hill win the 2026 Alaska Senate race?",
                        "rules_primary": "If Sid Hill wins the 2026 Alaska Senate election, then the market resolves to Yes.",
                        "yes_sub_title": "Sid Hill",
                        "status": "active",
                        "last_price_dollars": "0.02",
                    }
                ),
                encoding="utf-8",
            )
            payload = build_kalshi_us_senate_contest_index(
                output_json=root / "index.json",
                output_csv=root / "index.csv",
                output_violations_csv=root / "violations.csv",
                output_violations_json=root / "violations.json",
                output_candidate_winner_json=root / "candidate_winner.json",
                output_candidate_winner_csv=root / "candidate_winner.csv",
                output_party_winner_json=root / "party_winner.json",
                output_party_winner_csv=root / "party_winner.csv",
                output_candidate_nominee_json=root / "candidate_nominee.json",
                output_candidate_nominee_csv=root / "candidate_nominee.csv",
                output_excluded_csv=root / "excluded.csv",
                output_unmapped_csv=root / "unmapped.csv",
                output_ambiguous_csv=root / "ambiguous.csv",
                output_coverage_json=root / "coverage.json",
                output_candidate_match_report_json=root / "candidate_match_report.json",
                output_candidate_match_report_csv=root / "candidate_match_report.csv",
                market_dirs=(market_dir,),
                series_dirs=(series_dir,),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
                strict=True,
                enforce_required_sample_tickers=False,
            )
            report = payload.get("artifacts", {}).get("candidate_match_report_json")
            self.assertTrue(Path(str(report)).exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
