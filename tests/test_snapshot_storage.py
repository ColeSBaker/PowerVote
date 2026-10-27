import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = ROOT / "scripts" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import snapshot_storage


class SnapshotStorageTests(unittest.TestCase):
    def test_compute_file_hash_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_text("abc", encoding="utf-8")
            digest = snapshot_storage.compute_file_hash(path)
            self.assertEqual(digest, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_build_snapshot_manifest_counts_csv_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "example.csv"
            csv_path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
            json_path = root / "example.json"
            json_path.write_text(json.dumps([{"x": 1}, {"x": 2}, {"x": 3}]), encoding="utf-8")

            manifest = snapshot_storage.build_snapshot_manifest(
                snapshot_id="2026-04-02T12:00:00Z",
                snapshot_date="2026-04-02",
                schema_version="v1",
                source_lineage=["one.csv", "two.csv"],
                artifacts=[
                    snapshot_storage.ArtifactInput(name="example_csv", path=csv_path),
                    snapshot_storage.ArtifactInput(name="example_json", path=json_path),
                ],
                bucket="powervote-snapshots",
                prefix="2026-04-02",
            )

            self.assertEqual(manifest["snapshotId"], "2026-04-02T12:00:00Z")
            self.assertEqual(len(manifest["artifacts"]), 2)
            self.assertEqual(manifest["artifacts"][0]["rowCount"], 2)
            self.assertEqual(manifest["artifacts"][1]["rowCount"], 3)
            self.assertTrue(manifest["artifacts"][0]["contentHash"])
            self.assertTrue(manifest["artifacts"][1]["uri"].startswith("s3://powervote-snapshots/2026-04-02/"))

    def test_validation_gates_detect_blocking_issues(self):
        gates = snapshot_storage.evaluate_validation_gates(
            unresolved_high_impact=1,
            unresolved_included_senate_markets=0,
            schema_contract_ok=True,
            artifact_hashes_ok=True,
            required_artifacts_present=True,
        )
        self.assertFalse(gates["passed"])
        self.assertIn("unresolved_high_impact", gates["failures"])

    def test_validation_gates_pass_when_all_green(self):
        gates = snapshot_storage.evaluate_validation_gates(
            unresolved_high_impact=0,
            unresolved_included_senate_markets=0,
            schema_contract_ok=True,
            artifact_hashes_ok=True,
            required_artifacts_present=True,
        )
        self.assertTrue(gates["passed"])
        self.assertEqual(gates["failures"], [])


if __name__ == "__main__":
    unittest.main()
