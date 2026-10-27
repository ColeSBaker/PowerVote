import unittest
from pathlib import Path
import tempfile
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = ROOT / "scripts" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import load_rollups_to_postgres as loader


class RollupPipelineLoaderTests(unittest.TestCase):
    def test_normalize_seat_id(self):
        self.assertEqual(loader.normalize_seat_id("tx-1"), "TX-01")
        self.assertEqual(loader.normalize_seat_id("AK-AL"), "AK-AL")

    def test_parse_bool(self):
        self.assertTrue(loader.parse_bool("True"))
        self.assertTrue(loader.parse_bool("1"))
        self.assertFalse(loader.parse_bool("False"))
        self.assertFalse(loader.parse_bool(None))

    def test_ensure_files_exist_raises_for_missing(self):
        missing = Path("this/file/does/not/exist.csv")
        with self.assertRaises(FileNotFoundError):
            loader.ensure_files_exist([missing])

    def test_validation_allows_promote(self):
        self.assertTrue(loader.validation_allows_promote({"passed": True}))
        self.assertFalse(loader.validation_allows_promote({"passed": False}))

    def test_load_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.json"
            path.write_text(json.dumps({"ok": True}), encoding="utf-8")
            payload = loader.load_json_payload(path)
            self.assertEqual(payload, {"ok": True})


if __name__ == "__main__":
    unittest.main()
