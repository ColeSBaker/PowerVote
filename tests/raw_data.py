"""Third-party raw captures kept locally but not distributed with the repo.

Ballotpedia page captures and Kalshi API snapshots under test_data/ are
gitignored. Tests that parse them are skipped when the directories are absent
(e.g. on a fresh clone); populate them with the scrape/fetch scripts to run them.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIRS = (
    REPO_ROOT / "test_data" / "candidates" / "ballotpedia",
    REPO_ROOT / "test_data" / "kalshi",
    REPO_ROOT / "test_data" / "kalshi_json_data",
)

requires_raw_data = unittest.skipUnless(
    all(path.is_dir() for path in RAW_DATA_DIRS),
    "needs local Ballotpedia/Kalshi raw captures under test_data/ (not distributed)",
)
