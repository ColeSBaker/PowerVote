import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = ROOT / "scripts" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import publish_snapshot_artifacts as publisher


class PublishSnapshotArtifactsTests(unittest.TestCase):
    def test_build_artifact_inputs_only_includes_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            existing = data / "ballotpedia-general-election-rollup.csv"
            existing.write_text("seat\nAL-01\n", encoding="utf-8")
            missing = data / "does-not-exist.csv"
            artifacts = publisher.build_artifact_inputs(data, [existing.name, missing.name])
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0].path, existing)

    def test_publish_writes_manifest_and_validation_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir(parents=True, exist_ok=True)
            (data / "rollup-snapshot-date.txt").write_text("2026-04-02\n", encoding="utf-8")
            (data / "ballotpedia-general-election-rollup.csv").write_text("seat\nAL-01\n", encoding="utf-8")

            manifest_path, validation_path = publisher.publish_snapshot(
                data_dir=data,
                output_manifest=data / "snapshot_manifest.json",
                output_validation=data / "snapshot_validation_report.json",
                bucket="powervote-snapshots",
                schema_version="v1",
                unresolved_high_impact=0,
                unresolved_included_senate_markets=0,
                required_files=["ballotpedia-general-election-rollup.csv"],
                source_lineage=["ballotpedia-general-election-rollup.csv"],
            )

            self.assertTrue(manifest_path.exists())
            self.assertTrue(validation_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["snapshotDate"], "2026-04-02")
            self.assertTrue(validation["passed"])


if __name__ == "__main__":
    unittest.main()
