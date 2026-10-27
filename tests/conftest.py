"""
pytest configuration for the PowerVote test suite.

## Test data categories

Two categories of tests exist in this suite:

**Quality-gate tests** (run against live pipeline output in apps/web/data/)
  Check that the daily ETL produces output meeting quality thresholds.
  Examples: FEC match rate < 5%, Kalshi odds summing to 90-110%, vote shares ~100%.
  These tests SHOULD fail when the pipeline produces degraded output.

**Regression/contract tests** (run against frozen snapshots in test_data/rollup/)
  Pin specific behaviors against stable fixture data so daily data refreshes
  never silently break test assertions.
  Examples: parser correctness, API contract validation, specific candidate-handling rules.

## Overriding the data directory

Set POWERVOTE_DATA_DIR to redirect all rollup CSV paths in a test run:

    # Use frozen fixtures (default for regression tests):
    POWERVOTE_DATA_DIR=test_data/rollup python -m pytest tests/ -v

    # Use live pipeline output (for quality-gate CI runs):
    POWERVOTE_DATA_DIR=apps/web/data python -m pytest tests/ -v

The POWERVOTE_DATA_DIR env var is read at module import time, so it must be set
before pytest collects tests (i.e., in the environment, not via a pytest fixture).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Paths for reference in tests that need to construct fixture paths explicitly.
FROZEN_ROLLUP_DIR = REPO_ROOT / "test_data" / "rollup"
LIVE_ROLLUP_DIR = REPO_ROOT / "apps" / "web" / "data"

from ballotpedia_rollup import parser
from ballotpedia_rollup.parse_all_cache import ParseAllCache, parse_cache_copy_mode_from_env
from tests.slow_lane import is_slow_lane

# Session-level parse result caching shared across tests.
parser.parse_all = ParseAllCache(parser.parse_all, copy_mode=parse_cache_copy_mode_from_env())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark known heavy integration tests for split CI lanes."""
    mark = pytest.mark.slow_integrity
    for item in items:
        if is_slow_lane(str(item.fspath)):
            item.add_marker(mark)
