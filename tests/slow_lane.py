from __future__ import annotations

from pathlib import Path

SLOW_LANE_PATTERNS = (
    "test_ballotpedia_rollup_parser.py",
    "test_ballotpedia_rollup_split_rollups.py",
    "test_ballotpedia_kalshi_rollup_integrity.py",
    "test_candidate_rollup_kalshi_integrity.py",
    "test_ballotpedia_historical_vote_total_integrity.py",
    "test_ballotpedia_general_primary_status_buckets.py",
    "test_ballotpedia_election_date_integrity.py",
    "test_ballotpedia_fec_integrity.py",
    "test_ballotpedia_fec_unified_integrity.py",
    "test_kalshi_integrity_pipeline_checks.py",
)


def is_slow_lane(path: str | Path) -> bool:
    text = str(path)
    return any(pattern in text for pattern in SLOW_LANE_PATTERNS)
