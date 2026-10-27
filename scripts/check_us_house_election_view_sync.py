#!/usr/bin/env python3
"""Flag election-view builder changes that are not paired with UI/review updates."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = "scripts/build_us_house_election_view.py"
EXPECTED_COMPANION_FILES = {
    "apps/web/congressional-map.js",
    "README.md",
    "docs/pipeline-reference.md",
}


def run_git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def collect_changed_files() -> set[str]:
    changed = set(run_git("diff", "--name-only"))
    changed.update(run_git("diff", "--cached", "--name-only"))
    if changed:
        return changed

    try:
        changed.update(run_git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"))
    except subprocess.CalledProcessError:
        return set()
    return changed


def main() -> int:
    changed_files = collect_changed_files()
    if BUILDER not in changed_files:
        print("No election-view builder change detected.")
        return 0

    if EXPECTED_COMPANION_FILES & changed_files:
        touched = ", ".join(sorted(EXPECTED_COMPANION_FILES & changed_files))
        print(f"Election-view builder change is paired with companion update(s): {touched}")
        return 0

    expected = ", ".join(sorted(EXPECTED_COMPANION_FILES))
    print(
        "Detected a change to scripts/build_us_house_election_view.py without a matching UI/review update. "
        f"Also touch one of: {expected}.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
