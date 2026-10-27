"""Shared parsing primitives for Kalshi Governor and Lt. Governor market indexers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from house_seat_parsing import STATE_CODES, STATE_NAMES
from ballotpedia_rollup.kalshi import odds_map_sum_status

# ---------------------------------------------------------------------------
# Party normalization
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

# Matches: GOVPARTYAK, KXGOVPARTYAK, KXGOVAK, KXLTGOVAK
_GOV_STATE_RE = re.compile(
    r"(?:KXGOVPARTY|GOVPARTY|KXGOV|KXLTGOV)([A-Z]{2})",
    re.IGNORECASE,
)
# KXCALIEUTENANTGOV -> CA, KXCALIEUTENANT -> CA
_CALI_LTGOV_RE = re.compile(
    r"^KXCALI(?:EUTENANT|LIEUTENANT)GOV",
    re.IGNORECASE,
)


def extract_state_from_ticker(ticker: str) -> str | None:
    """Return 2-letter state code from a GOV/LTGOV ticker, or None."""
    m = _GOV_STATE_RE.search(ticker.upper())
    if m:
        candidate = m.group(1).upper()
        if candidate in STATE_CODES:
            return candidate
    return None


def extract_state_from_cali_ticker(ticker: str) -> str | None:
    """Return 'CA' if this is a KXCALIEUTENANTGOV ticker, else None."""
    if _CALI_LTGOV_RE.match(ticker):
        return "CA"
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
    """Return 4-digit year from ticker (e.g. -26- → 2026), or None."""
    for text in (ticker, *extra_texts):
        m = _CYCLE_YEAR_RE.search(text)
        if m:
            return 2000 + int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Party from ticker suffix
# ---------------------------------------------------------------------------

# GOVPARTYAL-26-D  or KXLTGOVGA-26-DEM  or KXLTGOVGA-26-GOP
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
    """Extract party from NOM{R|D} embedded in ticker."""
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
# Advance-count extraction (top-two / top-four primaries)
# ---------------------------------------------------------------------------

_TOP_FOUR_RE = re.compile(r"top.four|top-4\b|four\s+candidates?\s+advance", re.IGNORECASE)
_TOP_TWO_RE  = re.compile(r"top.two|top-2\b|top\s+2\s+primary|two\s+candidates?\s+advance", re.IGNORECASE)
_ADVANCE_RE  = re.compile(r"\badvances?\b", re.IGNORECASE)


def extract_advance_count(rules: str, title: str = "") -> int:
    """Return how many candidates advance from this primary.

    4  → top-four primary (e.g. AK)
    2  → top-two primary, or any market with generic 'advance' language
    1  → binary partisan primary (one winner)
    """
    combined = f"{rules} {title}"
    if _TOP_FOUR_RE.search(combined):
        return 4
    if _TOP_TWO_RE.search(combined):
        return 2
    if _ADVANCE_RE.search(combined):
        return 2  # conservative: generic "advance" implies multi-winner
    return 1


# ---------------------------------------------------------------------------
# Party-combo market detection (e.g. KXGOVCAPRIMARYPARTY: "2 Democrats", "1D1R")
# ---------------------------------------------------------------------------

_PARTY_COMBO_RE = re.compile(r"^\d+\s+(democrat|republican)", re.IGNORECASE)


def is_primary_party_combo(entity_name: str) -> bool:
    """Return True for party-outcome combo markets ('2 Democrats', '1 Democrat, 1 Republican').

    These are distinct from individual candidate markets — they have no specific
    candidate and instead describe which party combination advances.
    """
    return bool(_PARTY_COMBO_RE.match(entity_name or ""))


# ---------------------------------------------------------------------------
# Advance sum check (integrity helper for multi-winner primaries)
# ---------------------------------------------------------------------------

def advance_sum_check(
    odds_map: dict[str, float],
    advance_count: int,
) -> tuple[float, str]:
    """Check that the sum of yes_prices (in %) ≈ advance_count × 100, ±20% per slot.

    Reuses the existing odds_map_sum_status function with parameterized bounds.

    Expected ranges:
        advance_count=1  →  [80, 120]   (±20%)
        advance_count=2  →  [160, 240]  (±20% = ±40)
        advance_count=4  →  [320, 480]  (±20% = ±80)

    Returns (observed_sum, status) where status is one of:
        'ok'                   — sum is in the expected range
        'out_of_band'          — sum deviates beyond tolerance
        'insufficient_entries' — fewer than 2 candidates
    """
    expected = advance_count * 100.0
    tolerance = advance_count * 20.0
    return odds_map_sum_status(
        odds_map,
        min_sum=expected - tolerance,
        max_sum=expected + tolerance,
    )


# ---------------------------------------------------------------------------
# Market type inference
# ---------------------------------------------------------------------------

_PARTY_TICKER_PATTERNS = re.compile(
    r"(?:GOVPARTY|KXGOVPARTY|KXLTGOVPARTY)", re.IGNORECASE
)
_PARTY_TITLE_RE = re.compile(r"\bwhich\s+party\b", re.IGNORECASE)


def infer_market_type(
    ticker: str,
    title: str = "",
    round_name: str = "",
    rules: str = "",
    entity_name: str = "",
) -> str:
    """Return the market type string for a Kalshi governor/ltgov market.

    Possible return values:
        'party_winner'       — party-level outcome (e.g. which party wins)
        'primary_party_combo' — multi-party advance combo (e.g. '2 Democrats advance')
        'candidate_advance'  — individual candidate advancing from top-two/top-four primary
        'candidate_nominee'  — individual candidate winning a binary partisan primary
        'candidate_winner'   — individual candidate winning the general election
    """
    if _PARTY_TICKER_PATTERNS.search(ticker):
        return "party_winner"
    if _PARTY_TITLE_RE.search(title):
        return "party_winner"
    if is_primary_party_combo(entity_name):
        return "primary_party_combo"
    effective_round = round_name or infer_round(ticker, title)
    if effective_round == "primary":
        if extract_advance_count(rules, title) > 1:
            return "candidate_advance"
        return "candidate_nominee"
    return "candidate_winner"


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


# ---------------------------------------------------------------------------
# Non-seat / meta market exclusion
# ---------------------------------------------------------------------------

_NON_SEAT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^KXCLOSEST",           re.IGNORECASE),
    re.compile(r"^KXDEMSWING",          re.IGNORECASE),
    re.compile(r"^KXCOLOMBIA",          re.IGNORECASE),
    re.compile(r"GOV\w*WINS\b",         re.IGNORECASE),
    re.compile(r"GOVSWEEP",             re.IGNORECASE),
    # NOTE: KXGA1ROUND is intentionally NOT listed here — the ltgov indexer
    # handles it explicitly in gate 2 so it is recorded in excluded_markets.
]


def is_non_seat_market(ticker: str, title: str = "") -> bool:
    """Return True for meta/portfolio/non-US markets that should be excluded."""
    for pat in _NON_SEAT_PATTERNS:
        if pat.search(ticker):
            return True
    return False


# ---------------------------------------------------------------------------
# LTGOV detection
# ---------------------------------------------------------------------------

_LTGOV_TICKER_RE = re.compile(
    r"(?:KXLTGOV|KXCALI(?:EUTENANT|LIEUTENANT)GOV)",
    re.IGNORECASE,
)
_LTGOV_TEXT_RE = re.compile(
    r"lt\.?\s*gov|lieutenant\s+governor",
    re.IGNORECASE,
)


def is_ltgov_market(ticker: str, title: str = "", rules: str = "") -> bool:
    """Return True if this market is about a Lt. Governor seat."""
    if _LTGOV_TICKER_RE.search(ticker):
        return True
    if _LTGOV_TEXT_RE.search(title):
        return True
    if _LTGOV_TEXT_RE.search(rules):
        return True
    return False
