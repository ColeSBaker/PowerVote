from __future__ import annotations

from dataclasses import dataclass
import re

STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
}

STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL",
    "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
    "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def build_primary_nomination_key(*, office_family: str, seat_id: str | None, cycle_year: int | None, party: str | None) -> str | None:
    if not office_family or not seat_id or cycle_year is None or not party:
        return None
    return f"{office_family}:{seat_id}:{cycle_year}:{party}"


@dataclass(frozen=True)
class USHouseParsingResult:
    state_code: str | None
    district_code: str | None
    is_at_large: bool
    party: str | None
    cycle_year: int | None

    @property
    def seat_id(self) -> str | None:
        if not self.state_code:
            return None
        if self.is_at_large:
            return f"{self.state_code}-AL"
        if self.district_code:
            return f"{self.state_code}-{self.district_code}"
        return None

    @property
    def normalized_primary_key(self) -> str | None:
        return build_primary_nomination_key(
            office_family="US-REP",
            seat_id=self.seat_id,
            cycle_year=self.cycle_year,
            party=self.party,
        )


def format_house_seat_id(state_code: str, district_code: str) -> str:
    return f"{state_code}-AL" if district_code == "AL" else f"{state_code}-{int(district_code):02d}"


def _normalize_district(raw: str | None) -> str | None:
    if not raw:
        return None
    upper = raw.upper()
    if upper == "AL":
        return "AL"
    return f"{int(upper):02d}" if upper.isdigit() else None


def _extract_state_from_text(upper: str) -> str | None:
    for state_name, code in STATE_NAMES.items():
        if state_name.upper() in upper:
            return code

    title_district_match = re.search(r"\b([A-Z]{2})[-\s]?(?:AL|\d{1,2})\b", upper)
    if title_district_match and title_district_match.group(1) in STATE_CODES:
        return title_district_match.group(1)

    for match in re.findall(r"\b([A-Z]{2})\b", upper):
        if match in STATE_CODES:
            return match
    return None


def _extract_from_structured_text(upper: str) -> tuple[str | None, str | None, bool]:
    patterns = (
        r"\bKXHOUSERACE-([A-Z]{2})(AL|\d{1,2})-\d{2}(?:-|$)",
        r"\bKX([A-Z]{2})PRIMARY-(AL|\d{1,2})([DR])\d{2}(?:-|$)",
        r"\bKX([A-Z]{2})(AL|\d{1,2})([DR])(?:-|$)",
        r"\b([A-Z]{2})-(AL|\d{1,2})\b",
        r"\b([A-Z]{2})(AL|\d{1,2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, upper)
        if match:
            state_code = match.group(1)
            district_code = _normalize_district(match.group(2))
            if state_code in STATE_CODES and district_code:
                return state_code, district_code, district_code == "AL"
    return None, None, False


def _extract_from_natural_language(upper: str) -> tuple[str | None, str | None, bool]:
    if "DISTRICT OF COLUMBIA" in upper and "AT-LARGE DISTRICT" in upper:
        return "DC", "AL", True

    match = re.search(
        r"\b([A-Z][A-Z\s]+?)'?S\s+(AT-LARGE|AT LARGE|\d{1,2})(?:ST|ND|RD|TH)?\s+(?:CONGRESSIONAL\s+)?DISTRICT\b",
        upper,
    )
    if match:
        state_name = re.sub(r"\s+", " ", match.group(1).strip().lower())
        state_code = STATE_NAMES.get(state_name)
        district_token = match.group(2)
        if state_code:
            district_code = "AL" if district_token.startswith("AT") else _normalize_district(district_token)
            if district_code:
                return state_code, district_code, district_code == "AL"

    state_code = _extract_state_from_text(upper)
    district_match = re.search(r"\b(?:DISTRICT|CD)\s*(AL|\d{1,2})\b", upper)
    if state_code and district_match:
        district_code = _normalize_district(district_match.group(1))
        if district_code:
            return state_code, district_code, district_code == "AL"

    if state_code:
        state_specific = re.search(rf"\b{state_code}[-\s]?(AL|\d{{1,2}})\b", upper)
        if state_specific:
            district_code = _normalize_district(state_specific.group(1))
            if district_code:
                return state_code, district_code, district_code == "AL"

    return state_code, None, False


def infer_us_house_parsing(
    *,
    event_ticker: str = "",
    market_ticker: str = "",
    series_ticker: str = "",
    title: str = "",
    rules_primary: str = "",
) -> USHouseParsingResult:
    texts = [event_ticker, market_ticker, series_ticker, title, rules_primary]
    uppercase_texts = [str(text or "").upper() for text in texts if str(text or "").strip()]

    state_code = None
    district_code = None
    is_at_large = False

    for upper in uppercase_texts:
        state_code, district_code, is_at_large = _extract_from_structured_text(upper)
        if state_code and (district_code or is_at_large):
            break
    else:
        combined = " ".join(uppercase_texts)
        state_code, district_code, is_at_large = _extract_from_natural_language(combined)

    combined = " ".join(uppercase_texts)
    if state_code and not district_code:
        state_code2, district_code2, is_at_large2 = _extract_from_natural_language(combined)
        state_code = state_code or state_code2
        district_code = district_code or district_code2
        is_at_large = is_at_large or is_at_large2

    if not is_at_large and re.search(r"\bAT[-\s]LARGE\b", combined) and state_code:
        district_code = "AL"
        is_at_large = True

    party = None
    primary_suffix_match = re.search(r"(?:NOM|PRIMARY)([DR])$", str(series_ticker or "").upper())
    if primary_suffix_match:
        party = primary_suffix_match.group(1)
    else:
        for upper in uppercase_texts:
            primary_match = re.search(r"(?:-|^)(?:AL|\d{1,2})([DR])(\d{2})(?:-|$)", upper)
            if primary_match:
                party = primary_match.group(1)
                break
        if not party:
            if re.search(r"\b(DEMOCRAT|DEMOCRATIC)\b", combined):
                party = "D"
            elif re.search(r"\b(REPUBLICAN|GOP)\b", combined):
                party = "R"

    cycle_year = None
    year_patterns = (
        re.compile(r"[DR](\d{2})(?:-|$)"),
        re.compile(r"-(\d{2})(?:-|$)"),
        re.compile(r"\b(20\d{2})\b"),
    )
    for upper in uppercase_texts:
        for pattern in year_patterns:
            cycle_match = pattern.search(upper)
            if cycle_match:
                value = cycle_match.group(1)
                cycle_year = int(value) if len(value) == 4 else 2000 + int(value)
                break
        if cycle_year:
            break

    return USHouseParsingResult(
        state_code=state_code,
        district_code=district_code if district_code != "AL" else None,
        is_at_large=is_at_large,
        party=party,
        cycle_year=cycle_year,
    )
