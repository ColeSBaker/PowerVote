import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.parser import parse_all
from tests.raw_data import requires_raw_data


@requires_raw_data
class BallotpediaRollupSplitRollupsTests(unittest.TestCase):
    def test_parse_all_emits_primary_and_runoff_rollups(self):
        input_dir = REPO_ROOT / "test_data" / "candidates" / "ballotpedia" / "ballotpedia_house_raw"
        general_rows, primary_rows, runoff_rows, _counts = parse_all(input_dir)

        self.assertGreater(len(general_rows), 0)
        self.assertGreater(len(primary_rows), 0)
        self.assertGreater(len(runoff_rows), 0)
        self.assertTrue(all(row.get("round") != "runoff" for row in primary_rows))
        self.assertTrue(all(row.get("round") == "runoff" for row in runoff_rows))


if __name__ == "__main__":
    unittest.main()
