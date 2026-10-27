"""Election date extraction utilities for Ballotpedia raw pages."""
from __future__ import annotations

import os
import re
from datetime import date, datetime

MONTH_RE = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_TEXT_RE = rf"{MONTH_RE}\s+\d{{1,2}},\s+\d{{4}}"
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def _to_iso(date_text: str) -> str:
    value = date_text.replace("Sept.", "September").replace("Sep.", "September").strip()
    return datetime.strptime(value, "%B %d, %Y").date().isoformat()


def _extract_first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _to_iso(match.group("date"))


def _strip_html(value: str) -> str:
    return SPACE_RE.sub(" ", TAG_RE.sub(" ", value)).strip()


def extract_election_dates(page_html: str) -> dict[str, str]:
    """Parse key election dates from district/state pages."""
    plain_text = _strip_html(page_html)
    primary_patterns = [
        rf"\bprimary(?:\s+election)?\s*(?::|is|was|will\s+occur\s+on|on)?\s*(?P<date>{DATE_TEXT_RE})",
        rf"\bprimary\s+for\s+this\s+election\s*(?::|is|was|on)?\s*(?P<date>{DATE_TEXT_RE})",
    ]
    runoff_patterns = [
        rf"\brunoff(?:\s+election)?\s*(?::|is|was|will\s+occur\s+on|on)?\s*(?P<date>{DATE_TEXT_RE})",
    ]
    general_patterns = [
        rf"\bgeneral\s+election\s*(?::|is|was|will\s+occur\s+on|on)?\s*(?P<date>{DATE_TEXT_RE})",
    ]
    filing_patterns = [
        rf"\bfiling\s+deadline\s*(?::|is|was|on)?\s*(?P<date>{DATE_TEXT_RE})",
    ]

    primary_date = ""
    runoff_date = ""
    general_date = ""
    filing_deadline = ""
    for pattern in primary_patterns:
        primary_date = _extract_first(pattern, plain_text)
        if primary_date:
            break
    for pattern in runoff_patterns:
        runoff_date = _extract_first(pattern, plain_text)
        if runoff_date:
            break
    for pattern in general_patterns:
        general_date = _extract_first(pattern, plain_text)
        if general_date:
            break
    for pattern in filing_patterns:
        filing_deadline = _extract_first(pattern, plain_text)
        if filing_deadline:
            break

    # Fallback: infer dates from election link titles if sentence extraction failed.
    if not primary_date:
        primary_match = re.search(rf"title=\"[^\"]*\((?P<date>{DATE_TEXT_RE})\s+[^\"]*primary\)\"", page_html, flags=re.IGNORECASE)
        if primary_match:
            primary_date = _to_iso(primary_match.group("date"))
    if not runoff_date:
        runoff_match = re.search(rf"title=\"[^\"]*\((?P<date>{DATE_TEXT_RE})\s+[^\"]*runoff\)\"", page_html, flags=re.IGNORECASE)
        if runoff_match:
            runoff_date = _to_iso(runoff_match.group("date"))
    if not general_date:
        general_match = re.search(rf"title=\"[^\"]*\((?P<date>{DATE_TEXT_RE})\s+[^\"]*general\s+election\)\"", page_html, flags=re.IGNORECASE)
        if general_match:
            general_date = _to_iso(general_match.group("date"))

    return {
        "primary_date": primary_date,
        "runoff_date": runoff_date,
        "general_date": general_date,
        "filing_deadline": filing_deadline,
    }


def get_validation_date() -> date:
    override = os.environ.get("POWERVOTE_VALIDATION_DATE", "").strip()
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return date.today()


def parse_iso_date(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None
