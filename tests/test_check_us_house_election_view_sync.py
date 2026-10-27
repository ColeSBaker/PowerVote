import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / 'scripts' / 'check_us_house_election_view_sync.py'
spec = importlib.util.spec_from_file_location('check_us_house_election_view_sync', MODULE_PATH)
check_us_house_election_view_sync = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_us_house_election_view_sync)


class CheckUsHouseElectionViewSyncTests(unittest.TestCase):
    def test_passes_when_builder_unchanged(self):
        with patch.object(check_us_house_election_view_sync, 'collect_changed_files', return_value={'README.md'}):
            self.assertEqual(check_us_house_election_view_sync.main(), 0)

    def test_fails_when_builder_changes_without_companion_file(self):
        with patch.object(
            check_us_house_election_view_sync,
            'collect_changed_files',
            return_value={'scripts/build_us_house_election_view.py'},
        ):
            self.assertEqual(check_us_house_election_view_sync.main(), 1)

    def test_passes_when_builder_changes_with_ui_update(self):
        with patch.object(
            check_us_house_election_view_sync,
            'collect_changed_files',
            return_value={'scripts/build_us_house_election_view.py', 'apps/web/congressional-map.js'},
        ):
            self.assertEqual(check_us_house_election_view_sync.main(), 0)


if __name__ == '__main__':
    unittest.main()
