import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup import cli, parser
from tests.raw_data import requires_raw_data


class BallotpediaRollupPerformanceTests(unittest.TestCase):
    def test_parse_ballotpedia_fec_unmatched_reuses_existing_row_maps(self):
        primary_rows = [
            {
                "seat": "TX-01",
                "party": "D",
                "primary_id": "TX-1-D-primary-2026",
                "candidates": ["Alice Candidate"],
                "candidate_party_map": {"Alice Candidate": "D"},
                "candidate_fec_id_map": {},
                "candidate_fec_match_strategy_map": {"Alice Candidate": "no_match"},
                "candidate_fec_match_score_map": {"Alice Candidate": 0.12},
            }
        ]
        with mock.patch.object(parser, "parse_all", side_effect=AssertionError("parse_all should not be called")):
            unmatched = parser.parse_ballotpedia_fec_unmatched(
                REPO_ROOT / "test_data",
                primary_rows=primary_rows,
                runoff_rows=[],
            )
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched[0]["ballotpedia_name"], "Alice Candidate")
        self.assertEqual(unmatched[0]["reason"], "no_match")

    def test_build_rollup_context_uses_single_parse_pass(self):
        fake_general = [{"seat": "TX-01"}]
        fake_primary = [{"seat": "TX-01", "candidates": []}]
        fake_runoff = []
        fake_counts = {"district_detail": 1, "state_rollup": 0, "national_overview": 0, "unknown": 0}

        with mock.patch.object(parser, "parse_all", return_value=(fake_general, fake_primary, fake_runoff, fake_counts)) as parse_all_mock, \
            mock.patch.object(parser, "parse_national_incumbent_departures", return_value=[]), \
            mock.patch.object(parser, "parse_ballotpedia_fec_unmatched", return_value=[]) as fec_unmatched_mock, \
            mock.patch.object(parser, "collect_kalshi_rollup_join_audit", return_value=[]), \
            mock.patch.object(parser, "collect_ballotpedia_kalshi_unmatched_candidates", return_value=[]), \
            mock.patch.object(parser, "load_fec_rows", return_value=[]), \
            mock.patch.object(parser, "load_fec_candidates", return_value=[]):
            context = parser.build_rollup_context(REPO_ROOT / "test_data")

        self.assertEqual(parse_all_mock.call_count, 1)
        self.assertEqual(context.general_rows, fake_general)
        self.assertEqual(context.primary_rows, fake_primary)
        self.assertEqual(context.runoff_rows, fake_runoff)
        self.assertEqual(fec_unmatched_mock.call_count, 1)
        called_kwargs = fec_unmatched_mock.call_args.kwargs
        self.assertIs(called_kwargs["primary_rows"], fake_primary)
        self.assertIs(called_kwargs["runoff_rows"], fake_runoff)

    def test_preflight_output_paths_writable_raises_for_locked_path(self):
        class _DummyParent:
            def mkdir(self, parents=True, exist_ok=True):
                return None

        class _DummyPath:
            parent = _DummyParent()

            def exists(self):
                return True

            def open(self, mode):  # pragma: no cover - used by test assertion path
                raise OSError("locked by another process")

            def __str__(self):
                return "dummy-output.csv"

        with self.assertRaises(RuntimeError):
            cli._preflight_output_paths_writable([_DummyPath()])

    @requires_raw_data
    def test_incremental_parse_cache_reuses_cached_page_payload(self):
        fixture_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        source_file = fixture_dir / "TX-1.txt"
        cache_path = REPO_ROOT / ".cache" / "test-parse-cache.json"
        captured_cache: dict = {}

        def _capture_save(_path, payload):
            captured_cache.clear()
            captured_cache.update(payload)

        with mock.patch.object(parser, "list_input_files", return_value=[source_file]), \
            mock.patch.object(parser, "_load_parse_cache", return_value={"version": parser.PARSE_CACHE_VERSION, "entries": {}}), \
            mock.patch.object(parser, "_save_parse_cache", side_effect=_capture_save):
            first = parser.parse_all(fixture_dir, incremental=True, cache_path=cache_path)

        with mock.patch.object(parser, "list_input_files", return_value=[source_file]), \
            mock.patch.object(parser, "_load_parse_cache", return_value=captured_cache), \
            mock.patch.object(parser, "_save_parse_cache"), \
            mock.patch.object(parser, "parse_district_detail_file", side_effect=AssertionError("cache not used")):
            second = parser.parse_all(fixture_dir, incremental=True, cache_path=cache_path)

        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])
        self.assertEqual(first[2], second[2])
        self.assertTrue((captured_cache.get("entries") or {}))


if __name__ == "__main__":
    unittest.main()
