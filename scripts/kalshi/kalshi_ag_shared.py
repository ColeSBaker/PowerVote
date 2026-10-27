"""Shared parsing primitives for Kalshi Attorney General market indexers."""
from __future__ import annotations

import re
from typing import Any

from house_seat_parsing import STATE_CODES, STATE_NAMES

# ---------------------------------------------------------------------------
# Party normalization (shared with gov)
# ---------------------------------------------------------------------------

_PARTY_MAP: dict[str, str] = {
    "D": "D",
    "R": "R",
    "DEM": "D",
    "GOP": "R",
    "DEMOCRAT": "D",
    "DEMOCRATIC": "D",
    "REPUBLICAN": "R",
}


def normalize_party(raw: str | None) -> str | None:
    """Map any raw party token to 'D' or 'R', or None if unrecognized."""
    if not raw:
        return None
    return _PARTY_MAP.get(str(raw).strip().upper())


# ---------------------------------------------------------------------------
# State extraction from ticker
# ---------------------------------------------------------------------------

# Matches: KXATTYGEN{STATE} — e.g. KXATTYGENAR, KXATTYGENFL
_AG_STATE_RE = re.compile(
    r"KXATTYGEN([A-Z]{2})",
    re.IGNORECASE,
)
# Matches: KXAGNOM{STATE}{PARTY} — e.g. KXAGNOMAZR, KXAGNOMGAD
_AG_NOM_STATE_PARTY_RE = re.compile(
    r"KXAGNOM([A-Z]{2})([DR])",
    re.IGNORECASE,
)
# Matches reversed: KXAGNOM{PARTY}{STATE} — e.g. KXAGNOMROK (R + OK)
_AG_NOM_PARTY_STATE_RE = re.compile(
    r"KXAGNOM([DR])([A-Z]{2})",
    re.IGNORECASE,
)


def extract_state_from_ticker(ticker: str) -> str | None:
    """Return 2-letter state code from an AG ticker, or None."""
    upper = ticker.upper()
    m = _AG_STATE_RE.search(upper)
    if m:
        candidate = m.group(1).upper()
        if candidate in STATE_CODES:
            return candidate
    # Try {STATE}{PARTY} first (most common: KXAGNOMAZR -> AZ)
    m = _AG_NOM_STATE_PARTY_RE.search(upper)
    if m:
        candidate = m.group(1).upper()
        if candidate in STATE_CODES:
            return candidate
    # Try {PARTY}{STATE} fallback (e.g. KXAGNOMROK -> OK)
    m = _AG_NOM_PARTY_STATE_RE.search(upper)
    if m:
        candidate = m.group(2).upper()
        if candidate in STATE_CODES:
            return candidate
    return None


# Build state-name alternation for title-based fallback
_STATE_NAME_ALTERNATION = "|".join(
    re.escape(name) for name in sorted(STATE_NAMES, key=len, reverse=True)
)
_TITLE_STATE_RE = re.compile(
    r"\bin\s+(?:the\s+)?(" + _STATE_NAME_ALTERNATION + r")\b",
    re.IGNORECASE,
)


def extract_state_from_title(title: str) -> str | None:
    """Fallback: scan title for 'in {State Name}' and return state code."""
    m = _TITLE_STATE_RE.search(title)
    if m:
        return STATE_NAMES.get(m.group(1).lower())
    return None


# ---------------------------------------------------------------------------
# Cycle year extraction
# ---------------------------------------------------------------------------

# Matches -26-, -26NOV03-, -26JUN02-, etc.
_CYCLE_YEAR_RE = re.compile(r"-(\d{2})(?:[A-Z]{3}\d{2})?(?:-|$)", re.IGNORECASE)


def extract_cycle_year(ticker: str, *extra_texts: str) -> int | None:
    """Return 4-digit year from ticker (e.g. -26- -> 2026), or None."""
    for text in (ticker, *extra_texts):
        m = _CYCLE_YEAR_RE.search(text)
        if m:
            return 2000 + int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Party from ticker suffix
# ---------------------------------------------------------------------------

# KXATTYGENAR-26-R or KXATTYGENAR-26-D or KXATTYGENAR-26-DEM
_PARTY_SUFFIX_RE = re.compile(r"-(D|R|DEM|GOP)$", re.IGNORECASE)


