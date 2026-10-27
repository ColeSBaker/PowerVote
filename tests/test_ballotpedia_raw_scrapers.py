import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup.scrape_house import (  # noqa: E402
    HOUSE_NATIONAL_URL,
    build_house_download_plan,
    discover_seat_links,
    discover_state_links,
)
from ballotpedia_rollup.scrape_senate import (  # noqa: E402
    SENATE_NATIONAL_URL,
    build_senate_download_plan,
    discover_senate_links,
)
from ballotpedia_rollup.scrape_governor import (  # noqa: E402
    GOVERNOR_NATIONAL_URL,
    build_governor_download_plan,
    discover_governor_links,
    discover_ltgovernor_links,
)
from ballotpedia_rollup.scrape_shared import (  # noqa: E402
    FetchExhaustedError,
    RetryPolicy,
    ScrapeConfig,
    fetch_with_retry,
    get_or_fetch,
    looks_like_rejected_or_bad_response,
)


def _load_script(name: str):
    module_path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class SharedScraperCoreTests(unittest.TestCase):
    def test_looks_like_rejected_or_bad_response_flags_short_and_bad_marker(self):
        self.assertTrue(looks_like_rejected_or_bad_response("x", min_nonempty_chars=5))
        blocked = "<html><body>Access denied due to unusual traffic.</body></html>"
        self.assertTrue(looks_like_rejected_or_bad_response(blocked))
        self.assertFalse(looks_like_rejected_or_bad_response("<html><body>valid content " + ("z" * 250) + "</body></html>"))

    def test_fetch_with_retry_retries_then_succeeds(self):
        responses = iter(
            [
                (500, "<html><body>bad</body></html>"),
                (200, "<html><body>" + ("ok " * 120) + "</body></html>"),
            ]
        )

        def fake_fetch(url, headers, timeout):
            del url, headers, timeout
            return next(responses)

        sleeps: List[float] = []
        text = fetch_with_retry(
            url="https://example.com",
            filename="National.txt",
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(initial_delay_seconds=0.1, max_attempts=3, backoff_multiplier=2.0),
            headers={},
            min_nonempty_chars=20,
            fetcher=fake_fetch,
            sleep_fn=sleeps.append,
            logger=lambda _: None,
        )
        self.assertIn("ok", text)
        self.assertEqual(sleeps[0], 0.1)
        self.assertEqual(sleeps[1], 0.2)

    def test_fetch_with_retry_raises_when_exhausted(self):
        def bad_fetch(url, headers, timeout):
            del url, headers, timeout
            return 500, "<html><body>blocked</body></html>"

        with self.assertRaises(FetchExhaustedError):
            fetch_with_retry(
                url="https://example.com",
                filename="National.txt",
                timeout_seconds=10.0,
                retry_policy=RetryPolicy(initial_delay_seconds=0.0, max_attempts=2, backoff_multiplier=2.0),
                headers={},
                min_nonempty_chars=20,
                fetcher=bad_fetch,
                sleep_fn=lambda _: None,
                logger=lambda _: None,
            )

    def test_get_or_fetch_uses_cache_and_refreshes_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            outdir = Path(tmp_dir)
            config = ScrapeConfig(base_url="https://example.com", national_url="https://example.com/n", outdir=outdir)
            target = outdir / "National.txt"
            target.write_text("<html><body>" + ("cached " * 60) + "</body></html>", encoding="utf-8")

            def should_not_fetch(url, headers, timeout):
                raise AssertionError("fetch should not be called")

            cached, source = get_or_fetch(
                config=config,
                url="https://example.com/n",
                filename="National.txt",
                fetcher=should_not_fetch,
                sleep_fn=lambda _: None,
                logger=lambda _: None,
            )
            self.assertEqual(source, "cache")
            self.assertIn("cached", cached)

            target.write_text("", encoding="utf-8")

            def good_fetch(url, headers, timeout):
                del url, headers, timeout
                return 200, "<html><body>" + ("fresh " * 60) + "</body></html>"

            fresh, source = get_or_fetch(
                config=config,
                url="https://example.com/n",
                filename="National.txt",
                fetcher=good_fetch,
                sleep_fn=lambda _: None,
                logger=lambda _: None,
            )
            self.assertEqual(source, "write")
            self.assertIn("fresh", fresh)


