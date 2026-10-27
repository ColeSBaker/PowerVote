#!/usr/bin/env python3
"""
Convert Census Bureau shapefile to GeoJSON without GDAL.
Uses struct module to parse binary shapefile format.
"""

import struct
import json
from pathlib import Path

def read_shapefile(shp_path, dbf_path, shx_path=None):
    """Read shapefile components and build GeoJSON."""
    
    # Read the main shapefile (.shp)
    with open(shp_path, 'rb') as f:
        shp_data = f.read()
    
    # Read the attribute database (.dbf)
    with open(dbf_path, 'rb') as f:
        dbf_data = f.read()
    
    # Parse shapefile header
    file_code, = struct.unpack('>i', shp_data[0:4])
    file_length, = struct.unpack('>i', shp_data[24:28])
    shape_type, = struct.unpack('<i', shp_data[32:36])
    
    print(f"Shapefile type: {shape_type} (polygon=5)")
    print(f"File length (16-bit words): {file_length}")
    
    # Parse DBF header to get field definitions
    dbf_headers = parse_dbf_headers(dbf_data)
    print(f"Found {len(dbf_headers)} fields in DBF")
    
    # Parse records from DBF
    dbf_records = parse_dbf_records(dbf_data, dbf_headers)
    print(f"Parsed {len(dbf_records)} records from DBF")
    
    # Parse shapes from SHP
    features = []
    offset = 100  # Skip header (100 bytes = 50 16-bit words)
    record_num = 0
    
    while offset < len(shp_data) and record_num < len(dbf_records):
        # Parse record header
        record_number, = struct.unpack('>i', shp_data[offset:offset+4])
        content_length, = struct.unpack('>i', shp_data[offset+4:offset+8])
        
        # content_length is in 16-bit words, convert to bytes
        record_size = content_length * 2
        
        # Parse record content (shape)
        geometry = parse_polygon_record(shp_data[offset+8:offset+8+record_size])
        
        if geometry:
            properties = dbf_records[record_num]
            feature = {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry
            }
            features.append(feature)
        
        offset += 8 + record_size
        record_num += 1
    
    print(f"Extracted {len(features)} features")
    
    # Build GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    return geojson

def parse_dbf_headers(data):
    """Parse DBF field definitions from header."""
    headers = []
    offset = 32  # Skip DBF header
    
    while offset < len(data):
        field_name_bytes = data[offset:offset+11]
        if field_name_bytes[0] == 0x0D:  # End of headers marker
            break
        
        field_name = field_name_bytes.split(b'\x00')[0].decode('ascii', errors='ignore').strip()
        field_type = chr(data[offset+11])
        field_length = data[offset+16]
        
        if field_name:
            headers.append({
                'name': field_name,
                'type': field_type,
                'length': field_length
            })
        
        offset += 32
    
    return headers

def parse_dbf_records(data, headers):
    """Parse DBF records."""
    records = []
    
    # Find start of records (after header)
    header_length, = struct.unpack('<H', data[8:10])
    offset = header_length
    
    record_length, = struct.unpack('<H', data[10:12])
    
    while offset + record_length <= len(data):
        # First byte indicates if record is deleted
        deleted = data[offset] in (0x2A, ord('*'))
        offset += 1
        
        if not deleted:
            record = {}
            field_offset = 0
            
            for header in headers:
                field_data = data[offset + field_offset:offset + field_offset + header['length']]
                value = parse_dbf_field(field_data, header['type'])
                record[header['name']] = value
                field_offset += header['length']
            
            records.append(record)
        
        offset += record_length - 1
    
    return records

def parse_dbf_field(data, field_type):
    """Parse a single DBF field value."""
    if field_type == 'C':  # Character
        return data.decode('ascii', errors='ignore').strip()
    elif field_type == 'N':  # Numeric
        try:
            return float(data.decode('ascii', errors='ignore').strip())
        except ValueError:
            return None
    elif field_type == 'L':  # Logical
        return data[0] in (ord('T'), ord('Y'), b'T')
    else:
        return data.decode('ascii', errors='ignore').strip()

def parse_polygon_record(data):
    """Parse a polygon record from shapefile."""
    if len(data) < 4:
        return None
    
    record_type, = struct.unpack('<i', data[0:4])
    
    if record_type == 5:  # Polygon
        if len(data) < 44:
            return None
        
        # Parse bounding box (not used)
        # Parse counts
        num_parts, = struct.unpack('<i', data[32:36])
        num_points, = struct.unpack('<i', data[36:40])
        
        offset = 40
        
        # Parse part indices
        part_indices = []
        for i in range(num_parts):
            if offset + 4 <= len(data):
                idx, = struct.unpack('<i', data[offset:offset+4])
                part_indices.append(idx)
                offset += 4
        
        # Parse points
        coordinates = []
        for i in range(num_points):
            if offset + 16 <= len(data):
                x, y = struct.unpack('<dd', data[offset:offset+16])
                coordinates.append([round(x, 4), round(y, 4)])
                offset += 16
        
        if len(part_indices) == 1:
            # Single polygon
            return {
                "type": "Polygon",
                "coordinates": [coordinates]
            }
        else:
            # MultiPolygon
            polygons = []
            for i in range(len(part_indices)):
                start = part_indices[i]
                end = part_indices[i+1] if i+1 < len(part_indices) else len(coordinates)
                if start < len(coordinates) and end <= len(coordinates):
                    polygon = coordinates[start:end]
                    if polygon:
                        # Ensure ring is closed
                        if polygon[0] != polygon[-1]:
                            polygon.append(polygon[0])
                        polygons.append([polygon])
            
            if polygons:
                return {
                    "type": "MultiPolygon",
                    "coordinates": polygons
                }
    
    return None

def main():
    """Convert Census shapefile to GeoJSON."""
    data_dir = Path(__file__).parent.parent / "apps" / "web" / "data"
    
    shp_path = data_dir / "cb_2024_us_state_20m.shp"
    dbf_path = data_dir / "cb_2024_us_state_20m.dbf"
    shx_path = data_dir / "cb_2024_us_state_20m.shx"
    output_path = data_dir / "us-states-census.geojson"
    
    print("Converting Census shapefile to GeoJSON...")
    print(f"Input: {shp_path}")
    
    try:
        geojson = read_shapefile(shp_path, dbf_path, shx_path)
        
        # Write GeoJSON
        with open(output_path, 'w') as f:
            json.dump(geojson, f)
        
        print(f"✓ Successfully created {output_path}")
        print(f"  Features: {len(geojson['features'])}")
        print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
        
        # Sample output
        if geojson['features']:
            sample = geojson['features'][0]
            print(f"  Sample: {sample['properties']}")
        
    except Exception as e:
        print(f"✗ Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
