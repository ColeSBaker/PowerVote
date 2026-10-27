#!/usr/bin/env python3
"""Fetch Kalshi election series and market data without API keys.

Writes individual JSON files for each series and market to disk so the
daily contest-index builders always have fresh price data.

Output layout:
  <series-dir>/series_{TICKER}_{CATEGORY}.json   — one file per series
  <market-dir>/market_{SERIES}_{MARKET}.json     — one file per open market
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent

SERIES_URL = "https://api.elections.kalshi.com/trade-api/v2/series?category=Elections"
MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
RATE_LIMIT_SLEEP = 0.1


def parse_args() -> argparse.Namespace:
    default_market_dir = str(WORKSPACE_ROOT / "kalshi" / "data" / "markets")
    default_series_dir = str(WORKSPACE_ROOT / "kalshi" / "data" / "series")

    parser = argparse.ArgumentParser(
        description="Fetch all Kalshi election series and open-market data to disk."
    )
    parser.add_argument(
        "--market-dir",
        default=default_market_dir,
        help="Directory for market JSON files (default: %(default)s)",
    )
    parser.add_argument(
        "--series-dir",
        default=default_series_dir,
        help="Directory for series JSON files (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP request timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of attempts per request (default: %(default)s)",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=2.0,
        help="Initial retry backoff in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--bypass-proxy-for-kalshi",
        action="store_true",
        help="Attempt a direct (no-proxy) request if the proxied request fails.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# HTTP helpers (mirrors fetch_kalshi_series.py)
# ---------------------------------------------------------------------------

def _build_direct_no_proxy_env(url: str) -> dict[str, str]:
    host = parse.urlparse(url).hostname
    if not host:
        return {}
    no_proxy_keys = ["NO_PROXY", "no_proxy"]
    updates: dict[str, str] = {}
    for key in no_proxy_keys:
        existing = os.environ.get(key, "")
        values = [item.strip() for item in existing.split(",") if item.strip()]
        if host not in values:
            values.append(host)
        updates[key] = ",".join(values)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        updates[key] = ""
    return updates


def _request_json(url: str, timeout: float, direct_mode: bool = False) -> Any:
    req = request.Request(url, method="GET", headers={"User-Agent": "PowerVote/1.0"})
    if not direct_mode:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    env_overrides = _build_direct_no_proxy_env(url)
    previous = {k: os.environ.get(k) for k in env_overrides}
    try:
        os.environ.update(env_overrides)
        opener = request.build_opener(request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _fetch_with_retry(
    url: str,
    *,
    timeout: float,
    retries: int,
    retry_delay: float,
    bypass_proxy: bool,
) -> Any:
    modes = ["proxied"]
    if bypass_proxy:
        modes.append("direct")

    last_error: Exception | None = None
    for mode in modes:
        direct_mode = mode == "direct"
        delay = retry_delay
        for attempt in range(1, retries + 1):
            try:
                return _request_json(url=url, timeout=timeout, direct_mode=direct_mode)
            except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
                last_error = err
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2

    raise last_error or RuntimeError(f"Kalshi fetch failed: {url}")


# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------

def fetch_all_markets(
    market_dir: Path,
    series_dir: Path,
    timeout: float,
    retries: int,
    retry_delay: float,
    bypass_proxy: bool,
) -> tuple[int, int]:
    """Fetch all Election series and their open markets.

    Returns (series_count, market_count).
    """
    market_dir.mkdir(parents=True, exist_ok=True)
    series_dir.mkdir(parents=True, exist_ok=True)

    kwargs = dict(timeout=timeout, retries=retries, retry_delay=retry_delay, bypass_proxy=bypass_proxy)

    print(f"Fetching election series from Kalshi …")
    all_series_data = _fetch_with_retry(SERIES_URL, **kwargs)
    series_list = all_series_data.get("series", [])
    print(f"  Found {len(series_list)} series")

    series_count = 0
    market_count = 0

    for series in series_list:
        ticker = series.get("ticker", "")
        category = series.get("category", "")
        tags = series.get("tags") or []

        if "Foreign Elections" in tags:
            print(f"  Skipping foreign election series: {ticker}")
            continue

        # Write series file (always overwrite for fresh data)
        series_filename = f"series_{ticker}_{category}.json"
        series_path = series_dir / series_filename
        series_path.write_text(json.dumps(series, indent=4), encoding="utf-8")
        series_count += 1

        # Fetch open markets for this series
        markets_url = f"{MARKETS_URL}?series_ticker={ticker}&status=open"
        try:
            markets_data = _fetch_with_retry(markets_url, **kwargs)
        except Exception as err:
            print(f"  WARNING: Failed to fetch markets for {ticker}: {err}", file=sys.stderr)
            time.sleep(RATE_LIMIT_SLEEP)
            continue

        markets = markets_data.get("markets", [])
        for market in markets:
            market_ticker = market.get("ticker", "")
            market_filename = f"market_{ticker}_{market_ticker}.json"
            market_path = market_dir / market_filename
            market_path.write_text(json.dumps(market, indent=4), encoding="utf-8")
            market_count += 1

        print(f"  {ticker}: {len(markets)} markets")
        time.sleep(RATE_LIMIT_SLEEP)

    return series_count, market_count


def main() -> int:
    args = parse_args()
    market_dir = Path(args.market_dir)
    series_dir = Path(args.series_dir)

    started = datetime.now(timezone.utc).isoformat()
    print(f"fetch_kalshi_markets started at {started}")
    print(f"  market-dir: {market_dir}")
    print(f"  series-dir: {series_dir}")

    try:
        series_count, market_count = fetch_all_markets(
            market_dir=market_dir,
            series_dir=series_dir,
            timeout=args.timeout,
            retries=max(args.retries, 1),
            retry_delay=max(args.retry_delay, 0.1),
            bypass_proxy=args.bypass_proxy_for_kalshi,
        )
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
        print(f"Kalshi fetch failed: {err}", file=sys.stderr)
        print(
            "If this is a proxy issue, rerun with --bypass-proxy-for-kalshi.",
            file=sys.stderr,
        )
        return 1
    except OSError as err:
        print(f"Unable to write output files: {err}", file=sys.stderr)
        return 1

    finished = datetime.now(timezone.utc).isoformat()
    print(
        f"fetch_kalshi_markets complete at {finished}: "
        f"{series_count} series, {market_count} markets written"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