def extract_party_suffix(ticker: str) -> str | None:
    """Extract party from trailing -D/-R/-DEM/-GOP suffix."""
    m = _PARTY_SUFFIX_RE.search(ticker)
    return normalize_party(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Party from NOM{R|D} in ticker (nomination markets)
# ---------------------------------------------------------------------------

_NOM_PARTY_RE = re.compile(r"NOM([RD])\b", re.IGNORECASE)


def extract_nom_party(ticker: str) -> str | None:
    """Extract party from KXAGNOM tickers or generic NOM{R|D} patterns.

    Handles both conventions:
    - KXAGNOM{STATE}{PARTY}: KXAGNOMAZR -> R (state=AZ, party=R)
    - KXAGNOM{PARTY}{STATE}: KXAGNOMROK -> R (party=R, state=OK)
    """
    upper = ticker.upper()
    # Try {STATE}{PARTY}: 3 chars after KXAGNOM, party is last
    m = _AG_NOM_STATE_PARTY_RE.search(upper)
    if m:
        state_candidate = m.group(1).upper()
        if state_candidate in STATE_CODES:
            return normalize_party(m.group(2))
    # Try {PARTY}{STATE}: party is first char after KXAGNOM
    m = _AG_NOM_PARTY_STATE_RE.search(upper)
    if m:
        state_candidate = m.group(2).upper()
        if state_candidate in STATE_CODES:
            return normalize_party(m.group(1))
    # Generic NOM{R|D} fallback
    m = _NOM_PARTY_RE.search(ticker)
    return normalize_party(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Party from subtitle / title text
# ---------------------------------------------------------------------------

_SUBTITLE_PARTY_RE = re.compile(r"::\s*(Republican|Democrat)", re.IGNORECASE)
_TITLE_PARTY_RE = re.compile(
    r"\b(Democratic|Democrat|Republican)\s+party\b", re.IGNORECASE
)


def extract_party_from_subtitle(subtitle: str) -> str | None:
    """Extract party from ':: Republican' or ':: Democrat' subtitle."""
    m = _SUBTITLE_PARTY_RE.search(subtitle)
    if not m:
        return None
    return normalize_party(m.group(1))


def extract_party_from_title(title: str) -> str | None:
    """Extract party from 'Democratic party' / 'Republican party' in title."""
    m = _TITLE_PARTY_RE.search(title)
    if not m:
        return None
    raw = m.group(1).upper()
    return "D" if raw.startswith("DEM") else "R"


# ---------------------------------------------------------------------------
# Round inference
# ---------------------------------------------------------------------------

def infer_round(ticker: str, title: str = "", rules: str = "") -> str:
    """Return 'primary', 'runoff', or 'general'."""
    combined = f"{ticker} {title} {rules}".upper()
    if "RUNOFF" in combined or "SECOND ROUND" in combined or "2ND ROUND" in combined:
        return "runoff"
    if "NOM" in ticker.upper() or "PRIMARY" in ticker.upper():
        return "primary"
    if re.search(r"\b(NOMINEE|NOMINATION|PRIMARY)\b", combined):
        return "primary"
    return "general"


# ---------------------------------------------------------------------------
# Market type inference
# ---------------------------------------------------------------------------

_PARTY_TITLE_RE = re.compile(r"\bwhich\s+party\b", re.IGNORECASE)
# AG titles use "Will the {Party} party win the Attorney General race"
_PARTY_WIN_TITLE_RE = re.compile(
    r"\bwill\s+the\s+(?:Republican|Democratic|Democrat)\s+party\s+win\b",
    re.IGNORECASE,
)


def infer_market_type(ticker: str, title: str = "", round_name: str = "") -> str:
    """Return 'party_winner', 'candidate_nominee', or 'candidate_winner'."""
    if _PARTY_TITLE_RE.search(title):
        return "party_winner"
    if _PARTY_WIN_TITLE_RE.search(title):
        return "party_winner"
    effective_round = round_name or infer_round(ticker, title)
    if effective_round == "primary":
        return "candidate_nominee"
    return "candidate_winner"


# ---------------------------------------------------------------------------
# AG market detection
# ---------------------------------------------------------------------------

# AG ticker positive-match prefixes
_AG_PREFIXES = ("KXATTYGEN", "KXAGNOM")

# Regex to detect a title mentioning "attorney general"
_AG_TITLE_RE = re.compile(r"\battorney\s+general\b", re.IGNORECASE)


def is_ag_market(ticker: str, title: str = "", rules: str = "") -> bool:
    """Return True if this market belongs to a US Attorney General race."""
    ticker_upper = ticker.upper()
    for prefix in _AG_PREFIXES:
        if ticker_upper.startswith(prefix):
            return True
    if _AG_TITLE_RE.search(title):
        return True
    if _AG_TITLE_RE.search(rules):
        return True
    return False


# ---------------------------------------------------------------------------
# Non-seat / meta market exclusion
# ---------------------------------------------------------------------------

_NON_SEAT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^KXCLOSEST", re.IGNORECASE),
    re.compile(r"AGSWEEP", re.IGNORECASE),
    re.compile(r"ATTYGEN\w*WINS\b", re.IGNORECASE),
]


def is_non_seat_market(ticker: str, title: str = "") -> bool:
    """Return True for meta/portfolio/non-US markets that should be excluded."""
    for pat in _NON_SEAT_PATTERNS:
        if pat.search(ticker):
            return True
    return False


# ---------------------------------------------------------------------------
# Finish-position market exclusion
# ---------------------------------------------------------------------------

_FINISH_POS_TICKER_RE = re.compile(r"PRIMARY\d+(?:ST|ND|RD|TH)", re.IGNORECASE)
_FINISH_POS_TITLE_RE = re.compile(r"\bfinish\s+\d+(?:st|nd|rd|th)\b", re.IGNORECASE)


def is_finish_position_market(ticker: str, title: str = "") -> bool:
    """Return True for 'finish 1st in primary' style markets (not nominations)."""
    return bool(
        _FINISH_POS_TICKER_RE.search(ticker) or _FINISH_POS_TITLE_RE.search(title)
    )
