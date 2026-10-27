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

from kalshi.kalshi_ltgov_mapping import (
    build_kalshi_us_ltgov_contest_index,
    build_kalshi_us_ltgov_contest_rows,
)


def _workspace_temp_dir() -> Path:
    root = REPO_ROOT / "tmp_test_runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"kalshi_us_ltgov_{uuid.uuid4().hex[:8]}"
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

KXLTGOVGA_DEM = {
    "ticker": "KXLTGOVGA-26-DEM",
    "event_ticker": "KXLTGOVGA-26",
    "title": "Which party will win the Lt. Gov race in Georgia?",
    "yes_sub_title": "Democratic party",
    "subtitle": "::",
    "custom_strike": {"Party": "Democratic"},
    "rules_primary": "...sworn in as the Lieutenant Governor of Georgia...",
    "last_price_dollars": "0.4100",
    "status": "active",
}
KXLTGOVTX_GOP = {
    "ticker": "KXLTGOVTX-26-GOP",
    "event_ticker": "KXLTGOVTX-26",
    "title": "Which party will win the Lt. Gov race in Texas?",
    "yes_sub_title": "Republican party",
    "subtitle": "::",
    "custom_strike": {"Party": "Republican"},
    "rules_primary": "...sworn in as the Lieutenant Governor of Texas...",
    "last_price_dollars": "0.8500",
    "status": "active",
}
KXLTGOVOKNOMR_BHIL = {
    "ticker": "KXLTGOVOKNOMR-26-BHIL",
    "event_ticker": "KXLTGOVOKNOMR-26",
    "title": "Will Brian Hill be the Republican nominee for Lt. Governor in Oklahoma?",
    "yes_sub_title": "Brian Hill",
    "subtitle": "",
    "custom_strike": {"Candidate": "Brian Hill"},
    "rules_primary": "If Brian Hill wins the nomination for the Republican Party...",
    "last_price_dollars": "0.0600",
    "status": "active",
}
KXCALIEUTENANTGOV_BDAH = {
    "ticker": "KXCALIEUTENANTGOV-26NOV03-BDAH",
    "event_ticker": "KXCALIEUTENANTGOV-26NOV03",
    "title": "Will Brian Dahle win the 2026 California Lieutenant Governor election?",
    "yes_sub_title": "Brian Dahle",
    "subtitle": ":: Republican",
    "custom_strike": {"Option": "Brian Dahle"},
    "rules_primary": "If Brian Dahle wins the 2026 California Lieutenant Governor election...",
    "last_price_dollars": "0.0100",
    "status": "active",
}
KXGA1ROUND_LTGOV = {
    "ticker": "KXGA1ROUND-26NOV03-LTGOV",
    "event_ticker": "KXGA1ROUND-26NOV03",
    "title": "Will anyone win the 2026 Georgia Lieutenant Governor general election in the first round?",
    "yes_sub_title": "Lieutenant Governor",
    "subtitle": "",
    "last_price_dollars": "0.7800",
    "status": "active",
}
GOVPARTYAL_D = {
    "ticker": "GOVPARTYAL-26-D",
    "event_ticker": "GOVPARTYAL-26",
    "title": "Will the Democratic party win the governorship in Alabama",
    "yes_sub_title": "Democratic party",
    "subtitle": "",
    "rules_primary": "...inaugurated as the governor of Alabama...",
    "last_price_dollars": "0.1000",
    "status": "active",
}


class KalshiUsLtGovContestIndexTests(unittest.TestCase):

    # -----------------------------------------------------------------------
    # Market type / party classification
    # -----------------------------------------------------------------------

    def test_kxltgov_dem_suffix_is_party_winner(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVGA_DEM)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "party_winner")
            self.assertEqual(c["party"], "D")
            self.assertEqual(c["state"], "GA")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxltgov_gop_suffix_is_party_winner_r(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVTX_GOP)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "party_winner")
            self.assertEqual(c["party"], "R")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxltgovoknomr_is_candidate_nominee_r(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVOKNOMR_BHIL)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_nominee")
            self.assertEqual(c["party"], "R")
            self.assertEqual(c["state"], "OK")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxcalieutenantgov_is_candidate_winner_ca(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXCALIEUTENANTGOV_BDAH)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_winner")
            self.assertEqual(c["state"], "CA")
            self.assertEqual(c["seat_id"], "CA-LTGOV")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Exclusion gates
    # -----------------------------------------------------------------------

    def test_kxga1round_ltgov_excluded_as_meta(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXGA1ROUND_LTGOV)
            contests, _, summary = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 0)
            excluded = summary.get("excluded_markets") or []
            tickers = [e["market_ticker"] for e in excluded]
            self.assertIn("KXGA1ROUND-26NOV03-LTGOV", tickers)
            reasons = {e["exclusion_reason"] for e in excluded}
            self.assertIn("meta_market_first_round", reasons)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_governor_market_not_in_ltgov_index(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, GOVPARTYAL_D)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # State extraction
    # -----------------------------------------------------------------------

    def test_kxltgov_state_ok_extracted_from_oknomr(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVOKNOMR_BHIL)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertEqual(contests[0]["state"], "OK")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # seat_id / contest_id / office
    # -----------------------------------------------------------------------

    def test_seat_id_format_is_state_ltgov(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            for payload in [KXLTGOVGA_DEM, KXLTGOVTX_GOP, KXCALIEUTENANTGOV_BDAH]:
                _write_market(market_dir, payload)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            pattern = re.compile(r"^[A-Z]{2}-LTGOV$")
            for c in contests:
                self.assertRegex(c["seat_id"], pattern, msg=f"Bad seat_id: {c['seat_id']}")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_contest_id_prefix_is_us_ltgov(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVGA_DEM)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertTrue(contests[0]["contest_id"].startswith("US-LTGOV:"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_office_field_is_ltgov(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVGA_DEM)
            contests, _, _ = build_kalshi_us_ltgov_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertEqual(contests[0]["office"], "LTGOV")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Full index build (artifact files)
    # -----------------------------------------------------------------------

    def test_writes_all_artifact_files(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVGA_DEM)
            _write_market(market_dir, KXCALIEUTENANTGOV_BDAH)

            out = root / "out"
            build_kalshi_us_ltgov_contest_index(
                output_json=out / "index.json",
                output_csv=out / "index.csv",
                output_violations_csv=out / "violations.csv",
                output_violations_json=out / "violations.json",
                output_candidate_winner_json=out / "winner.json",
                output_candidate_winner_csv=out / "winner.csv",
                output_party_winner_json=out / "party.json",
                output_party_winner_csv=out / "party.csv",
                output_candidate_nominee_json=out / "nominee.json",
                output_candidate_nominee_csv=out / "nominee.csv",
                output_excluded_csv=out / "excluded.csv",
                output_unmapped_csv=out / "unmapped.csv",
                output_ambiguous_csv=out / "ambiguous.csv",
                output_coverage_json=out / "coverage.json",
                output_candidate_match_report_json=out / "match_report.json",
                output_candidate_match_report_csv=out / "match_report.csv",
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
                strict=False,
            )
            expected = [
                "index.json", "index.csv",
                "violations.csv", "violations.json",
                "winner.json", "winner.csv",
                "party.json", "party.csv",
                "nominee.json", "nominee.csv",
                "excluded.csv", "unmapped.csv", "ambiguous.csv",
                "coverage.json", "match_report.json", "match_report.csv",
            ]
            for name in expected:
                self.assertTrue((out / name).exists(), msg=f"Missing artifact: {name}")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