class HouseDiscoveryTests(unittest.TestCase):
    def test_discover_state_links_extracts_expected_states(self):
        html = """
        <a href="/United_States_House_of_Representatives_elections_in_Alabama,_2026">AL</a>
        <a href="/United_States_House_of_Representatives_election_in_Alaska,_2026">AK</a>
        <a href="/ignore">Nope</a>
        """
        links = discover_state_links(html)
        self.assertEqual(list(links.keys()), ["Alabama", "Alaska"])
        self.assertTrue(links["Alabama"].endswith("Alabama,_2026"))

    def test_discover_seat_links_extracts_al_and_numbered_and_sorts(self):
        html = """
        <a href="/Alabama%27s_2nd_Congressional_District_election,_2026">2nd</a>
        <a href="/Alabama%27s_At-large_Congressional_District_election,_2026">AL</a>
        <a href="/Alabama%27s_1st_Congressional_District_election,_2026">1st</a>
        """
        links = discover_seat_links(html, "Alabama")
        self.assertEqual(list(links.keys()), ["AL", "1", "2"])

    def test_build_house_download_plan_matches_parser_file_naming(self):
        national_html = """
        <a href="/United_States_House_of_Representatives_elections_in_Alabama,_2026">Alabama</a>
        """
        state_html_by_name = {
            "Alabama": """
            <a href="/Alabama%27s_At-large_Congressional_District_election,_2026">AL</a>
            <a href="/Alabama%27s_1st_Congressional_District_election,_2026">1</a>
            """
        }
        plan = build_house_download_plan(national_html, state_html_by_name)
        filenames = [name for name, _ in plan]
        self.assertEqual(filenames, ["National.txt", "AL.txt", "AL-AL.txt", "AL-1.txt"])
        self.assertEqual(plan[0][1], HOUSE_NATIONAL_URL)


class SenateDiscoveryTests(unittest.TestCase):
    def test_discover_senate_links_extracts_regular_and_special(self):
        html = """
        <a href="/United_States_Senate_election_in_Alaska,_2026">AK regular</a>
        <a href="/United_States_Senate_special_election_in_Florida,_2026">FL special</a>
        """
        links = discover_senate_links(html)
        self.assertIn("AK", links)
        self.assertIn("FL-SPECIAL", links)
        self.assertEqual(links["AK"]["kind"], "regular")
        self.assertEqual(links["FL-SPECIAL"]["kind"], "special")

    def test_build_senate_download_plan_matches_parser_file_naming(self):
        html = """
        <a href="/United_States_Senate_election_in_Alaska,_2026">AK regular</a>
        <a href="/United_States_Senate_special_election_in_Florida,_2026">FL special</a>
        """
        plan = build_senate_download_plan(html)
        filenames = [name for name, _ in plan]
        self.assertEqual(filenames, ["National.txt", "AK.txt", "FL-SPECIAL.txt"])
        self.assertEqual(plan[0][1], SENATE_NATIONAL_URL)


class GovernorDiscoveryTests(unittest.TestCase):
    def test_discover_governor_and_ltgovernor_links_extract_expected_states(self):
        html = """
        <a href="/Alabama_gubernatorial_election,_2026">AL governor</a>
        <a href="/Iowa_gubernatorial_and_lieutenant_gubernatorial_election,_2026">IA combined</a>
        <a href="/Arizona_lieutenant_gubernatorial_election,_2026">AZ lt governor</a>
        <a href="/Puerto_Rico_gubernatorial_election,_2026">PR excluded</a>
        """

        governor = discover_governor_links(html)
        ltgovernor = discover_ltgovernor_links(html)

        self.assertEqual(set(governor.keys()), {"AL", "IA"})
        self.assertEqual(set(ltgovernor.keys()), {"AZ", "IA"})
        self.assertEqual(governor["IA"]["kind"], "combined")
        self.assertEqual(ltgovernor["IA"]["kind"], "combined")

    def test_build_governor_download_plan_matches_parser_file_naming(self):
        html = """
        <a href="/Alabama_gubernatorial_election,_2026">AL governor</a>
        <a href="/Arizona_lieutenant_gubernatorial_election,_2026">AZ lt governor</a>
        <a href="/Iowa_gubernatorial_and_lieutenant_gubernatorial_election,_2026">IA combined</a>
        """
        plan = build_governor_download_plan(html)
        filenames = [name for name, _ in plan]
        self.assertEqual(
            filenames,
            [
                "National.txt",
                "AL-GOV.txt",
                "AZ-LTGOV.txt",
                "IA-GOV.txt",
                "IA-LTGOV.txt",
            ],
        )
        self.assertEqual(plan[0][1], GOVERNOR_NATIONAL_URL)


