"""Governor and lieutenant governor Ballotpedia raw scrape discovery and orchestration."""
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

GOVERNOR_BASE_URL = "https://ballotpedia.org"
GOVERNOR_NATIONAL_URL = f"{GOVERNOR_BASE_URL}/Gubernatorial_elections,_{ELECTION_CYCLE_YEAR}"
GOVERNOR_DEFAULT_OUTDIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "ballotpedia_governor_raw"


def default_governor_config(**kwargs: object) -> ScrapeConfig:
    params = {
        "base_url": GOVERNOR_BASE_URL,
        "national_url": GOVERNOR_NATIONAL_URL,
        "outdir": GOVERNOR_DEFAULT_OUTDIR,
    }
    params.update(kwargs)
    return ScrapeConfig(
        **params,
    )


def _state_abbr_from_slug(slug: str) -> tuple[str, str] | None:
    state_name = slug.replace("_", " ")
    abbr = STATE_ABBR.get(state_name)
    if not abbr:
        return None
    return state_name, abbr


def discover_governor_links(national_html: str, *, base_url: str = GOVERNOR_BASE_URL) -> dict[str, dict[str, str]]:
    soup = soup_from_html(national_html)
    result: dict[str, dict[str, str]] = {}
    governor_pattern = re.compile(rf"^/(.+)_gubernatorial_election,_{ELECTION_CYCLE_YEAR}$")
    combined_pattern = re.compile(rf"^/(.+)_gubernatorial_and_lieutenant_gubernatorial_election,_{ELECTION_CYCLE_YEAR}$")

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        decoded = unquote(href)

        combined_match = combined_pattern.match(decoded)
        if combined_match:
            parsed = _state_abbr_from_slug(combined_match.group(1))
            if not parsed:
                continue
            state_name, abbr = parsed
            result[abbr] = {
                "kind": "combined",
                "state": state_name,
                "url": urljoin(base_url, href),
            }
            continue

        governor_match = governor_pattern.match(decoded)
        if not governor_match:
            continue

        parsed = _state_abbr_from_slug(governor_match.group(1))
        if not parsed:
            continue
        state_name, abbr = parsed
        result[abbr] = {
            "kind": "governor",
            "state": state_name,
            "url": urljoin(base_url, href),
        }

    return dict(sorted(result.items(), key=lambda item: item[0]))


def discover_ltgovernor_links(national_html: str, *, base_url: str = GOVERNOR_BASE_URL) -> dict[str, dict[str, str]]:
    soup = soup_from_html(national_html)
    result: dict[str, dict[str, str]] = {}
    ltgov_pattern = re.compile(rf"^/(.+)_lieutenant_gubernatorial_election,_{ELECTION_CYCLE_YEAR}$")
    combined_pattern = re.compile(rf"^/(.+)_gubernatorial_and_lieutenant_gubernatorial_election,_{ELECTION_CYCLE_YEAR}$")

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        decoded = unquote(href)

        combined_match = combined_pattern.match(decoded)
        if combined_match:
            parsed = _state_abbr_from_slug(combined_match.group(1))
            if not parsed:
                continue
            state_name, abbr = parsed
            result[abbr] = {
                "kind": "combined",
                "state": state_name,
                "url": urljoin(base_url, href),
            }
            continue

        ltgov_match = ltgov_pattern.match(decoded)
        if not ltgov_match:
            continue

        parsed = _state_abbr_from_slug(ltgov_match.group(1))
        if not parsed:
            continue
        state_name, abbr = parsed
        result[abbr] = {
            "kind": "lt_governor",
            "state": state_name,
            "url": urljoin(base_url, href),
        }

    return dict(sorted(result.items(), key=lambda item: item[0]))


def build_governor_download_plan(national_html: str, *, base_url: str = GOVERNOR_BASE_URL) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = [("National.txt", GOVERNOR_NATIONAL_URL)]
    governor_links = discover_governor_links(national_html, base_url=base_url)
    ltgov_links = discover_ltgovernor_links(national_html, base_url=base_url)

    for abbr in sorted(set(governor_links) | set(ltgov_links)):
        if abbr in governor_links:
            plan.append((f"{abbr}-GOV.txt", governor_links[abbr]["url"]))
        if abbr in ltgov_links:
            plan.append((f"{abbr}-LTGOV.txt", ltgov_links[abbr]["url"]))
    return plan


def run_governor_scrape(
    config: ScrapeConfig | None = None,
    *,
    fetcher: FetchFn | None = None,
    sleep_fn: SleepFn | None = None,
    logger: LoggerFn = print,
) -> ScrapeSummary:
    active_config = config or default_governor_config()
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
    plan = build_governor_download_plan(national_html, base_url=active_config.base_url)
    cache_count = 1 if national_source == "cache" else 0
    write_count = 1 if national_source == "write" else 0
    state_codes: set[str] = set()
    seat_pages = 0

    for filename, url in plan[1:]:
        logger(f"\nFetching {filename}")
        _, source = _get(url, filename)
        seat_pages += 1
        state_codes.add(filename.split("-", 1)[0])
        cache_count += 1 if source == "cache" else 0
        write_count += 1 if source == "write" else 0

    return ScrapeSummary(
        office="state_governor",
        outdir=active_config.outdir,
        national_pages=1,
        state_pages=len(state_codes),
        seat_pages=seat_pages,
        files_cached=cache_count,
        files_written=write_count,
    )
