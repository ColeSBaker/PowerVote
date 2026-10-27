#!/usr/bin/env python3
"""
Generate zipcode centroid data from US Census Bureau ZCTA boundaries.

Downloads the official TIGER/Line Shapefiles ZCTA data and extracts the
centroid (latitude, longitude) for each 5-digit zipcode. Output is a JSON
file compatible with PowerVote's zipcode lookup service.

Usage:
    python generate_zipcode_centroids.py
    
Output:
    Generated JSON file at: ../PowerVote/apps/web-next/lib/server/zipcode-centroids-data.json
    
Licensing:
    Source: U.S. Census Bureau TIGER/Line Shapefiles 2025 (Public Domain)
"""

import json
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

try:
    import shapefile
    from shapely.geometry import shape as shape_from_geom
    from shapely.geometry import Polygon, MultiPolygon
except ImportError:
    print("Error: Required packages not found.")
    print("Install them with: pip install pyshp shapely")
    sys.exit(1)


CENSUS_ZCTA_URL = "https://www2.census.gov/geo/tiger/TIGER2025/ZCTA520/tl_2025_us_zcta520.zip"
OUTPUT_DIR = Path(__file__).parent.parent / "PowerVote" / "apps" / "web-next" / "lib" / "server"
OUTPUT_FILE = OUTPUT_DIR / "zipcode-centroids-data.json"


