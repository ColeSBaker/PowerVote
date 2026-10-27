import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch
from urllib import error


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_kalshi_series.py"
spec = importlib.util.spec_from_file_location("fetch_kalshi_series", MODULE_PATH)
fetch_kalshi_series = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(fetch_kalshi_series)


class FetchKalshiSeriesTests(unittest.TestCase):
    def test_build_direct_no_proxy_env_includes_host_and_clears_proxy(self):
        with patch.dict(
            fetch_kalshi_series.os.environ,
            {"NO_PROXY": "example.com", "HTTPS_PROXY": "http://proxy:8080"},
            clear=False,
        ):
            env = fetch_kalshi_series._build_direct_no_proxy_env(
                "https://api.elections.kalshi.com/trade-api/v2/series"
            )

        self.assertIn("api.elections.kalshi.com", env["NO_PROXY"])
        self.assertIn("api.elections.kalshi.com", env["no_proxy"])
        self.assertEqual(env["HTTP_PROXY"], "")
        self.assertEqual(env["HTTPS_PROXY"], "")

    def test_load_cached_payload_supports_wrapped_and_raw_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            wrapped = temp_path / "wrapped.json"
            raw = temp_path / "raw.json"

            wrapped.write_text(json.dumps({"payload": {"series": [1, 2, 3]}}), encoding="utf-8")
            raw.write_text(json.dumps({"series": [4, 5]}), encoding="utf-8")

            self.assertEqual(fetch_kalshi_series.load_cached_payload(wrapped), {"series": [1, 2, 3]})
            self.assertEqual(fetch_kalshi_series.load_cached_payload(raw), {"series": [4, 5]})

    def test_fetch_series_tries_direct_mode_after_proxied_failures(self):
        responses = [
            error.URLError("proxy failure"),
            {"series": [{"ticker": "KXTEST"}]},
        ]

        def fake_request_json(url, timeout, direct_mode=False):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch.object(fetch_kalshi_series, "_request_json", side_effect=fake_request_json):
            payload, mode = fetch_kalshi_series.fetch_series(
                url="https://api.elections.kalshi.com/trade-api/v2/series",
                timeout=1,
                retries=1,
                retry_delay=0.1,
                bypass_proxy_for_kalshi=True,
            )

        self.assertEqual(mode, "direct")
        self.assertEqual(payload["series"][0]["ticker"], "KXTEST")

    def test_fetch_series_raises_last_error_when_all_attempts_fail(self):
        with patch.object(
            fetch_kalshi_series,
            "_request_json",
            side_effect=error.URLError("down"),
        ):
            with self.assertRaises(error.URLError):
                fetch_kalshi_series.fetch_series(
                    url="https://api.elections.kalshi.com/trade-api/v2/series",
                    timeout=1,
                    retries=2,
                    retry_delay=0.01,
                    bypass_proxy_for_kalshi=False,
                )

    def test_main_writes_fresh_payload_on_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "series.json"
            args = Namespace(
                url="https://api.elections.kalshi.com/trade-api/v2/series",
                output=str(output_path),
                timeout=5.0,
                retries=1,
                retry_delay=0.1,
                bypass_proxy_for_kalshi=False,
                cache_fallback="",
            )

            with patch.object(fetch_kalshi_series, "parse_args", return_value=args), patch.object(
                fetch_kalshi_series,
                "fetch_series",
                return_value=({"series": [{"ticker": "ONE"}]}, "proxied"),
            ):
                status = fetch_kalshi_series.main()

            self.assertEqual(status, 0)
            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertFalse(written["stale"])
            self.assertEqual(written["source"], "kalshi-public-elections-api:proxied")
            self.assertEqual(written["payload"]["series"][0]["ticker"], "ONE")

    def test_main_uses_cache_fallback_when_fetch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "series.json"
            cache_path = temp_path / "cache.json"
            cache_path.write_text(json.dumps({"payload": {"series": [{"ticker": "CACHED"}]}}), encoding="utf-8")

            args = Namespace(
                url="https://api.elections.kalshi.com/trade-api/v2/series",
                output=str(output_path),
                timeout=5.0,
                retries=1,
                retry_delay=0.1,
                bypass_proxy_for_kalshi=False,
                cache_fallback=str(cache_path),
            )

            with patch.object(fetch_kalshi_series, "parse_args", return_value=args), patch.object(
                fetch_kalshi_series,
                "fetch_series",
                side_effect=error.URLError("offline"),
            ):
                status = fetch_kalshi_series.main()

            self.assertEqual(status, 0)
            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(written["stale"])
            self.assertEqual(written["payload"]["series"][0]["ticker"], "CACHED")

    def test_main_returns_error_without_cache_when_fetch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "series.json"
            args = Namespace(
                url="https://api.elections.kalshi.com/trade-api/v2/series",
                output=str(output_path),
                timeout=5.0,
                retries=1,
                retry_delay=0.1,
                bypass_proxy_for_kalshi=False,
                cache_fallback="",
            )

            with patch.object(fetch_kalshi_series, "parse_args", return_value=args), patch.object(
                fetch_kalshi_series,
                "fetch_series",
                side_effect=error.URLError("offline"),
            ):
                status = fetch_kalshi_series.main()

            self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
