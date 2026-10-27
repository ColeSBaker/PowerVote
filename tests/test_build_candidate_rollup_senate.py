import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_candidate_rollup_senate import (
    _build_candidate_rows,
    _headers_from_template,
    _load_rows,
    run_cli,
)

DATA_DIR = Path(os.environ.get("POWERVOTE_DATA_DIR", str(REPO_ROOT / "apps" / "web" / "data")))


def _numeric_map_sum(odds_map: dict) -> tuple[int, float]:
    values = []
    for v in odds_map.values():
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    return len(values), round(sum(values), 2)


class BuildCandidateRollupSenateTests(unittest.TestCase):
    def test_build_senate_candidate_rollup_matches_house_header(self):
        house_template = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-2026.csv"
        with house_template.open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            template_file = tmp_path / "template.csv"
            template_file.write_text(",".join(header) + "\n", encoding="utf-8")

            primary_file = tmp_path / "primary.csv"
            runoff_file = tmp_path / "runoff.csv"
            general_file = tmp_path / "general.csv"
            out_csv = tmp_path / "senate-candidates.csv"
            out_json = tmp_path / "senate-candidates.json"

            primary_file.write_text(
                "\n".join(
                    [
                        "seat,party,primary_id,candidates,primary_vote_count,primary_vote_share,runoff_id,kalshi_primary_odds_map,kalshi_runoff_odds_map",
                        'TX-SEN-C2,D,TX-SEN-C2-D-primary-2026,"[""Alice Example"",""Bob Example""]","{""Alice Example"":1200,""Bob Example"":800}","{""Alice Example"":60.0,""Bob Example"":40.0}",,"{""Alice Example"":62.0,""Bob Example"":38.0}","{""Alice Example"":65.0}"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            runoff_file.write_text(
                "\n".join(
                    [
                        "seat,party,primary_id,parent_primary_id,candidates",
                        'TX-SEN-C2,D,TX-SEN-C2-D-runoff-2026,TX-SEN-C2-D-primary-2026,"[""Alice Example"",""Bob Example""]"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            general_file.write_text(
                "\n".join(
                    [
                        "seat,nominee_d,nominee_r,other_general_candidates,primary_id_d,primary_id_r,primary_date,runoff_date,general_date,incumbent_name,incumbent_party",
                        'TX-SEN-C2,Alice Example,Rick Rival,"[""Ivy Independent""]",TX-SEN-C2-D-primary-2026,TX-SEN-C2-R-primary-2026,2026-03-03,2026-05-05,2026-11-03,Rick Rival,R',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            exit_code = run_cli(
                [
                    "--primary-file",
                    str(primary_file),
                    "--runoff-file",
                    str(runoff_file),
                    "--general-file",
                    str(general_file),
                    "--template-file",
                    str(template_file),
                    "--out-csv",
                    str(out_csv),
                    "--out-json",
                    str(out_json),
                ]
            )
            self.assertEqual(exit_code, 0)

            with out_csv.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
                out_header = list(rows[0].keys())
            # OutOfBand flag columns are injected after their map columns if absent in the template.
            expected_header = list(header)
            for map_col, flag_col in (
                ("KalshiPrimaryOddsMap", "KalshiPrimaryOddsMapOutOfBand"),
                ("KalshiGeneralOddsMap", "KalshiGeneralOddsMapOutOfBand"),
            ):
                if flag_col not in expected_header and map_col in expected_header:
                    expected_header.insert(expected_header.index(map_col) + 1, flag_col)
            self.assertEqual(out_header, expected_header)

            by_name = {row["BallotpediaName"]: row for row in rows}
            self.assertEqual(by_name["Alice Example"]["Status"], "general (nominated)")
            self.assertEqual(by_name["Rick Rival"]["Status"], "general (nominated)")
            self.assertEqual(by_name["Ivy Independent"]["Status"], "general (other)")
            self.assertEqual(by_name["Rick Rival"]["IsIncumbent"], "True")
            self.assertEqual(by_name["Alice Example"]["IsIncumbent"], "False")
            self.assertEqual(by_name["Alice Example"]["KalshiBestPrimaryOdds"], "65.0")
            self.assertEqual(by_name["Bob Example"]["KalshiBestPrimaryOdds"], "38.0")

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["rowCount"], len(rows))


class SenateKalshiOddsMapIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template = DATA_DIR / "candidate-rollup-2026.csv"
        headers = _headers_from_template(template)
        cls.rows = _build_candidate_rows(
            headers=headers,
            general_rows=_load_rows(DATA_DIR / "ballotpedia-senate-general-election-rollup.csv"),
            primary_rows=_load_rows(DATA_DIR / "ballotpedia-senate-primary-election-rollup.csv"),
            runoff_rows=_load_rows(DATA_DIR / "ballotpedia-senate-runoff-election-rollup.csv"),
        )

    def test_candidate_odds_maps_sum_range(self):
        flag_by_field = {
            "KalshiPrimaryOddsMap": "KalshiPrimaryOddsMapOutOfBand",
            "KalshiGeneralOddsMap": "KalshiGeneralOddsMapOutOfBand",
        }
        for row in self.rows:
            for field in ("KalshiPrimaryOddsMap", "KalshiGeneralOddsMap"):
                if row.get(flag_by_field[field]):
                    continue
                raw = row.get(field)
                if isinstance(raw, str):
                    try:
                        odds_map = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        odds_map = {}
                else:
                    odds_map = raw or {}
                count, total = _numeric_map_sum(odds_map)
                if count >= 2:
                    self.assertTrue(
                        90.0 <= total <= 110.0,
                        msg=f"{row.get('2026 Seat')} {row.get('BallotpediaName')} {field} sum={total}",
                    )

    def test_out_of_band_flag_set_when_odds_sum_exceeds_threshold(self):
        for row in self.rows:
            raw = row.get("KalshiPrimaryOddsMap")
            if isinstance(raw, str):
                try:
                    odds_map = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    odds_map = {}
            else:
                odds_map = raw or {}
            count, total = _numeric_map_sum(odds_map)
            if count >= 2 and not (90.0 <= total <= 110.0):
                self.assertTrue(
                    row.get("KalshiPrimaryOddsMapOutOfBand"),
                    msg=f"{row.get('2026 Seat')} {row.get('BallotpediaName')} sum={total} but flag not set",
                )


if __name__ == "__main__":
    unittest.main()
