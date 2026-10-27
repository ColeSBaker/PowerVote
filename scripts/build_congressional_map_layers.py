#!/usr/bin/env python3
"""Build local GIS layers for the congressional map."""
from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = REPO_ROOT / "test_data" / "maps" / "NTAD_Congressional_Districts_03182026"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "apps" / "web" / "data"
DEFAULT_KMZ_GLOB = "*.kmz"
OUTPUT_DISTRICT_FILE = DEFAULT_OUTPUT_DIR / "congressional-districts.geojson"
OUTPUT_STATE_FILE = DEFAULT_OUTPUT_DIR / "us-states.geojson"

REMOTE_STATE_SOURCE = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/"
    "USA_States_Generalized/FeatureServer/0/query"
    "?where=STATE_ABBR%20NOT%20IN%20(%27PR%27%2C%27GU%27%2C%27MP%27%2C%27VI%27%2C%27AS%27)"
    "&outFields=STATE_ABBR,STATE_NAME&returnGeometry=true&f=geojson"
)

NON_STATE_TERRITORIES = {"PR", "GU", "MP", "VI", "AS", "AQ"}
KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

STATE_FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}


def normalize_coordinate(value: str) -> float:
    return round(float(value), 4)


def parse_coordinates(text: str) -> list[list[float]]:
    coordinates = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lon = normalize_coordinate(parts[0])
        lat = normalize_coordinate(parts[1])
        coordinates.append([lon, lat])
    return coordinates


def perpendicular_distance(point: list[float], start: list[float], end: list[float]) -> float:
    if start == end:
        return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
    numerator = abs(
        (end[1] - start[1]) * point[0]
        - (end[0] - start[0]) * point[1]
        + end[0] * start[1]
        - end[1] * start[0]
    )
    denominator = ((end[1] - start[1]) ** 2 + (end[0] - start[0]) ** 2) ** 0.5
    return numerator / denominator


def simplify_line(points: list[list[float]], epsilon: float = 0.01) -> list[list[float]]:
    if len(points) <= 2:
        return points

    start = points[0]
    end = points[-1]
    max_distance = -1.0
    split_index = 0
    for index in range(1, len(points) - 1):
        distance = perpendicular_distance(points[index], start, end)
        if distance > max_distance:
            max_distance = distance
            split_index = index

    if max_distance > epsilon:
        left = simplify_line(points[: split_index + 1], epsilon)
        right = simplify_line(points[split_index:], epsilon)
        return left[:-1] + right
    return [start, end]


def simplify_ring(points: list[list[float]], epsilon: float = 0.01) -> list[list[float]]:
    if len(points) < 4:
        return points

    closed = points[0] == points[-1]
    open_points = points[:-1] if closed else points
    simplified = simplify_line(open_points, epsilon)
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])

    while len(simplified) < 4 and len(open_points) >= len(simplified):
        simplified = open_points[:]
        if simplified[0] != simplified[-1]:
            simplified.append(simplified[0])
        break
    return simplified


def parse_html_table(html: str) -> dict[str, str]:
    pairs = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td></tr>", html, flags=re.S)
    cleaned: dict[str, str] = {}
    for key, value in pairs:
        plain_value = re.sub(r"<.*?>", "", value).strip()
        cleaned[key.strip()] = "" if plain_value == "Null" else plain_value
    return cleaned


def district_code_from_properties(properties: dict[str, str]) -> str:
    raw_value = (
        properties.get("DISTRICT")
        or properties.get("CD119FP")
        or properties.get("CD118FP")
        or ""
    ).strip().upper()
    if raw_value in {"00", "0", "AL"}:
        return "AL"
    return raw_value.zfill(2)


def state_code_from_properties(properties: dict[str, str]) -> str | None:
    state = (properties.get("STATE") or "").strip().upper()
    if state:
        return state
    state_fips = (properties.get("STATEFP") or "").strip().zfill(2)
    return STATE_FIPS_TO_ABBR.get(state_fips)


