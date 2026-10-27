"""Shared fetch/cache/retry utilities for Ballotpedia raw scrapers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Tuple
from urllib import request

from bs4 import BeautifulSoup

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )
}

DEFAULT_BAD_MARKERS = (
    "access denied",
    "forbidden",
    "temporarily unavailable",
    "too many requests",
    "rate limit",
    "attention required",
    "request blocked",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "just a moment",
    "checking your browser",
    "cloudflare",
    "automated access",
    "unusual traffic",
)


class ScrapeError(RuntimeError):
    """Base scraper error."""


class FetchExhaustedError(ScrapeError):
    """Raised when fetch retries are exhausted."""


@dataclass(frozen=True)
class RetryPolicy:
    initial_delay_seconds: float = 0.8
    max_attempts: int = 5
    backoff_multiplier: float = 2.0
    reset_delay_seconds: float = 0.0


@dataclass(frozen=True)
class ScrapeConfig:
    base_url: str
    national_url: str
    outdir: Path
    timeout_seconds: float = 30.0
    min_nonempty_chars: int = 200
    force_refresh: bool = False
    headers: Mapping[str, str] = field(default_factory=lambda: DEFAULT_HEADERS.copy())
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass(frozen=True)
class ScrapeSummary:
    office: str
    outdir: Path
    national_pages: int
    state_pages: int
    seat_pages: int
    files_cached: int
    files_written: int


FetchFn = Callable[[str, Mapping[str, str], float], Tuple[int, str]]
SleepFn = Callable[[float], None]
LoggerFn = Callable[[str], None]


def _requests_fetch(url: str, headers: Mapping[str, str], timeout_seconds: float) -> tuple[int, str]:
    req = request.Request(url, headers=dict(headers))
    with request.urlopen(req, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace")
        status = int(getattr(response, "status", 200))
    return status, body


def looks_like_rejected_or_bad_response(
    text: str,
    *,
    status_code: int | None = None,
    min_nonempty_chars: int = 200,
    bad_markers: tuple[str, ...] = DEFAULT_BAD_MARKERS,
) -> bool:
    if status_code is not None and status_code >= 400:
        return True

    stripped = text.strip()
    lowered = stripped.lower()
    if len(stripped) < min_nonempty_chars:
        return True
    if any(marker in lowered for marker in bad_markers):
        return True
    if "<html" not in lowered and "<!doctype html" not in lowered:
        return True
    return False


def fetch_with_retry(
    *,
    url: str,
    filename: str,
    timeout_seconds: float,
    retry_policy: RetryPolicy,
    headers: Mapping[str, str],
    min_nonempty_chars: int,
    fetcher: FetchFn = _requests_fetch,
    sleep_fn: SleepFn = time.sleep,
    logger: LoggerFn = print,
) -> str:
    delay = retry_policy.initial_delay_seconds
    last_error: Exception | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            logger(
                f"  [fetch attempt {attempt}/{retry_policy.max_attempts}] "
                f"{filename} (delay={delay:.1f}s)"
            )
            sleep_fn(delay)
            status_code, text = fetcher(url, headers, timeout_seconds)
            if looks_like_rejected_or_bad_response(
                text,
                status_code=status_code,
                min_nonempty_chars=min_nonempty_chars,
            ):
                raise ScrapeError(
                    "Suspicious or rejected response "
                    f"(status={status_code}, chars={len(text.strip())})"
                )
            if attempt > 1 and retry_policy.reset_delay_seconds > 0:
                sleep_fn(retry_policy.reset_delay_seconds)
            return text
        except Exception as exc:  # noqa: BLE001 - intentional to surface all retryable fetch errors.
            last_error = exc
            logger(f"  [retry] {filename}: {exc}")
            if attempt == retry_policy.max_attempts:
                break
            delay *= retry_policy.backoff_multiplier
    raise FetchExhaustedError(f"Failed to fetch {filename}: {last_error}")


def soup_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def get_or_fetch(
    *,
    config: ScrapeConfig,
    url: str,
    filename: str,
    fetcher: FetchFn = _requests_fetch,
    sleep_fn: SleepFn = time.sleep,
    logger: LoggerFn = print,
) -> tuple[str, str]:
    path = config.outdir / filename
    if path.exists() and not config.force_refresh:
        cached_text = path.read_text(encoding="utf-8")
        if not cached_text.strip():
            logger(f"  [refresh empty cache] {filename}")
        elif looks_like_rejected_or_bad_response(
            cached_text,
            min_nonempty_chars=config.min_nonempty_chars,
        ):
            logger(f"  [refresh suspicious cache] {filename}")
        else:
            logger(f"  [cache] {filename}")
            return cached_text, "cache"

    fresh = fetch_with_retry(
        url=url,
        filename=filename,
        timeout_seconds=config.timeout_seconds,
        retry_policy=config.retry_policy,
        headers=config.headers,
        min_nonempty_chars=config.min_nonempty_chars,
        fetcher=fetcher,
        sleep_fn=sleep_fn,
        logger=logger,
    )
    if not fresh.strip():
        raise ScrapeError(f"Fresh content is empty for {filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fresh, encoding="utf-8")
    return fresh, "write"
