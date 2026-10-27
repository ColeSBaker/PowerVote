import importlib.util
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_congressional_map_layers.py"
spec = importlib.util.spec_from_file_location("build_congressional_map_layers", MODULE_PATH)
build_congressional_map_layers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(build_congressional_map_layers)


class BuildCongressionalMapLayersTests(unittest.TestCase):
    def test_parse_html_table_extracts_properties(self):
        html = "<table><tr><td>STATE</td><td>NM</td></tr><tr><td>DISTRICT</td><td>02</td></tr></table>"
        self.assertEqual(
            build_congressional_map_layers.parse_html_table(html),
            {"STATE": "NM", "DISTRICT": "02"},
        )

    def test_build_district_geojson_from_kmz_includes_ak_hi_and_filters_non_state_territories_and_zz(self):
        kml = textwrap.dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <kml xmlns="http://www.opengis.net/kml/2.2">
              <Document>
                <Placemark>
                  <description><![CDATA[
                    <html><body><table border="1">
                      <tr><td>STATE</td><td>NM</td></tr>
                      <tr><td>DISTRICT</td><td>02</td></tr>
                      <tr><td>NAMELSAD</td><td>Congressional District 2</td></tr>
                      <tr><td>GEOID</td><td>3502</td></tr>
                    </table></body></html>
                  ]]></description>
                  <Polygon>
                    <outerBoundaryIs><LinearRing><coordinates>
                      -109.0,31.0,0 -108.0,31.0,0 -108.0,32.0,0 -109.0,31.0,0
                    </coordinates></LinearRing></outerBoundaryIs>
                  </Polygon>
                </Placemark>
                <Placemark>
                  <description><![CDATA[
                    <html><body><table border="1">
                      <tr><td>STATE</td><td>AK</td></tr>
                      <tr><td>DISTRICT</td><td>00</td></tr>
                    </table></body></html>
                  ]]></description>
                  <Polygon>
                    <outerBoundaryIs><LinearRing><coordinates>
                      -150.0,60.0,0 -149.0,60.0,0 -149.0,61.0,0 -150.0,60.0,0
                    </coordinates></LinearRing></outerBoundaryIs>
                  </Polygon>
                </Placemark>
                <Placemark>
                  <description><![CDATA[
                    <html><body><table border="1">
                      <tr><td>STATE</td><td>HI</td></tr>
                      <tr><td>DISTRICT</td><td>01</td></tr>
                    </table></body></html>
                  ]]></description>
                  <Polygon>
                    <outerBoundaryIs><LinearRing><coordinates>
                      -158.3,21.2,0 -157.9,21.2,0 -157.9,21.6,0 -158.3,21.2,0
                    </coordinates></LinearRing></outerBoundaryIs>
                  </Polygon>
                </Placemark>
                <Placemark>
                  <description><![CDATA[
                    <html><body><table border="1">
                      <tr><td>STATE</td><td>PR</td></tr>
                      <tr><td>DISTRICT</td><td>01</td></tr>
                    </table></body></html>
                  ]]></description>
                  <Polygon>
                    <outerBoundaryIs><LinearRing><coordinates>
                      -66.5,18.0,0 -66.0,18.0,0 -66.0,18.4,0 -66.5,18.0,0
                    </coordinates></LinearRing></outerBoundaryIs>
                  </Polygon>
                </Placemark>
                <Placemark>
                  <description><![CDATA[
                    <html><body><table border="1">
                      <tr><td>STATEFP</td><td>09</td></tr>
                      <tr><td>CD119FP</td><td>ZZ</td></tr>
                    </table></body></html>
                  ]]></description>
                  <Polygon>
                    <outerBoundaryIs><LinearRing><coordinates>
                      -73.0,41.0,0 -72.0,41.0,0 -72.0,42.0,0 -73.0,41.0,0
                    </coordinates></LinearRing></outerBoundaryIs>
                  </Polygon>
                </Placemark>
              </Document>
            </kml>
            """
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            kmz_path = root / "sample.kmz"
            with zipfile.ZipFile(kmz_path, "w") as archive:
                archive.writestr("doc.kml", kml)

            payload = build_congressional_map_layers.build_district_geojson(root)

        self.assertEqual(len(payload["features"]), 3)
        self.assertEqual(
            sorted((feature["properties"]["STATE_ABBR"], feature["properties"]["DISTRICT"]) for feature in payload["features"]),
            [("AK", "AL"), ("HI", "01"), ("NM", "02")],
        )

    def test_build_state_geojson_from_districts_creates_outline_feature(self):
        district_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"STATE_ABBR": "NM"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-109.0, 31.0], [-108.0, 31.0], [-108.0, 32.0], [-109.0, 31.0]]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"STATE_ABBR": "NM"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-107.5, 32.0], [-106.5, 32.0], [-106.5, 33.0], [-107.5, 32.0]]],
                    },
                },
            ],
        }

        payload = build_congressional_map_layers.build_state_geojson_from_districts(district_geojson)

        self.assertEqual(len(payload["features"]), 1)
        self.assertEqual(payload["features"][0]["properties"]["STATE_ABBR"], "NM")
        self.assertEqual(payload["features"][0]["geometry"]["type"], "Polygon")


if __name__ == "__main__":
    unittest.main()
