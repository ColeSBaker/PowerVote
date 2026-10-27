#!/usr/bin/env python3
"""Fetch Kalshi election series data without API keys.

This utility uses Kalshi's public elections endpoint and writes JSON to disk so
scheduled ingestion can run without manual intervention.
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

DEFAULT_URL = "https://api.elections.kalshi.com/trade-api/v2/series"
DEFAULT_OUTPUT = "data/kalshi/series.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch public Kalshi election series and persist response JSON."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Kalshi endpoint URL to query (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Path to write the output JSON (default: %(default)s)",
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
        help="Number of network attempts per mode (default: %(default)s)",
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
        help=(
            "Attempt a direct (no-proxy) Kalshi request if the proxied request fails."
        ),
    )
    parser.add_argument(
        "--cache-fallback",
        default=DEFAULT_OUTPUT,
        help=(
            "Fallback JSON to use when network fetch fails. Set empty string to disable "
            "fallback (default: %(default)s)."
        ),
    )
    return parser.parse_args()


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

    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
    ):
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


def fetch_series(
    url: str,
    timeout: float,
    retries: int,
    retry_delay: float,
    bypass_proxy_for_kalshi: bool,
) -> tuple[Any, str]:
    modes = ["proxied"]
    if bypass_proxy_for_kalshi:
        modes.append("direct")

    last_error: Exception | None = None

    for mode in modes:
        direct_mode = mode == "direct"
        delay = retry_delay

        for attempt in range(1, retries + 1):
            try:
                payload = _request_json(url=url, timeout=timeout, direct_mode=direct_mode)
                return payload, mode
            except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
                last_error = err
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2

    if last_error is None:
        raise RuntimeError("Kalshi fetch failed without a captured exception")
    raise last_error


def load_cached_payload(cache_path: Path) -> Any:
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "payload" in raw:
        return raw["payload"]
    return raw


def write_payload(payload: Any, output_path: Path, source: str, stale: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wrapped_payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "stale": stale,
        "payload": payload,
    }
    output_path.write_text(json.dumps(wrapped_payload, indent=2), encoding="utf-8")


def _count_series(payload: Any) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("series"), list):
        return len(payload["series"])
    return 0


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    cache_fallback = args.cache_fallback.strip()

    try:
        payload, mode = fetch_series(
            url=args.url,
            timeout=args.timeout,
            retries=max(args.retries, 1),
            retry_delay=max(args.retry_delay, 0.1),
            bypass_proxy_for_kalshi=args.bypass_proxy_for_kalshi,
        )
        write_payload(
            payload=payload,
            output_path=output_path,
            source=f"kalshi-public-elections-api:{mode}",
            stale=False,
        )
        print(
            "Fetched Kalshi series successfully: "
            f"{_count_series(payload)} series written to {output_path}"
        )
        return 0

    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
        if cache_fallback:
            cache_path = Path(cache_fallback)
            if cache_path.exists():
                try:
                    cached_payload = load_cached_payload(cache_path)
                    write_payload(
                        payload=cached_payload,
                        output_path=output_path,
                        source=f"cache-fallback:{cache_path}",
                        stale=True,
                    )
                    print(
                        "Kalshi fetch failed; used cache fallback: "
                        f"{cache_path} -> {output_path}. Error: {err}",
                        file=sys.stderr,
                    )
                    return 0
                except (OSError, json.JSONDecodeError) as cache_err:
                    print(
                        f"Kalshi fetch failed and cache fallback unreadable: {cache_err}",
                        file=sys.stderr,
                    )

        print(
            "Kalshi fetch failed. "
            "If this is a proxy tunnel issue, rerun with "
            "--bypass-proxy-for-kalshi and/or configure NO_PROXY for "
            "api.elections.kalshi.com. "
            f"Error: {err}",
            file=sys.stderr,
        )
        return 1
    except OSError as err:
        print(f"Unable to write output file: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
