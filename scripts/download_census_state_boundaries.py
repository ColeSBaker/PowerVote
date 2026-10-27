#!/usr/bin/env python3
"""
Download and convert Census Bureau state boundary files to GeoJSON format.

This script downloads the 2024 Census Bureau Cartographic Boundary Files
(States at 20m resolution) and converts them from Shapefile to GeoJSON format.

Sources:
- Census Bureau Cartographic Boundaries: https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html
- 2024 States (20m): https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip

License: Public Domain (U.S. Census Bureau)
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "apps" / "web" / "data"
OUTPUT_FILE = OUTPUT_DIR / "us-states-census.geojson"

# Census Bureau source
CENSUS_SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"
SHAPEFILE_NAME = "cb_2024_us_state_20m"


def download_shapefile(url: str, temp_dir: Path) -> Path:
    """Download Census Bureau shapefile from URL."""
    logger.info(f"Downloading Census boundaries from {url}")
    zip_path = temp_dir / "census_states.zip"
    
    try:
        urllib.request.urlretrieve(url, zip_path)
        logger.info(f"Downloaded to {zip_path}")
        return zip_path
    except Exception as e:
        logger.error(f"Failed to download: {e}")
        raise


def extract_shapefile(zip_path: Path, temp_dir: Path) -> Path:
    """Extract shapefile from ZIP archive."""
    logger.info(f"Extracting shapefile from {zip_path}")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the .shp file
        shp_files = list(temp_dir.glob("*.shp"))
        if not shp_files:
            raise FileNotFoundError("No .shp file found in archive")
        
        logger.info(f"Extracted shapefile: {shp_files[0]}")
        return shp_files[0]
    except Exception as e:
        logger.error(f"Failed to extract: {e}")
        raise


def convert_shapefile_to_geojson(shp_path: Path, output_path: Path) -> None:
    """
    Convert Shapefile to GeoJSON using ogr2ogr (GDAL).
    
    Requirements: gdal-bin (on Linux) or osgeo4w (on Windows) or brew install gdal (macOS)
    """
    logger.info(f"Converting {shp_path} to GeoJSON")
    
    try:
        # Try using ogr2ogr (part of GDAL)
        cmd = [
            "ogr2ogr",
            "-f", "GeoJSON",
            str(output_path),
            str(shp_path),
            "-t_srs", "EPSG:4326"  # Ensure WGS-84 projection
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Successfully converted to {output_path}")
        
        if result.stdout:
            logger.debug(f"GDAL output: {result.stdout}")
            
    except FileNotFoundError:
        logger.error("ogr2ogr not found. Please install GDAL:")
        logger.error("  Linux: sudo apt-get install gdal-bin")
        logger.error("  macOS: brew install gdal")
        logger.error("  Windows: Install OSGeo4W")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"ogr2ogr conversion failed: {e}")
        logger.error(f"Error: {e.stderr}")
        raise


def validate_geojson(geojson_path: Path) -> bool:
    """Validate GeoJSON file."""
    logger.info(f"Validating GeoJSON: {geojson_path}")
    
    try:
        with open(geojson_path, 'r') as f:
            data = json.load(f)
        
        # Check basic structure
        assert data.get("type") == "FeatureCollection", "Must be a FeatureCollection"
        assert "features" in data, "Must have features property"
        assert isinstance(data["features"], list), "Features must be an array"
        assert len(data["features"]) > 0, "Must have at least one feature"
        
        # Check feature structure
        first_feature = data["features"][0]
        assert first_feature.get("type") == "Feature", "Each item must be a Feature"
        assert "geometry" in first_feature, "Each feature must have geometry"
        assert "properties" in first_feature, "Each feature must have properties"
        
        feature_count = len(data["features"])
        logger.info(f"✓ GeoJSON valid with {feature_count} features")
        
        # Check state count (should be 50 states + DC + 5 territories = ~56 features)
        if feature_count >= 50:
            logger.info(f"✓ Contains {feature_count} geographic features (expected 50+ states)")
        
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return False
    except AssertionError as e:
        logger.error(f"Invalid GeoJSON structure: {e}")
        return False
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return False


def get_file_info(filepath: Path) -> None:
    """Log file size and feature info."""
    if not filepath.exists():
        logger.warning(f"File not found: {filepath}")
        return
    
    size_mb = filepath.stat().st_size / (1024 * 1024)
    logger.info(f"File size: {size_mb:.2f} MB")
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        feature_count = len(data.get("features", []))
        logger.info(f"Feature count: {feature_count}")
        
        # Sample state codes from first few features
        state_codes = [
            f.get("properties", {}).get("STUSPS", "?")
            for f in data.get("features", [])[:5]
        ]
        logger.info(f"Sample state codes: {', '.join(state_codes)}")
    except Exception as e:
        logger.error(f"Could not read GeoJSON info: {e}")


def main():
    """Main function to download and convert Census state boundaries."""
    logger.info("=== Census Bureau State Boundaries Downloader ===")
    
    # Create output directory if needed
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create temporary directory for work
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        logger.info(f"Using temporary directory: {temp_dir}")
        
        try:
            # Step 1: Download
            zip_path = download_shapefile(CENSUS_SHAPEFILE_URL, temp_dir)
            
            # Step 2: Extract
            shp_path = extract_shapefile(zip_path, temp_dir)
            
            # Step 3: Convert to GeoJSON
            convert_shapefile_to_geojson(shp_path, OUTPUT_FILE)
            
            # Step 4: Validate
            if validate_geojson(OUTPUT_FILE):
                logger.info(f"✓ Successfully created {OUTPUT_FILE}")
                get_file_info(OUTPUT_FILE)
                logger.info("\n=== Attribution ===")
                logger.info("Data Source: U.S. Census Bureau")
                logger.info("Dataset: Cartographic Boundary Files (2024)")
                logger.info("License: Public Domain")
                logger.info("URL: https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html")
            else:
                logger.error("GeoJSON validation failed")
                return 1
                
        except Exception as e:
            logger.error(f"Failed to process Census boundaries: {e}")
            return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
