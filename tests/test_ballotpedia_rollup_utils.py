import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ballotpedia_rollup import html_utils, meta, normalize


class BallotpediaRollupUtilsTests(unittest.TestCase):
    def test_party_and_value_normalization(self):
        self.assertEqual(normalize.norm_party("Democratic Party"), "D")
        self.assertEqual(normalize.norm_party("No party affiliation"), "IND")
        self.assertEqual(normalize.clean_name(" Jane Doe ✔ "), "Jane Doe")
        self.assertEqual(normalize.parse_int_votes("89,484 votes"), 89484)
        self.assertEqual(normalize.parse_pct("53.4%"), 53.4)

    def test_html_helpers_find_ids_classes_and_sections(self):
        html = """
        <div id="Candidates_and_election_results"></div>
        <div class="foo votebox bar"></div>
        <h2>General election</h2><p>A</p>
        <h2>Democratic primary</h2><p>B</p>
        """
        ids = html_utils.find_anchor_ids(html)
        self.assertIn("Candidates_and_election_results", ids)
        self.assertTrue(html_utils.contains_class(html, "votebox"))
        self.assertIn("A", html_utils.section_after_heading(html, "General election") or "")

    def test_meta_extracts_title_url_and_filename_seed(self):
        html = """
        <html><head>
        <title>Example Seat</title>
        <meta property="og:url" content="https://example.com/seat" />
        </head></html>
        """
        extracted = meta.extract_meta(html, Path("TX-07.txt"))
        self.assertEqual(extracted["title"], "Example Seat")
        self.assertEqual(extracted["source_url"], "https://example.com/seat")
        self.assertEqual(extracted["seat"], "TX-07")


if __name__ == "__main__":
    unittest.main()
