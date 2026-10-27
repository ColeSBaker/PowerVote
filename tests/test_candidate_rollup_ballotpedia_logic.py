import csv
import os
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = Path(os.environ.get("POWERVOTE_DATA_DIR", str(REPO_ROOT / "apps" / "web" / "data")))
PRIMARY_ROLLUP_PATH = _DATA_DIR / "ballotpedia-primary-election-rollup.csv"
CANDIDATE_ROLLUP_PATH = Path(os.environ.get("POWERVOTE_CANDIDATE_ROLLUP_CSV", str(_DATA_DIR / "candidate-rollup-2026.csv")))


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


class CandidateRollupBallotpediaLogicTests(unittest.TestCase):
    def test_primaries_with_vote_totals_are_not_left_in_primary_status(self):
        primary_rows = _load_csv(PRIMARY_ROLLUP_PATH)
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)

        # find a primary with a numeric primary_vote_total > 0
        target = None
        for row in primary_rows:
            total = _parse_float(row.get("primary_vote_total"))
            if total is not None and total > 0:
                pid = (row.get("primary_id") or "").strip()
                if pid:
                    # ensure there are candidate rows tied to that primary
                    have = [c for c in candidate_rows if (c.get("Primary ID") or "").strip() == pid]
                    if have:
                        target = pid
                        break

        if target is None:
            self.skipTest("No primaries with numeric primary_vote_total > 0 found in rollup")

        offenders = [c for c in candidate_rows if (c.get("Primary ID") or "").strip() == target and (c.get("Status") or "").strip() == "primary"]
        self.assertEqual(len(offenders), 0, f"Found candidate rows left with Status==primary for primary_id={target}: {offenders}")

    def test_IL9_duplicate_nominee_resolved(self):
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)
        primary_id = "IL-9-R-primary-2026"
        candidates = [c for c in candidate_rows if (c.get("Primary ID") or "").strip() == primary_id]
        nominated = [c for c in candidates if (c.get("Status") or "").strip() == "general (nominated)"]
        self.assertLessEqual(len(nominated), 1, f"Expected <=1 general (nominated) in {primary_id}, found {len(nominated)}")

    def test_CO3_primary_dedupes_jeff_hurd_aliases(self):
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)
        primary_id = "CO-3-R-primary-2026"
        rows = [r for r in candidate_rows if (r.get("Primary ID") or "").strip() == primary_id]
        normalized_names = {(r.get("BallotpediaName") or "").strip().upper() for r in rows}
        jeff_like = [name for name in normalized_names if "HURD" in name]
        self.assertEqual(len(jeff_like), 1, f"Expected one HURD identity in {primary_id}, found {jeff_like}")

    def test_TX1_runoff_has_exactly_two_unique_candidates(self):
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)
        runoff_id = "TX-1-D-runoff-2026"
        rows = [r for r in candidate_rows if (r.get("RunoffID") or "").strip() == runoff_id and (r.get("Status") or "").strip() == "runoff"]
        normalized_names = {(r.get("BallotpediaName") or "").strip().upper() for r in rows}
        self.assertEqual(len(normalized_names), 2, f"Expected 2 runoff candidates in {runoff_id}, found {sorted(normalized_names)}")

    def test_CA20_CA25_nonpartisan_primary_coverage_present(self):
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)
        expected_counts = {
            "CA-20-NP-primary-2026": 4,
            "CA-25-NP-primary-2026": 4,
        }
        for primary_id, expected_count in expected_counts.items():
            rows = [r for r in candidate_rows if (r.get("Primary ID") or "").strip() == primary_id]
            self.assertGreaterEqual(
                len(rows),
                expected_count,
                f"Expected at least {expected_count} rows for {primary_id}, found {len(rows)}",
            )

    def test_CA2_jared_huffman_uses_candidate_affiliation_and_incumbency(self):
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)
        rows = [
            r for r in candidate_rows
            if (r.get("Primary ID") or "").strip() == "CA-2-NP-primary-2026"
            and (r.get("BallotpediaName") or "").strip().upper() == "JARED HUFFMAN"
        ]
        self.assertGreaterEqual(len(rows), 1, "Expected Jared Huffman row in CA-2 NP primary")
        row = rows[0]
        self.assertEqual((row.get("Party") or "").strip(), "DEM")
        self.assertEqual((row.get("BallotpediaIsIncumbent") or "").strip().lower(), "true")
        self.assertEqual((row.get("CanonicalIsIncumbent") or "").strip().lower(), "true")

    def test_CA2_oth_primary_mirror_is_suppressed(self):
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)
        rows = [r for r in candidate_rows if (r.get("Primary ID") or "").strip() == "CA-2-OTH-primary-2026"]
        self.assertEqual(len(rows), 0, f"Expected no CA-2 OTH mirror rows, found {len(rows)}")


if __name__ == "__main__":
    unittest.main()
