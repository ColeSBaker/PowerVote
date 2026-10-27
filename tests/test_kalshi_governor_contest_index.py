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

from kalshi.kalshi_governor_mapping import (
    build_kalshi_us_governor_contest_index,
    build_kalshi_us_governor_contest_rows,
)


def _workspace_temp_dir() -> Path:
    root = REPO_ROOT / "tmp_test_runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"kalshi_us_gov_{uuid.uuid4().hex[:8]}"
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
GOVPARTYAL_R = {
    "ticker": "GOVPARTYAL-26-R",
    "event_ticker": "GOVPARTYAL-26",
    "title": "Will the Republican party win the governorship in Alabama",
    "yes_sub_title": "Republican party",
    "subtitle": "",
    "rules_primary": "...inaugurated as the governor of Alabama...",
    "last_price_dollars": "0.8000",
    "status": "active",
}
KXGOVAK_ACRU = {
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
KXGOVALNOMR_ACRU = {
    "ticker": "KXGOVALNOMR-26-ACRU",
    "event_ticker": "KXGOVALNOMR-26",
    "title": "Will Adam Crum be the Republican nominee for Governor in Alabama?",
    "yes_sub_title": "Adam Crum",
    "subtitle": ":: Republican",
    "custom_strike": {"Candidate": "Adam Crum"},
    "rules_primary": "If Adam Crum wins the Republican nomination for Governor in Alabama...",
    "last_price_dollars": "0.0500",
    "status": "active",
}
KXGOVALNOMD_XYZ = {
    "ticker": "KXGOVALNOMD-26-XYZ",
    "event_ticker": "KXGOVALNOMD-26",
    "title": "Will Jane Doe be the Democratic nominee for Governor in Alabama?",
    "yes_sub_title": "Jane Doe",
    "subtitle": ":: Democrat",
    "custom_strike": {"Candidate": "Jane Doe"},
    "rules_primary": "If Jane Doe wins the Democratic nomination for Governor in Alabama...",
    "last_price_dollars": "0.0300",
    "status": "active",
}
KXGOVAKPRIMARY_ACRU = {
    "ticker": "KXGOVAKPRIMARY-26-ACRU",
    "event_ticker": "KXGOVAKPRIMARY-26",
    # Real Kalshi title mentions "top-four primary" — triggers advance_count=4
    "title": "Who will win Alaska's top-four primary for Governor?",
    "yes_sub_title": "Adam Crum",
    "subtitle": ":: Republican",
    "custom_strike": {"Candidate": "Adam Crum"},
    # Real Kalshi rules_primary text: "advances" + "top-four" → candidate_advance, advance_count=4
    "rules_primary": (
        "If Adam Crum advances to the general election from Alaska's top-four primary "
        "for Governor in 2026, then the market resolves to Yes."
    ),
    "last_price_dollars": "0.0700",
    "status": "active",
}
# CA governor top-two individual candidate market
KXGOVCAPRIMARY_AVIL = {
    "ticker": "KXGOVCAPRIMARY-26-AVIL",
    "event_ticker": "KXGOVCAPRIMARY-26",
    "title": "Who will win California's top-two primary for governor?",
    "yes_sub_title": "Antonio Villaraigosa",
    "subtitle": ":: Democratic",
    "custom_strike": {"Candidate/Party": "Antonio Villaraigosa"},
    "rules_primary": (
        "If Antonio Villaraigosa advances to the general election for California "
        "governor in 2026, then the market resolves to Yes."
    ),
    "last_price_dollars": "0.0510",
    "status": "active",
}
# CA governor party-combo market ("1 Democrat, 1 Republican advance")
KXGOVCAPRIMARYPARTY_1D1R = {
    "ticker": "KXGOVCAPRIMARYPARTY-26-1D1R",
    "event_ticker": "KXGOVCAPRIMARYPARTY-26",
    "title": "Who will advance from California's top-two primary for governor?",
    "yes_sub_title": "1 Democrat, 1 Republican",
    "subtitle": "",
    "custom_strike": {"Candidate/Party": "1 Democrat, 1 Republican"},
    "rules_primary": (
        "If 1 Democrat and 1 Republican advance to the general election for California "
        "Governor in 2026, then the market resolves to Yes."
    ),
    "last_price_dollars": "0.8200",
    "status": "active",
}
KXCAGOVPRIMARY1ST_AVIL = {
    "ticker": "KXCAGOVPRIMARY1ST-26JUN02-1ST-AVIL",
    "event_ticker": "KXCAGOVPRIMARY1ST-26JUN02-1ST",
    "title": "Will Antonio Villaraigosa finish 1st in the 2026 California Governor primary election?",
    "yes_sub_title": "Antonio Villaraigosa",
    "subtitle": ":: Democratic",
    "last_price_dollars": "0.0500",
    "status": "active",
}
GOVPARTYMI_MD = {
    "ticker": "GOVPARTYMI-26-MD",
    "event_ticker": "GOVPARTYMI-26",
    "title": "Will the Mike Duggan party win the governorship in Michigan",
    "yes_sub_title": "Mike Duggan",
    "subtitle": ":: Independent",
    "custom_strike": {"Party": "Mike Duggan", "State": "Michigan"},
    "last_price_dollars": "0.2200",
    "status": "active",
}
KXLTGOVGA_DEM = {
    "ticker": "KXLTGOVGA-26-DEM",
    "event_ticker": "KXLTGOVGA-26",
    "title": "Will the Democratic party win the Lt. Gov race in Georgia?",
    "yes_sub_title": "Democratic party",
    "subtitle": "::",
    "custom_strike": {"Party": "Democratic"},
    "rules_primary": "...sworn in as the Lieutenant Governor of Georgia...",
    "last_price_dollars": "0.4100",
    "status": "active",
}
KXCLOSESTGOVERNOR = {
    "ticker": "KXCLOSESTGOVERNOR-27JAN20-AK",
    "event_ticker": "KXCLOSESTGOVERNOR-27JAN20",
    "title": "Which state will have the closest Governor race in 2026?",
    "yes_sub_title": "Alaska",
    "subtitle": "",
    "last_price_dollars": "0.0300",
    "status": "active",
}


class KalshiUsGovernorContestIndexTests(unittest.TestCase):

    # -----------------------------------------------------------------------
    # Market type / round classification
    # -----------------------------------------------------------------------

    def test_govparty_ticker_classified_as_party_winner(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, GOVPARTYAL_D)
            contests, violations, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "party_winner")
            self.assertEqual(c["round"], "general")
            self.assertEqual(c["state"], "AL")
            self.assertEqual(c["party"], "D")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_govparty_r_suffix_extracts_party_r(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, GOVPARTYAL_R)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertEqual(contests[0]["party"], "R")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxgov_candidate_ticker_classified_as_candidate_winner(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXGOVAK_ACRU)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_winner")
            self.assertEqual(c["round"], "general")
            self.assertEqual(c["state"], "AK")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxgov_nomr_primary_is_candidate_nominee_party_r(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXGOVALNOMR_ACRU)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_nominee")
            self.assertEqual(c["round"], "primary")
            self.assertEqual(c["party"], "R")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxgov_nomd_primary_is_candidate_nominee_party_d(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXGOVALNOMD_XYZ)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_nominee")
            self.assertEqual(c["party"], "D")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxgov_top_four_primary_is_candidate_advance_advance_count_4(self) -> None:
        """KXGOVAKPRIMARY markets must classify as candidate_advance with advance_count=4."""
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXGOVAKPRIMARY_ACRU)
            contests, violations, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_advance")
            self.assertEqual(c["advance_count"], 4)
            self.assertEqual(c["party"], "R")
            self.assertEqual(c["round"], "primary")
            # Must NOT produce primary_missing_party_lane — candidate_advance is exempt
            violation_types = [v.get("type") for v in violations]
            self.assertNotIn("primary_missing_party_lane", violation_types)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_govca_top_two_primary_is_candidate_advance_advance_count_2(self) -> None:
        """KXGOVCAPRIMARY markets must classify as candidate_advance with advance_count=2."""
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXGOVCAPRIMARY_AVIL)
            contests, violations, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_advance")
            self.assertEqual(c["advance_count"], 2)
            self.assertEqual(c["party"], "D")
            self.assertEqual(c["round"], "primary")
            violation_types = [v.get("type") for v in violations]
            self.assertNotIn("primary_missing_party_lane", violation_types)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_govca_primary_party_combo_classified_correctly(self) -> None:
        """KXGOVCAPRIMARYPARTY markets must classify as primary_party_combo, no violations."""
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXGOVCAPRIMARYPARTY_1D1R)
            contests, violations, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "primary_party_combo")
            self.assertEqual(c["round"], "primary")
            # primary_party_combo has no party lane
            self.assertIsNone(c["party"])
            # Must not raise primary_missing_party_lane
            violation_types = [v.get("type") for v in violations]
            self.assertNotIn("primary_missing_party_lane", violation_types)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_advance_sum_out_of_band_emits_violation(self) -> None:
        """When yes_price sum deviates beyond ±20% of advance_count×100, emit violation."""
        # Build 3 candidates for a top-two primary with prices summing to 3.0 (300% > 240%)
        candidates = [
            {
                "ticker": f"KXGOVCAPRIMARY-26-C{i}",
                "event_ticker": "KXGOVCAPRIMARY-26",
                "title": "Who will win California's top-two primary for governor?",
                "yes_sub_title": f"Candidate {i}",
                "subtitle": ":: Democratic",
                "custom_strike": {"Candidate/Party": f"Candidate {i}"},
                "rules_primary": (
                    f"If Candidate {i} advances to the general election for California "
                    "governor in 2026, then the market resolves to Yes."
                ),
                "last_price_dollars": "1.0000",  # 100% each × 3 candidates = sum 300%
                "status": "active",
            }
            for i in range(3)
        ]
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            for m in candidates:
                _write_market(market_dir, m)
            _, violations, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            violation_types = [v.get("type") for v in violations]
            self.assertIn(
                "advance_sum_out_of_band",
                violation_types,
                msg=f"Expected advance_sum_out_of_band, got: {violation_types}",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Exclusion gates
    # -----------------------------------------------------------------------

    def test_finish_position_market_excluded(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXCAGOVPRIMARY1ST_AVIL)
            contests, _, summary = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 0)
            excluded = summary.get("excluded_markets") or []
            tickers = [e["market_ticker"] for e in excluded]
            self.assertIn("KXCAGOVPRIMARY1ST-26JUN02-1ST-AVIL", tickers)
            reasons = {e["exclusion_reason"] for e in excluded}
            self.assertIn("finish_position_market", reasons)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_ltgov_market_not_in_governor_index(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXLTGOVGA_DEM)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_kxclosestgovernor_not_in_governor_index(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, KXCLOSESTGOVERNOR)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Individual-in-party-series reclassification (Mike Duggan)
    # -----------------------------------------------------------------------

    def test_govparty_individual_candidate_reclassified_as_candidate_winner(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, GOVPARTYMI_MD)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            c = contests[0]
            self.assertEqual(c["market_type"], "candidate_winner")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # State extraction
    # -----------------------------------------------------------------------

    def test_state_extracted_from_govparty_ticker(self) -> None:
        states_and_payloads = [
            ("AL", GOVPARTYAL_D),
            ("AK", KXGOVAK_ACRU),
        ]
        for expected_state, payload in states_and_payloads:
            root = _workspace_temp_dir()
            try:
                market_dir = root / "market"
                market_dir.mkdir()
                _write_market(market_dir, payload)
                contests, _, _ = build_kalshi_us_governor_contest_rows(
                    market_dirs=(market_dir,),
                    series_dirs=(),
                    override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
                )
                self.assertTrue(len(contests) >= 1, msg=f"No contests for {expected_state}")
                self.assertEqual(contests[0]["state"], expected_state, msg=f"Wrong state for {payload['ticker']}")
            finally:
                shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # seat_id / contest_id / office field
    # -----------------------------------------------------------------------

    def test_seat_id_format_is_state_gov(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            for payload in [GOVPARTYAL_D, GOVPARTYAL_R, KXGOVAK_ACRU]:
                _write_market(market_dir, payload)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            pattern = re.compile(r"^[A-Z]{2}-GOV$")
            for c in contests:
                self.assertRegex(c["seat_id"], pattern, msg=f"Bad seat_id: {c['seat_id']}")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_contest_id_prefix_is_us_gov(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, GOVPARTYAL_D)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertTrue(contests[0]["contest_id"].startswith("US-GOV:"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_office_field_is_gov(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, GOVPARTYAL_D)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertEqual(contests[0]["office"], "GOV")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Cycle year extraction
    # -----------------------------------------------------------------------

    def test_cycle_year_from_26_suffix(self) -> None:
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, GOVPARTYAL_D)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertEqual(contests[0]["cycle_year"], 2026)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cycle_year_from_26_date_suffix(self) -> None:
        payload = {
            "ticker": "KXGOVAK-26NOV03-ACRU",
            "event_ticker": "KXGOVAK-26NOV03",
            "title": "Who will win the governorship in Alaska?",
            "yes_sub_title": "Adam Crum",
            "subtitle": ":: Republican",
            "rules_primary": "If Adam Crum is sworn in as the governor of Alaska...",
            "last_price_dollars": "0.0200",
            "status": "active",
        }
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, payload)
            contests, _, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            self.assertEqual(len(contests), 1)
            self.assertEqual(contests[0]["cycle_year"], 2026)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Violation: primary missing party lane
    # -----------------------------------------------------------------------

    def test_primary_missing_party_lane_is_violation(self) -> None:
        # No NOM suffix, no subtitle party, no -D/-R suffix → no party lane
        payload = {
            "ticker": "KXGOVAKPRIMARY-26-JKRE",
            "event_ticker": "KXGOVAKPRIMARY-26",
            "title": "Will John Krebs win the Alaska Governor Primary?",
            "yes_sub_title": "John Krebs",
            "subtitle": "",
            "rules_primary": "If John Krebs wins the primary for governor of Alaska...",
            "last_price_dollars": "0.0500",
            "status": "active",
        }
        root = _workspace_temp_dir()
        try:
            market_dir = root / "market"
            market_dir.mkdir()
            _write_market(market_dir, payload)
            contests, violations, _ = build_kalshi_us_governor_contest_rows(
                market_dirs=(market_dir,),
                series_dirs=(),
                override_registry={"ticker_overrides": {}, "ticker_prefix_overrides": {}},
            )
            violation_types = [v.get("type") for v in violations]
            self.assertTrue(
                any("primary_missing_party_lane" in str(vt) for vt in violation_types),
                msg=f"Expected primary_missing_party_lane violation, got: {violation_types}",
            )
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
            _write_market(market_dir, GOVPARTYAL_D)
            _write_market(market_dir, KXGOVAK_ACRU)

            out = root / "out"
            build_kalshi_us_governor_contest_index(
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