def download_and_extract_zcta_shapefile():
    """Download Census ZCTA shapefile and extract to temp directory."""
    print(f"Downloading ZCTA shapefile from Census Bureau...")
    print(f"URL: {CENSUS_ZCTA_URL}")
    
    temp_dir = Path(tempfile.gettempdir()) / "zcta_extract"
    temp_dir.mkdir(exist_ok=True)
    zip_file = temp_dir / "zcta520.zip"
    
    try:
        with urlopen(CENSUS_ZCTA_URL) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1 MB chunks
            
            with open(zip_file, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        percent = (downloaded / total_size) * 100
                        print(f"  Downloaded: {downloaded / 1024 / 1024:.1f} MB ({percent:.0f}%)", end='\r')
                print()  # New line after progress
    except Exception as e:
        print(f"Error downloading: {e}")
        sys.exit(1)
    
    # Extract shapefile
    print("Extracting shapefile...")
    with zipfile.ZipFile(zip_file, 'r') as zipf:
        zipf.extractall(temp_dir)
    
    # Find shapefile
    shapefiles = list(temp_dir.glob("*.shp"))
    if not shapefiles:
        print("Error: No shapefile found in archive")
        sys.exit(1)
    
    return str(shapefiles[0])


def extract_centroids(shapefile_path):
    """Extract centroid coordinates for all ZCTAs using pyshp."""
    print(f"Loading shapefile: {Path(shapefile_path).name}")
    
    try:
        # Read shapefile with pyshp
        shp_file = shapefile.Reader(str(shapefile_path))
    except Exception as e:
        print(f"Error reading shapefile: {e}")
        sys.exit(1)
    
    print(f"Processing {len(shp_file.records())} ZIP code tabulation areas...")
    
    centroids = {}
    errors = []
    
    # Get field index for ZCTA and coordinates
    field_names = [field[0] for field in shp_file.fields[1:]]  # Skip first (record ID)
    
    zcta_field_idx = None
    lat_field_idx = None
    lon_field_idx = None
    
    # Look for ZCTA field (different versions use different names)
    for idx, name in enumerate(field_names):
        if name.startswith('ZCTA5'):
            zcta_field_idx = idx
            print(f"  Using ZCTA field: {name}")
        elif name.startswith('INTPTLAT'):
            lat_field_idx = idx
            print(f"  Found pre-computed latitude: {name}")
        elif name.startswith('INTPTLON'):
            lon_field_idx = idx
            print(f"  Found pre-computed longitude: {name}")
    
    if zcta_field_idx is None:
        print(f"Error: Could not find ZCTA field. Available fields: {field_names}")
        sys.exit(1)
    
    # Process records
    for rec_idx, (shape_rec, attribute_rec) in enumerate(zip(shp_file.shapes(), shp_file.records())):
        if (rec_idx + 1) % 5000 == 0:
            print(f"  Processed: {rec_idx + 1}/{len(shp_file.records())}")
        
        try:
            # Get zipcode
            zipcode = str(attribute_rec[zcta_field_idx]).strip()
            
            if not zipcode or len(zipcode) != 5 or not zipcode.isdigit():
                errors.append(f"Row {rec_idx}: Invalid zipcode '{zipcode}'")
                continue
            
            # Use pre-computed interior point if available
            if lat_field_idx is not None and lon_field_idx is not None:
                try:
                    lat = float(attribute_rec[lat_field_idx])
                    lon = float(attribute_rec[lon_field_idx])
                    if lat != 0 and lon != 0:  # Skip invalid values
                        centroids[zipcode] = {
                            "latitude": round(lat, 6),
                            "longitude": round(lon, 6),
                        }
                        continue
                except (ValueError, TypeError):
                    pass  # Fall back to calculation
            
            # Fall back to calculating centroid from geometry
            if shape_rec.shapeType == 5:  # Polygon
                coords = shape_rec.points
                if not coords or len(coords) < 3:
                    errors.append(f"Zipcode {zipcode}: Invalid polygon")
                    continue
                
                poly = Polygon(coords)
                centroid = poly.centroid
            elif shape_rec.shapeType == 15:  # MultiPolygon
                polygons = []
                parts = shape_rec.parts + [len(shape_rec.points)]
                
                for i in range(len(shape_rec.parts)):
                    start = shape_rec.parts[i]
                    end = parts[i + 1]
                    coords = shape_rec.points[start:end]
                    if len(coords) >= 3:
                        polygons.append(Polygon(coords))
                
                if not polygons:
                    errors.append(f"Zipcode {zipcode}: No valid polygons in MultiPolygon")
                    continue
                
                multi = MultiPolygon(polygons)
                centroid = multi.centroid
            else:
                errors.append(f"Zipcode {zipcode}: Unsupported shape type {shape_rec.shapeType}")
                continue
            
            if centroid is None or centroid.is_empty:
                errors.append(f"Zipcode {zipcode}: Could not calculate centroid")
                continue
            
            # Store calculated centroid (swap x/y because pyshp uses (x, y) which is (lon, lat))
            centroids[zipcode] = {
                "latitude": round(centroid.y, 6),
                "longitude": round(centroid.x, 6),
            }
            
        except Exception as e:
            errors.append(f"Row {rec_idx}: {e}")
            continue
    
    print(f"Successfully extracted {len(centroids)} zipcodes")
    
    if errors:
        print(f"\nWarnings ({len(errors)} issues):")
        for error in errors[:10]:  # Show first 10
            print(f"  {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
    
    return centroids


def save_centroids(centroids):
    """Save centroids to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Sort by zipcode for readability
    sorted_centroids = dict(sorted(centroids.items()))
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(sorted_centroids, f, indent=2)
    
    file_size = OUTPUT_FILE.stat().st_size
    print(f"\n✓ Centroids saved to: {OUTPUT_FILE}")
    print(f"  File size: {file_size / 1024:.1f} KB")
    print(f"  Total zipcodes: {len(sorted_centroids)}")
    
    return sorted_centroids


def generate_typescript_file(centroids):
    """Generate TypeScript constant file from centroids."""
    ts_file = OUTPUT_DIR / "zipcode-centroids-generated.ts"
    
    # Build TypeScript code
    ts_code = '''/**
 * AUTO-GENERATED FILE - Do not edit manually
 * 
 * Generated from US Census Bureau ZCTA boundaries
 * Source: U.S. Census Bureau TIGER/Line Shapefiles 2025
 * License: Public Domain
 * 
 * To regenerate, run: python scripts/generate_zipcode_centroids.py
 */

type ZipcodeCentroid = {
  latitude: number;
  longitude: number;
};

export const ZIPCODE_CENTROIDS: Record<string, ZipcodeCentroid> = {
'''
    
    # Add each zipcode
    for zipcode in sorted(centroids.keys()):
        lat = centroids[zipcode]["latitude"]
        lon = centroids[zipcode]["longitude"]
        ts_code += f'  "{zipcode}": {{ latitude: {lat}, longitude: {lon} }},\n'
    
    ts_code += '''}

export function getZipcodeCentroid(zipcode: string): ZipcodeCentroid | null {
  const normalized = zipcode.trim().substring(0, 5);
  return ZIPCODE_CENTROIDS[normalized] || null;
}

export function hasZipcodeCentroid(zipcode: string): boolean {
  const normalized = zipcode.trim().substring(0, 5);
  return normalized in ZIPCODE_CENTROIDS;
}
'''
    
    with open(ts_file, 'w') as f:
        f.write(ts_code)
    
    file_size = ts_file.stat().st_size / 1024
    print(f"\n✓ TypeScript file generated: {ts_file}")
    print(f"  File size: {file_size:.1f} KB")


def verify_centroids(centroids):
    """Verify sample zipcodes match known locations."""
    test_cases = [
        ("90210", (34.0, -118.4), "Beverly Hills, CA"),
        ("02445", (42.3, -71.3), "Wellesley, MA"),
        ("10001", (40.7, -73.9), "NYC (Chelsea), NY"),
        ("60601", (41.8, -87.6), "Chicago, IL"),
    ]
    
    print("\nVerifying sample zipcodes:")
    all_pass = True
    
    for zipcode, (expected_lat, expected_lon), description in test_cases:
        if zipcode not in centroids:
            print(f"  ✗ {zipcode}: Not found")
            all_pass = False
            continue
        
        actual_lat = centroids[zipcode]["latitude"]
        actual_lon = centroids[zipcode]["longitude"]
        
        # Check if within ~0.5 degrees (roughly 55 km)
        lat_diff = abs(actual_lat - expected_lat)
        lon_diff = abs(actual_lon - expected_lon)
        
        if lat_diff < 0.5 and lon_diff < 0.5:
            print(f"  ✓ {zipcode}: ({actual_lat}, {actual_lon}) - {description}")
        else:
            print(f"  ✗ {zipcode}: Unexpected location ({actual_lat}, {actual_lon})")
            all_pass = False
    
    return all_pass


def main():
    """Main execution."""
    print("=" * 70)
    print("US Census ZCTA Centroid Generator")
    print("=" * 70)
    
    # Step 1: Download
    shapefile = download_and_extract_zcta_shapefile()
    
    # Step 2: Extract centroids
    centroids = extract_centroids(shapefile)
    
    # Step 3: Save JSON
    centroids = save_centroids(centroids)
    
    # Step 4: Generate TypeScript
    generate_typescript_file(centroids)
    
    # Step 5: Verify
    verify_centroids(centroids)
    
    print("\n" + "=" * 70)
    print("✓ Generation complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
