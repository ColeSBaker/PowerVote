#!/usr/bin/env python3
"""Build Ballotpedia 2026 House general and primary rollups from raw HTML snapshots."""

from ballotpedia_rollup.cli import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli())