def parse_polygon(placemark: ET.Element) -> dict | None:
    polygons = []
    for polygon in placemark.findall(".//kml:Polygon", KML_NS):
        outer = polygon.find("./kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS)
        if outer is None or not outer.text:
            continue
        outer_ring = parse_coordinates(outer.text)
        if len(outer_ring) < 4:
            continue

        rings = [simplify_ring(outer_ring)]
        for inner in polygon.findall("./kml:innerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS):
            if inner.text:
                inner_ring = parse_coordinates(inner.text)
                if len(inner_ring) >= 4:
                    rings.append(simplify_ring(inner_ring))
        polygons.append(rings)

    if not polygons:
        return None
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def iter_kml_features(kml_text: str):
    root = ET.fromstring(kml_text)
    for placemark in root.findall(".//kml:Placemark", KML_NS):
        description = placemark.findtext("./kml:description", default="", namespaces=KML_NS)
        properties = parse_html_table(description)
        geometry = parse_polygon(placemark)
        if geometry is None:
            continue
        yield properties, geometry


def build_district_geojson(source_dir: Path = DEFAULT_SOURCE_DIR) -> dict:
    kmz_candidates = sorted(source_dir.glob(DEFAULT_KMZ_GLOB))
    if not kmz_candidates:
        raise FileNotFoundError(f"No KMZ file found under {source_dir}")

    kmz_path = kmz_candidates[0]
    with zipfile.ZipFile(kmz_path) as archive:
        kml_name = next(name for name in archive.namelist() if name.lower().endswith(".kml"))
        kml_text = archive.read(kml_name).decode("utf-8", errors="ignore")

    features = []
    for properties, geometry in iter_kml_features(kml_text):
        state_code = state_code_from_properties(properties)
        district_code = district_code_from_properties(properties)
        if not state_code or state_code in NON_STATE_TERRITORIES or district_code == "ZZ":
            continue

        feature_properties = {
            "STATEFP": properties.get("STATEFP"),
            "STATE_ABBR": state_code,
            "DISTRICT": district_code,
            "NAME": properties.get("NAMELSAD") or properties.get("NAME") or f"{state_code}-{district_code}",
            "GEOID": properties.get("GEOID"),
            "GEOIDFQ": properties.get("GEOIDFQ"),
            "CDSESSN": properties.get("CDSESSN"),
            "INTPTLAT": properties.get("INTPTLAT"),
            "INTPTLON": properties.get("INTPTLON"),
        }
        features.append({"type": "Feature", "properties": feature_properties, "geometry": geometry})

    return {"type": "FeatureCollection", "features": features}


def fetch_state_geojson() -> dict:
    with urllib.request.urlopen(REMOTE_STATE_SOURCE) as response:
        return json.load(response)


def iter_geometry_points(geometry: dict):
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        for ring in coordinates:
            for point in ring:
                yield point
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for point in ring:
                    yield point


def cross(o: list[float], a: list[float], b: list[float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points: list[list[float]]) -> list[list[float]]:
    unique_points = sorted({(point[0], point[1]) for point in points})
    if len(unique_points) <= 1:
        return [[*point] for point in unique_points]

    lower: list[tuple[float, float]] = []
    for point in unique_points:
        while len(lower) >= 2 and cross(list(lower[-2]), list(lower[-1]), list(point)) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and cross(list(upper[-2]), list(upper[-1]), list(point)) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    return [[lon, lat] for lon, lat in hull]


def build_state_geojson_from_districts(district_geojson: dict) -> dict:
    state_points: dict[str, list[list[float]]] = {}
    for feature in district_geojson.get("features", []):
        state_code = feature.get("properties", {}).get("STATE_ABBR")
        if not state_code:
            continue
        state_points.setdefault(state_code, []).extend(iter_geometry_points(feature.get("geometry", {})))

    features = []
    for state_code, points in sorted(state_points.items()):
        hull = convex_hull(points)
        if len(hull) < 3:
            continue
        hull.append(hull[0])
        features.append(
            {
                "type": "Feature",
                "properties": {"STATE_ABBR": state_code, "STATE_NAME": state_code},
                "geometry": {"type": "Polygon", "coordinates": [hull]},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_layers(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    district_output: Path = OUTPUT_DISTRICT_FILE,
    state_output: Path = OUTPUT_STATE_FILE,
) -> tuple[dict, dict]:
    district_geojson = build_district_geojson(source_dir)
    try:
        state_geojson = fetch_state_geojson()
    except Exception:
        state_geojson = build_state_geojson_from_districts(district_geojson)
    write_json(district_output, district_geojson)
    write_json(state_output, state_geojson)
    return district_geojson, state_geojson


def main() -> None:
    district_geojson, state_geojson = build_layers()
    print(
        "Wrote "
        f"{len(district_geojson['features'])} congressional districts to {OUTPUT_DISTRICT_FILE} "
        f"and {len(state_geojson.get('features', []))} state outlines to {OUTPUT_STATE_FILE}"
    )


if __name__ == "__main__":
    main()
