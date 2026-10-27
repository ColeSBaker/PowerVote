import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = ROOT / "scripts" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import retention_prune_postgres as prune


class RetentionPruneTests(unittest.TestCase):
    def test_cutoff_date_days(self):
        cutoff = prune.cutoff_date(90)
        self.assertLessEqual((prune.date.today() - cutoff).days, 90)
        self.assertGreaterEqual((prune.date.today() - cutoff).days, 89)

    def test_build_prune_sql_preserves_active(self):
        sql = prune.build_prune_sql().lower()
        self.assertIn("active_batch", sql)
        self.assertIn("status <> 'active'", sql)


if __name__ == "__main__":
    unittest.main()
