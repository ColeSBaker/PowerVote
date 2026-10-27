"""Normalization and primitive value parsing helpers."""
from __future__ import annotations

import re

PARTY_PATTERNS: list[tuple[str, str]] = [
    ("D", r"\bdemocratic\b|\(d\)|^d$"),
    ("R", r"\brepublican\b|\(r\)|^r$"),
    ("G", r"\bgreen\b|\(g\)|^g$"),
    ("L", r"\blibertarian\b|\(l\)|^l$"),
    ("NP", r"\bnonpartisan\b|\bno party preference\b"),
    ("IND", r"\bindependent\b|\bno political party\b|\bno party affiliation\b"),
]


def norm_party(raw: str | None) -> str:
    if not raw:
        return "OTH"
    text = raw.strip().lower()
    for code, pattern in PARTY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return code
    return "OTH"


def clean_name(raw: str | None) -> str:
    if not raw:
        return ""
    value = raw.replace("✔", " ").replace("✓", " ")
    value = re.sub(r"\s+", " ", value.replace("\u2019", "'"))
    return value.strip(" -\t\n\r")


def parse_int_votes(raw: str | None) -> int | None:
    if not raw:
        return None
    match = re.search(r"\d[\d,]*", raw)
    if not match:
        return None
    return int(match.group(0).replace(",", ""))


def parse_pct(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"\d+(?:\.\d+)?", raw)
    if not match:
        return None
    return float(match.group(0))
