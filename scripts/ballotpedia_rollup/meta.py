"""Metadata extraction helpers."""
from __future__ import annotations

import re
from pathlib import Path

from .seat import parse_seat_from_filename


def extract_title(html: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def extract_source_url(html: str) -> str | None:
    og = re.search(
        r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"',
        html,
        flags=re.IGNORECASE,
    )
    if og:
        return og.group(1).strip()
    canonical = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', html, flags=re.IGNORECASE)
    if canonical:
        return canonical.group(1).strip()
    return None


def extract_meta(html: str, source_file: Path) -> dict:
    state, district, seat = parse_seat_from_filename(source_file.name)
    return {
        "source_file": source_file.name,
        "title": extract_title(html),
        "source_url": extract_source_url(html),
        "state": state,
        "district": district,
        "seat": seat,
    }