class WrapperSmokeTests(unittest.TestCase):
    def test_house_wrapper_parse_defaults(self):
        module = _load_script("scrape_ballotpedia_house_raw.py")
        args = module.parse_args([])
        self.assertEqual(args.outdir, "ballotpedia_house_raw")
        self.assertEqual(args.max_attempts, 7)

    def test_senate_wrapper_parse_defaults(self):
        module = _load_script("scrape_ballotpedia_senate_raw.py")
        args = module.parse_args([])
        self.assertEqual(args.outdir, "ballotpedia_senate_raw")
        self.assertEqual(args.max_attempts, 7)
        self.assertFalse(args.force_refresh)

    def test_governor_wrapper_parse_defaults(self):
        module = _load_script("scrape_ballotpedia_governor_raw.py")
        args = module.parse_args([])
        self.assertEqual(args.outdir, "ballotpedia_governor_raw")
        self.assertEqual(args.max_attempts, 7)
        self.assertEqual(args.office, "state_governor")

    def test_house_wrapper_main_smoke(self):
        module = _load_script("scrape_ballotpedia_house_raw.py")
        called = {"value": False}

        def fake_run(config):
            called["value"] = True
            self.assertEqual(config.outdir.name, "ballotpedia_house_raw")
            from ballotpedia_rollup.scrape_shared import ScrapeSummary

            return ScrapeSummary(
                office="us_house",
                outdir=config.outdir,
                national_pages=1,
                state_pages=1,
                seat_pages=1,
                files_cached=0,
                files_written=3,
            )

        module.run_house_scrape = fake_run
        status = module.main([])
        self.assertEqual(status, 0)
        self.assertTrue(called["value"])

    def test_senate_wrapper_main_smoke_with_force_refresh(self):
        module = _load_script("scrape_ballotpedia_senate_raw.py")
        called = {"value": False}

        def fake_run(config):
            called["value"] = True
            self.assertEqual(config.outdir.name, "tmp_senate")
            self.assertTrue(config.force_refresh)
            from ballotpedia_rollup.scrape_shared import ScrapeSummary

            return ScrapeSummary(
                office="us_senate",
                outdir=config.outdir,
                national_pages=1,
                state_pages=1,
                seat_pages=1,
                files_cached=0,
                files_written=2,
            )

        module.run_senate_scrape = fake_run
        status = module.main(["--outdir", "tmp_senate", "--force-refresh"])
        self.assertEqual(status, 0)
        self.assertTrue(called["value"])

    def test_governor_wrapper_main_smoke_with_force_refresh(self):
        module = _load_script("scrape_ballotpedia_governor_raw.py")
        called = {"value": False}

        def fake_run(config):
            called["value"] = True
            self.assertEqual(config.outdir.name, "tmp_governor")
            self.assertTrue(config.force_refresh)
            from ballotpedia_rollup.scrape_shared import ScrapeSummary

            return ScrapeSummary(
                office="state_governor",
                outdir=config.outdir,
                national_pages=1,
                state_pages=1,
                seat_pages=2,
                files_cached=0,
                files_written=3,
            )

        module.run_governor_scrape = fake_run
        status = module.main(["--outdir", "tmp_governor", "--force-refresh"])
        self.assertEqual(status, 0)
        self.assertTrue(called["value"])


if __name__ == "__main__":
    unittest.main()
