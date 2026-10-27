import csv
import os
import unittest
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_ROLLUP_PATH = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.csv"
CANDIDATE_ROLLUP_PATH = Path(os.environ.get("POWERVOTE_CANDIDATE_ROLLUP_CSV", str(REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-2026.csv")))

ALLOWED_COMPLETED_STATUSES = {"general (nominated)", "runoff", "eliminated"}


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


def _is_primary_complete(primary_row: dict[str, str]) -> bool:
    status = (primary_row.get("status") or "").strip().lower()
    if status == "complete":
        return True
    primary_vote_total = _parse_float(primary_row.get("primary_vote_total"))
    return bool(primary_vote_total is not None and primary_vote_total > 0)


class CandidatePrimaryStatusConsistencyTests(unittest.TestCase):
    def test_completed_primaries_have_valid_candidate_statuses(self):
        primary_rows = _load_csv(PRIMARY_ROLLUP_PATH)
        candidate_rows = _load_csv(CANDIDATE_ROLLUP_PATH)

        complete_primary_ids = {
            (row.get("primary_id") or "").strip(): row
            for row in primary_rows
            if (row.get("primary_id") or "").strip() and _is_primary_complete(row)
        }

        candidates_by_primary_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in candidate_rows:
            primary_id = (row.get("Primary ID") or "").strip()
            if primary_id:
                candidates_by_primary_id[primary_id].append(row)

        failures: list[str] = []

        for primary_id, primary_row in sorted(complete_primary_ids.items()):
            candidates = candidates_by_primary_id.get(primary_id, [])
            if not candidates:
                continue

            nominated_count = 0
            runoff_count = 0

            for candidate in candidates:
                candidate_name = (candidate.get("BallotpediaName") or "").strip()
                status = (candidate.get("Status") or "").strip()
                votes = (candidate.get("Votes in Primary") or "").strip()
                runoff_id = (candidate.get("RunoffID") or "").strip()
                row_summary = (
                    f"candidate='{candidate_name}', status='{status}', votes='{votes}', runoff_id='{runoff_id}'"
                )

                if status == "primary":
                    failures.append(
                        f"{primary_id}: completed primary has disallowed status 'primary' -> {row_summary}"
                    )

                if status not in ALLOWED_COMPLETED_STATUSES:
                    failures.append(
                        f"{primary_id}: completed primary has invalid status '{status}' -> {row_summary}; "
                        f"allowed={sorted(ALLOWED_COMPLETED_STATUSES)}"
                    )

                if status == "general (nominated)":
                    nominated_count += 1
                if status == "runoff":
                    runoff_count += 1

            if nominated_count > 1:
                failures.append(
                    f"{primary_id}: completed primary has {nominated_count} candidates with "
                    "status 'general (nominated)' (max 1)."
                )

            if runoff_count > 2:
                failures.append(
                    f"{primary_id}: completed primary has {runoff_count} candidates with "
                    "status 'runoff' (max 2)."
                )

        if failures:
            details = "\n".join(f"- {entry}" for entry in failures)
            self.fail(
                "Completed primary candidate status consistency failures:\n"
                f"{details}\n"
                f"Checked {len(complete_primary_ids)} completed primaries."
            )


if __name__ == "__main__":
    unittest.main()
