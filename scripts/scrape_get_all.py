#!/usr/bin/env python3
"""Backward-compatible alias for House raw Ballotpedia scraper."""
from __future__ import annotations

from scrape_ballotpedia_house_raw import main


if __name__ == "__main__":
    raise SystemExit(main())

