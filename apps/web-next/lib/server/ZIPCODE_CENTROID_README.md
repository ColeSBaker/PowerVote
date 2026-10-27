# Zipcode Centroid Data Generation

## Overview

PowerVote uses US Census Bureau ZIP Code Tabulation Area (ZCTA) boundaries to provide zipcode-to-congressional-district lookups. The system downloads official Census data and extracts the centroid for all ~33,000 US zipcodes for point-in-polygon district matching.

## Data Source

- **Source:** US Census Bureau TIGER/Line Shapefiles 2025
- **URL:** https://www2.census.gov/geo/tiger/TIGER2025/ZCTA520/tl_2025_us_zcta520.zip
- **Format:** ESRI Shapefile
- **Coverage:** 33,791 5-digit zipcodes covering all US territories
- **License:** Public Domain (federal government work)
- **Attribution:** "Source: U.S. Census Bureau TIGER/Line Shapefiles 2025"

## Files

| File | Purpose | Size | Updated |
|------|---------|------|---------|
| [scripts/generate_zipcode_centroids.py](../../../scripts/generate_zipcode_centroids.py) | Python script to download Census data and extract centroids | — | Manual run |
| [lib/server/zipcode-centroids-data.json](zipcode-centroids-data.json) | Raw JSON mapping of zips to centroids | 2.5 MB | Generated |
| [lib/server/zipcode-centroids-generated.ts](zipcode-centroids-generated.ts) | TypeScript exports for server-side lookup | 2.0 MB | Generated |
| [lib/server/zipcode-lookup.ts](zipcode-lookup.ts) | Zipcode lookup API using centroid point-in-polygon matching | — | Code |

## How It Works

1. **Zipcode Lookup API** (`GET /api/v1/zipcode-lookup?zipcode=90210`)
   - Caller provides a 5-digit zipcode
   - API calls `lookupZipcode()` function

2. **Centroid Lookup**
   - Use pre-computed centroid from Census (latitude, longitude)
   - If not available, fall back to Census Geocoder API
   - If both fail, throw clear error (never silently fail)

3. **Point-in-Polygon Matching**
   - Take centroid coordinates
   - Find which congressional district polygon contains the point
   - Extract state & House district (format: `CA-36`)

4. **Senate Seats**
   - Use state code to find Senate seats from data bundle
   - Return array of Senate seat IDs (if any)

5. **Result**
```json
{
  "zipcode": "90210",
  "state": "CA",
  "houseDistrict": "CA-36",
  "senateSeats": ["CA-SEN-C1", "CA-SEN-C2"],
  "latitude": 34.100517,
  "longitude": -118.41463
}
```

## Regenerating Centroid Data

The centroid data is **pre-generated and committed to the repository**. It does NOT regenerate automatically during builds.

To regenerate when Census releases ZCTA updates (typically annually):

```bash
# From root PowerVote directory
python scripts/generate_zipcode_centroids.py

# This will:
# 1. Download the latest Census ZCTA shapefile (~500 MB)
# 2. Extract centroids for all ~33,791 zipcodes
# 3. Generate TypeScript constant file
# 4. Verify sample zipcodes

# Then commit the updated files:
git add apps/web-next/lib/server/zipcode-centroids-*.{ts,json}
git commit -m "Update zipcode centroid data from Census Bureau 2025 ZCTA"
```

Or use the npm helper:

```bash
cd apps/web-next
npm run build:centroids
```

## Performance

- **Lookup Time:** O(1) in-memory Record lookup
- **Data Size:** 2 MB TypeScript constant (fits in bundle)
- **No External APIs:** None required after initial generation
- **Concurrency:** Fully thread-safe (read-only static data)

## Quality

- **Coverage:** 33,791 out of 43,000+ USPS zipcodes (excludes special/administrative codes)
- **Centroids:** Pre-computed by Census Bureau (Interior Point attributes)
- **Accuracy:** Tested against known locations (Beverly Hills, Chicago, NYC, etc.)
- **Validation:** Python script validates all zipcodes before generating

## Maintenance

| Change | Action | Frequency |
|--------|--------|-----------|
| Census Bureau releases new ZCTA | Re-run `generate_zipcode_centroids.py` | Annually (March) |
| Congressional redistricting | No action on centroid data (boundaries don't change) | Once per decade |
| New zipcodes (USPS) | Include automatically in next Census update | N/A |

## Testing

### API Endpoint
```bash
curl http://localhost:3002/api/v1/zipcode-lookup?zipcode=90210
# Returns: {"zipcode":"90210","state":"CA","houseDistrict":"CA-36",...}
```

### Sample Verified Zipcodes
- `90210` → Beverly Hills, CA → `CA-36`
- `02445` → Wellesley, MA → `MA-05`
- `10001` → NYC (Chelsea), NY → `NY-12`
- `60601` → Chicago, IL → `IL-07`
- `93101` → Santa Barbara, CA → `CA-24`
- `78201` → San Antonio, TX → `TX-20`

## Troubleshooting

### "Zipcode not found in database"
- Verify zipcode is valid 5-digit US code
- Check Census Bureau ZCTA coverage (small US territories may not be included)
- Try regenerating data with latest Census boundaries

### "Point does not fall within any congressional district"
- Indicates invalid coordinates for the zipcode
- Verify with an external zipcode tool
- May indicate data quality issue; report if consistent

### Slow Generation Script
- First run downloads 504 MB from Census
- On subsequent runs, reuses cached temp directory
- Processing ~33k zipcodes takes 5-10 minutes
- Using pre-computed Census interior points (fast)

## References

- [Census Bureau TIGER Products](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-html.html)
- [ZCTA Documentation](https://www.census.gov/programs-surveys/geography/guidance/geo-areas/zctas.html)
- [USPS Documentation](https://pe.usps.com/text/pub28/28apc.htm)
- [GIS Data Formats](https://www.ogc.org/standards/gml/)
