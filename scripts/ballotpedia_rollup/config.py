"""Configuration defaults for Ballotpedia rollup parsing."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Election cycle year — override via POWERVOTE_CYCLE_YEAR env var for future cycles.
ELECTION_CYCLE_YEAR: int = int(os.environ.get("POWERVOTE_CYCLE_YEAR", "2026"))
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "raw" / "ballotpedia_house_raw"
DEFAULT_OUTPUT_GENERAL_JSON = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-general-election-rollup.json"
DEFAULT_OUTPUT_PRIMARY_JSON = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.json"
DEFAULT_OUTPUT_RUNOFF_JSON = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-runoff-election-rollup.json"
DEFAULT_OUTPUT_GENERAL_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-general-election-rollup.csv"
DEFAULT_OUTPUT_PRIMARY_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.csv"
DEFAULT_OUTPUT_RUNOFF_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-runoff-election-rollup.csv"
DEFAULT_OUTPUT_GENERAL_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-general-election-rollup.jsonl"
DEFAULT_OUTPUT_PRIMARY_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-election-rollup.jsonl"
DEFAULT_OUTPUT_RUNOFF_FILE = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-runoff-election-rollup.jsonl"
DEFAULT_OUTPUT_INCUMBENT_DEPARTURES_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-incumbent-departures.csv"
DEFAULT_OUTPUT_FEC_UNMATCHED_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-fec-unmatched.csv"
DEFAULT_OUTPUT_FEC_MATCH_AUDIT_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-fec-match-audit.csv"
DEFAULT_OUTPUT_KALSHI_ROLLUP_JOIN_AUDIT_CSV = REPO_ROOT / "apps" / "web" / "data" / "kalshi-rollup-join-audit.csv"
DEFAULT_OUTPUT_BALLOTPEDIA_KALSHI_UNMATCHED_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-kalshi-unmatched-candidates.csv"
DEFAULT_OUTPUT_HISTORICAL_VOTE_TOTAL_VIOLATIONS_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-historical-vote-total-violations.csv"
DEFAULT_OUTPUT_PRIMARY_KALSHI_JOIN_ANOMALIES_CSV = REPO_ROOT / "apps" / "web" / "data" / "ballotpedia-primary-kalshi-join-anomalies.csv"
STATE_PRIMARY_RULES_JSON = REPO_ROOT / "apps" / "web" / "data" / "state-primary-rules.json"
DEFAULT_FEC_CANDIDATE_SUMMARY_FILE = REPO_ROOT / "test_data" / "candidates" / "candidate_summary_2026.csv"
DEFAULT_PARSE_CACHE_FILE = REPO_ROOT / ".cache" / "ballotpedia-rollup-parse-cache.json"


def display_path(path: Path | str) -> str:
    """Render a path for output metadata: repo-relative POSIX, never absolute.

    Paths outside the repo (e.g. the sibling ../kalshi/data workspace) become
    ../-relative so published snapshots don't embed machine-specific paths.
    """
    resolved = Path(path).resolve()
    try:
        return Path(os.path.relpath(resolved, REPO_ROOT)).as_posix()
    except ValueError:  # different drive on Windows
        return resolved.name
