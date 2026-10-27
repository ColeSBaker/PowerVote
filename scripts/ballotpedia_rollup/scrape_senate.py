"""Senate-specific Ballotpedia raw scrape discovery and orchestration."""
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

SENATE_BASE_URL = "https://ballotpedia.org"
SENATE_NATIONAL_URL = f"{SENATE_BASE_URL}/United_States_Senate_elections,_{ELECTION_CYCLE_YEAR}"
SENATE_DEFAULT_OUTDIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "ballotpedia_senate_raw"


def default_senate_config(**kwargs: object) -> ScrapeConfig:
    params = {
        "base_url": SENATE_BASE_URL,
        "national_url": SENATE_NATIONAL_URL,
        "outdir": SENATE_DEFAULT_OUTDIR,
    }
    params.update(kwargs)
    return ScrapeConfig(
        **params,
    )


def discover_senate_links(national_html: str, *, base_url: str = SENATE_BASE_URL) -> dict[str, dict[str, str]]:
    soup = soup_from_html(national_html)
    result: dict[str, dict[str, str]] = {}
    regular_pattern = re.compile(rf"^/United_States_Senate_election_in_(.+),_{ELECTION_CYCLE_YEAR}$")
    special_pattern = re.compile(rf"^/United_States_Senate_special_election_in_(.+),_{ELECTION_CYCLE_YEAR}$")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        decoded = unquote(href)
        regular_match = regular_pattern.match(decoded)
        if regular_match:
            state_name = regular_match.group(1).replace("_", " ")
            if state_name in STATE_ABBR:
                abbr = STATE_ABBR[state_name]
                result[abbr] = {
                    "kind": "regular",
                    "state": state_name,
                    "url": urljoin(base_url, href),
                }
            continue
        special_match = special_pattern.match(decoded)
        if special_match:
            state_name = special_match.group(1).replace("_", " ")
            if state_name in STATE_ABBR:
                abbr = STATE_ABBR[state_name]
                result[f"{abbr}-SPECIAL"] = {
                    "kind": "special",
                    "state": state_name,
                    "url": urljoin(base_url, href),
                }
    return dict(sorted(result.items(), key=lambda item: item[0]))


def build_senate_download_plan(national_html: str, *, base_url: str = SENATE_BASE_URL) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = [("National.txt", SENATE_NATIONAL_URL)]
    links = discover_senate_links(national_html, base_url=base_url)
    for key, meta in links.items():
        plan.append((f"{key}.txt", meta["url"]))
    return plan


def run_senate_scrape(
    config: ScrapeConfig | None = None,
    *,
    fetcher: FetchFn | None = None,
    sleep_fn: SleepFn | None = None,
    logger: LoggerFn = print,
) -> ScrapeSummary:
    active_config = config or default_senate_config()
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
    links = discover_senate_links(national_html, base_url=active_config.base_url)
    state_pages = 0
    seat_pages = 0
    cache_count = 1 if national_source == "cache" else 0
    write_count = 1 if national_source == "write" else 0
    for key, meta in links.items():
        logger(f"\n{meta['state']} [{meta['kind']}] -> {key}.txt")
        _, source = _get(meta["url"], f"{key}.txt")
        state_pages += 1
        seat_pages += 1
        cache_count += 1 if source == "cache" else 0
        write_count += 1 if source == "write" else 0

    return ScrapeSummary(
        office="us_senate",
        outdir=active_config.outdir,
        national_pages=1,
        state_pages=state_pages,
        seat_pages=seat_pages,
        files_cached=cache_count,
        files_written=write_count,
    )
