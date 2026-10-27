"""House-specific Ballotpedia raw scrape discovery and orchestration."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urljoin

from ballotpedia_rollup.scrape_shared import (
    FetchFn,
    LoggerFn,
    ScrapeConfig,
    ScrapeSummary,
    SleepFn,
    get_or_fetch,
    soup_from_html,
)
from ballotpedia_rollup.config import ELECTION_CYCLE_YEAR
from ballotpedia_rollup.states import STATE_ABBR

HOUSE_BASE_URL = "https://ballotpedia.org"
HOUSE_NATIONAL_URL = f"{HOUSE_BASE_URL}/United_States_House_of_Representatives_elections,_{ELECTION_CYCLE_YEAR}"
HOUSE_DEFAULT_OUTDIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "ballotpedia_house_raw"


def default_house_config(**kwargs: object) -> ScrapeConfig:
    params = {
        "base_url": HOUSE_BASE_URL,
        "national_url": HOUSE_NATIONAL_URL,
        "outdir": HOUSE_DEFAULT_OUTDIR,
    }
    params.update(kwargs)
    return ScrapeConfig(
        **params,
    )


def discover_state_links(national_html: str, *, base_url: str = HOUSE_BASE_URL) -> dict[str, str]:
    soup = soup_from_html(national_html)
    state_links: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        decoded = unquote(href)
        if not decoded.startswith("/United_States_House_of_Representatives_"):
            continue
        if not decoded.endswith(f",_{ELECTION_CYCLE_YEAR}"):
            continue
        match = re.match(rf"^/United_States_House_of_Representatives_election[s]?_in_(.+),_{ELECTION_CYCLE_YEAR}$", decoded)
        if not match:
            continue
        state_name = match.group(1).replace("_", " ")
        if state_name in STATE_ABBR:
            state_links[state_name] = urljoin(base_url, href)
    return dict(sorted(state_links.items()))


def discover_seat_links(state_html: str, state_name: str, *, base_url: str = HOUSE_BASE_URL) -> dict[str, str]:
    soup = soup_from_html(state_html)
    seat_links: dict[str, str] = {}
    state_slug = state_name.replace(" ", "_")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if not href.startswith("/") or "Congressional_District_election" not in href:
            continue
        decoded = unquote(href)
        if state_slug not in decoded or f"Congressional_District_election,_{ELECTION_CYCLE_YEAR}" not in decoded:
            continue
        if f"At-large_Congressional_District_election,_{ELECTION_CYCLE_YEAR}" in decoded:
            seat_links["AL"] = urljoin(base_url, href)
            continue
        match = re.search(rf"_([0-9]+)(?:st|nd|rd|th)_Congressional_District_election,_{ELECTION_CYCLE_YEAR}$", decoded)
        if match:
            seat_links[match.group(1)] = urljoin(base_url, href)

    def _sort_key(seat: str) -> tuple[int, int]:
        return (0, 0) if seat == "AL" else (1, int(seat))

    return dict(sorted(seat_links.items(), key=lambda item: _sort_key(item[0])))


def build_house_download_plan(
    national_html: str,
    state_html_by_name: dict[str, str],
    *,
    base_url: str = HOUSE_BASE_URL,
) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = [("National.txt", HOUSE_NATIONAL_URL)]
    state_links = discover_state_links(national_html, base_url=base_url)
    for state_name, state_url in state_links.items():
        abbr = STATE_ABBR[state_name]
        plan.append((f"{abbr}.txt", state_url))
        state_html = state_html_by_name.get(state_name, "")
        if not state_html:
            continue
        seat_links = discover_seat_links(state_html, state_name, base_url=base_url)
        for seat, seat_url in seat_links.items():
            plan.append((f"{abbr}-{seat}.txt", seat_url))
    return plan


def run_house_scrape(
    config: ScrapeConfig | None = None,
    *,
    fetcher: FetchFn | None = None,
    sleep_fn: SleepFn | None = None,
    logger: LoggerFn = print,
) -> ScrapeSummary:
    active_config = config or default_house_config()
    active_config.outdir.mkdir(parents=True, exist_ok=True)
    fetcher_fn = fetcher if fetcher is not None else None
    sleep_impl = sleep_fn if sleep_fn is not None else None

    def _get(url: str, filename: str) -> tuple[str, str]:
        kwargs: dict[str, object] = {}
        if fetcher_fn is not None:
            kwargs["fetcher"] = fetcher_fn
        if sleep_impl is not None:
            kwargs["sleep_fn"] = sleep_impl
        return get_or_fetch(config=active_config, url=url, filename=filename, logger=logger, **kwargs)

    national_html, national_source = _get(active_config.national_url, "National.txt")
    state_links = discover_state_links(national_html, base_url=active_config.base_url)
    state_count = 0
    seat_count = 0
    cache_count = 1 if national_source == "cache" else 0
    write_count = 1 if national_source == "write" else 0

    for state_name, state_url in state_links.items():
        abbr = STATE_ABBR[state_name]
        logger(f"\nState: {state_name} ({abbr})")
        state_html, state_source = _get(state_url, f"{abbr}.txt")
        state_count += 1
        cache_count += 1 if state_source == "cache" else 0
        write_count += 1 if state_source == "write" else 0
        seat_links = discover_seat_links(state_html, state_name, base_url=active_config.base_url)
        logger(f"  Found {len(seat_links)} seats")
        for seat, seat_url in seat_links.items():
            _, seat_source = _get(seat_url, f"{abbr}-{seat}.txt")
            seat_count += 1
            cache_count += 1 if seat_source == "cache" else 0
            write_count += 1 if seat_source == "write" else 0

    return ScrapeSummary(
        office="us_house",
        outdir=active_config.outdir,
        national_pages=1,
        state_pages=state_count,
        seat_pages=seat_count,
        files_cached=cache_count,
        files_written=write_count,
    )
