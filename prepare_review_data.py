#!/usr/bin/env python3
"""
Prepare review data from extracted field slip data.

This script:
1. Loads extracted_data_full.json from nemf-photos
2. Looks up locations and names in MO database (if available)
3. Cross-references with existing observations from nemf_inat_combined.csv
4. Creates a review-ready JSON file with prioritization

Usage:
    python prepare_review_data.py [--db] [--output review_data.json]

Options:
    --db        Connect to mo_development database for lookups
    --output    Output file path (default: review_data.json)
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Optional MySQL support
try:
    import mysql.connector
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False


def load_extracted_data(path):
    """Load the extracted field slip data."""
    with open(path) as f:
        return json.load(f)


def load_location_priorities(tsv_path):
    """Load location priority rankings from TSV file.

    The file has section headers that determine priority tier:
    - Top Priority: NYS DEC → tier 1
    - Secondary Priority: NYSOPRHP → tier 2
    - Third: FLLT → tier 3
    - Additional: → tier 4
    - Misc: → tier 5

    Returns dict mapping location name to priority tier (1-5).
    """
    priorities = {}
    if not os.path.exists(tsv_path):
        print(f"Warning: {tsv_path} not found, skipping location priorities")
        return priorities

    current_tier = 99  # Default for locations not in any section

    with open(tsv_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Check for section headers
            if line.startswith('Top Priority'):
                current_tier = 1
                continue
            elif line.startswith('Secondary Priority'):
                current_tier = 2
                continue
            elif line.startswith('Third'):
                current_tier = 3
                continue
            elif line.startswith('Additional'):
                current_tier = 4
                continue
            elif line.startswith('Misc'):
                current_tier = 5
                continue

            # Parse location line
            parts = line.split('\t')
            if len(parts) >= 1 and parts[0]:
                location = parts[0].strip()
                if location:
                    priorities[location] = current_tier

    return priorities


def load_existing_observations(csv_path):
    """Load existing MO observations with field slip codes."""
    existing = {}
    if not os.path.exists(csv_path):
        print(f"Warning: {csv_path} not found, skipping existing observation lookup")
        return existing

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Check field_slip_codes and notes_codes columns
            for col in ['field_slip_codes', 'notes_codes', 'consensus_code']:
                codes = row.get(col, '').strip()
                if codes:
                    for code in codes.split(','):
                        code = code.strip()
                        if code and code.startswith('NEMF-'):
                            if code not in existing:
                                existing[code] = []
                            existing[code].append({
                                'observation_id': row['observation_id'],
                                'url': row['observation_url'],
                                'owner': row['owner'],
                                'inat_id': row.get('inat_id', '')
                            })
    return existing


def connect_to_db():
    """Connect to mo_development database."""
    if not HAS_MYSQL:
        print("mysql-connector-python not installed, skipping database lookups")
        return None

    # Try environment variables first, then defaults from database.yml
    import os
    host = os.environ.get('MO_DB_HOST', 'localhost')
    database = os.environ.get('MO_DB_NAME', 'mo_development')
    user = os.environ.get('MO_DB_USER', 'mo')
    password = os.environ.get('MO_DB_PASSWORD', 'mo')
    socket = os.environ.get('MO_DB_SOCKET', '/tmp/mysql.sock')

    try:
        conn = mysql.connector.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            unix_socket=socket
        )
        return conn
    except Exception as e:
        print(f"Could not connect to database: {e}")
        return None


def lookup_locations(conn, location_names):
    """Look up location IDs from MO database."""
    if not conn or not location_names:
        return {}

    results = {}
    cursor = conn.cursor(dictionary=True, buffered=True)

    for name in location_names:
        if not name:
            continue
        # Try exact match first
        cursor.execute(
            "SELECT id, name, north, south, east, west FROM locations WHERE name = %s",
            (name,)
        )
        row = cursor.fetchone()
        if row:
            results[name] = {'id': row['id'], 'name': row['name'], 'match': 'exact'}
            continue

        # Try partial match
        cursor.execute(
            "SELECT id, name FROM locations WHERE name LIKE %s LIMIT 5",
            (f"%{name}%",)
        )
        rows = cursor.fetchall()
        if rows:
            results[name] = {
                'id': None,
                'candidates': [{'id': r['id'], 'name': r['name']} for r in rows],
                'match': 'partial'
            }
        else:
            results[name] = {'id': None, 'match': 'none'}

    cursor.close()
    return results


def lookup_names(conn, name_strings):
    """Look up name IDs from MO database."""
    if not conn or not name_strings:
        return {}

    results = {}
    cursor = conn.cursor(dictionary=True, buffered=True)

    for name_str in name_strings:
        if not name_str:
            continue
        # Try exact match on text_name
        cursor.execute(
            "SELECT id, text_name, author, deprecated FROM names WHERE text_name = %s",
            (name_str,)
        )
        row = cursor.fetchone()
        if row:
            results[name_str] = {
                'id': row['id'],
                'text_name': row['text_name'],
                'author': row['author'],
                'deprecated': bool(row['deprecated']),
                'match': 'exact'
            }
            continue

        # Try search_name match
        cursor.execute(
            "SELECT id, text_name, author, deprecated FROM names "
            "WHERE search_name LIKE %s LIMIT 5",
            (f"{name_str}%",)
        )
        rows = cursor.fetchall()
        if rows:
            results[name_str] = {
                'id': None,
                'candidates': [{
                    'id': r['id'],
                    'text_name': r['text_name'],
                    'author': r['author']
                } for r in rows],
                'match': 'partial'
            }
        else:
            results[name_str] = {'id': None, 'match': 'none'}

    cursor.close()
    return results


def export_all_names(conn, output_path):
    """Export all non-deprecated names from MO database for autocomplete."""
    if not conn:
        return 0

    cursor = conn.cursor(dictionary=True, buffered=True)

    # Get all non-deprecated names, ordered by text_name for efficient searching
    cursor.execute("""
        SELECT id, text_name, author, `rank`
        FROM names
        WHERE deprecated = 0
        ORDER BY text_name
    """)

    names = []
    for row in cursor:
        names.append({
            'id': row['id'],
            'text_name': row['text_name'],
            'author': row['author'] or '',
            'rank': row['rank']
        })

    cursor.close()

    with open(output_path, 'w') as f:
        json.dump(names, f)

    return len(names)


def export_all_locations(conn, output_path):
    """Export all locations from MO database for autocomplete."""
    if not conn:
        return 0

    cursor = conn.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT id, name
        FROM locations
        ORDER BY name
    """)

    locations = []
    for row in cursor:
        locations.append({
            'id': row['id'],
            'name': row['name']
        })

    cursor.close()

    with open(output_path, 'w') as f:
        json.dump(locations, f)

    return len(locations)


def calculate_priority(image_data, location_lookup, name_lookup, location_priorities):
    """
    Calculate review priority (lower = review first).

    Returns a tuple: (priority_class, location_priority, has_issues)

    Priority classes:
    0. No field code at all
    1. No location data or unknown location
    2. Has location but unknown name
    3. Has null/low confidence data
    4. Complete data with high confidence

    Within each class, images are further sorted by:
    - location_priority (from location-priorities.tsv, lower = first)
    - has_issues (True sorts before False within same location)
    """
    location = image_data.get('Location')
    field_code = image_data.get('Field Slip Code')
    name_id = image_data.get('ID')
    confidence = image_data.get('confidence', {})

    # Get location priority tier (default to 99 if not in priority list)
    loc_priority = location_priorities.get(location, 99) if location else 99

    # Check for low confidence or missing data
    low_confidence = any(
        confidence.get(k) == 'low'
        for k in ['Field Slip Code', 'Date', 'Location', 'ID']
    )
    has_null_data = not all([field_code, image_data.get('Date'), location, name_id])
    has_issues = low_confidence or has_null_data

    # No field code at all - highest priority
    if not field_code:
        return (0, loc_priority, not has_issues)

    # No location or unmatched location
    if not location:
        return (1, loc_priority, not has_issues)
    loc_match = location_lookup.get(location, {}).get('match', 'none')
    if loc_match == 'none':
        return (1, loc_priority, not has_issues)

    # Has location but no/unmatched name
    if not name_id:
        return (2, loc_priority, not has_issues)
    name_match = name_lookup.get(name_id, {}).get('match', 'none')
    if name_match == 'none':
        return (2, loc_priority, not has_issues)

    # Check confidence levels
    if low_confidence:
        return (3, loc_priority, not has_issues)

    # Complete with high confidence
    return (4, loc_priority, not has_issues)


def prepare_review_data(extracted_data, existing_obs, location_lookup, name_lookup,
                        location_priorities):
    """Prepare the review data structure."""
    images = {}

    for item in extracted_data:
        filename = item.get('filename')
        if not filename:
            continue

        field_code = item.get('Field Slip Code')
        location = item.get('Location')
        name_id = item.get('ID')

        # Look up existing observation for this field code
        existing = existing_obs.get(field_code, []) if field_code else []

        # Get location and name lookup results
        loc_info = location_lookup.get(location, {}) if location else {}
        name_info = name_lookup.get(name_id, {}) if name_id else {}

        priority = calculate_priority(item, location_lookup, name_lookup, location_priorities)

        images[filename] = {
            'source': {
                'filename': filename,
                'field_code': field_code,
                'date': item.get('Date'),
                'location': location,
                'location_id': loc_info.get('id'),
                'location_match': loc_info.get('match', 'none'),
                'location_candidates': loc_info.get('candidates', []),
                'name': name_id,
                'name_id': name_info.get('id'),
                'name_match': name_info.get('match', 'none'),
                'name_candidates': name_info.get('candidates', []),
                'confidence': item.get('confidence', {}),
                'notes': item.get('notes'),
                'existing_observations': existing
            },
            'review': {
                'status': None,  # None, 'approved', 'corrected', 'discarded', 'already_on_mo'
                'field_code': None,
                'date': None,
                'location': None,
                'location_id': None,
                'name': None,
                'name_id': None,
                'notes': None,
                'mo_id_type': None,  # 'observation' or 'image'
                'mo_id_value': None,  # The MO ID
                'reviewed_at': None,
                'reviewer': None
            },
            'priority': priority
        }

    return images


def main():
    parser = argparse.ArgumentParser(description='Prepare review data')
    parser.add_argument('--db', action='store_true', help='Connect to MO database')
    parser.add_argument('--output', default='review_data.json', help='Output file')
    args = parser.parse_args()

    # Paths
    base_dir = Path(__file__).parent.parent
    extracted_path = base_dir / 'nemf-photos' / 'extracted_data_full.json'
    csv_path = base_dir / 'nemf-report' / 'nemf_inat_combined.csv'
    priorities_path = base_dir / 'nemf-photos' / 'location-priorities.tsv'
    images_dir = base_dir / 'nemf-photos' / 'scaled-25pct'

    print(f"Loading extracted data from {extracted_path}")
    extracted_data = load_extracted_data(extracted_path)
    print(f"Loaded {len(extracted_data)} images")

    print(f"Loading location priorities from {priorities_path}")
    location_priorities = load_location_priorities(priorities_path)
    print(f"Loaded {len(location_priorities)} location priorities")

    print(f"Loading existing observations from {csv_path}")
    existing_obs = load_existing_observations(csv_path)
    print(f"Found {len(existing_obs)} field codes with existing observations")

    # Collect unique locations and names for lookup
    locations = set(item.get('Location') for item in extracted_data if item.get('Location'))
    names = set(item.get('ID') for item in extracted_data if item.get('ID'))
    print(f"Found {len(locations)} unique locations, {len(names)} unique names")

    # Database lookups
    location_lookup = {}
    name_lookup = {}
    if args.db:
        print("Connecting to database...")
        conn = connect_to_db()
        if conn:
            print("Looking up locations...")
            location_lookup = lookup_locations(conn, locations)
            matched = sum(1 for v in location_lookup.values() if v.get('match') == 'exact')
            print(f"  {matched}/{len(locations)} exact matches")

            print("Looking up names...")
            name_lookup = lookup_names(conn, names)
            matched = sum(1 for v in name_lookup.values() if v.get('match') == 'exact')
            print(f"  {matched}/{len(names)} exact matches")

            # Export all names and locations for autocomplete
            print("Exporting all names for autocomplete...")
            names_path = Path(args.output).parent / 'all_names.json'
            name_count = export_all_names(conn, names_path)
            print(f"  Exported {name_count} non-deprecated names to {names_path}")

            print("Exporting all locations for autocomplete...")
            locations_path = Path(args.output).parent / 'all_locations.json'
            location_count = export_all_locations(conn, locations_path)
            print(f"  Exported {location_count} locations to {locations_path}")

            conn.close()

    print("Preparing review data...")
    images = prepare_review_data(extracted_data, existing_obs, location_lookup, name_lookup,
                                 location_priorities)

    # Count by priority class (first element of priority tuple)
    priority_counts = {}
    for img in images.values():
        p = img['priority'][0]  # First element is priority class
        priority_counts[p] = priority_counts.get(p, 0) + 1

    # Valid NEMF dates
    nemf_dates = [
        '2025-09-17', '2025-09-18', '2025-09-19', '2025-09-20', '2025-09-21'
    ]

    review_data = {
        'metadata': {
            'created': datetime.now().isoformat(),
            'source': str(extracted_path),
            'total_images': len(images),
            'images_dir': str(images_dir),
            'priority_counts': priority_counts,
            'db_lookups': args.db
        },
        'reference': {
            'nemf_dates': nemf_dates,
            'location_lookup': location_lookup,
            'name_lookup': name_lookup,
            'location_priorities': location_priorities
        },
        'images': images,
        'review_summary': {
            'total': len(images),
            'reviewed': 0,
            'approved': 0,
            'corrected': 0,
            'discarded': 0,
            'already_on_mo': 0
        }
    }

    output_path = Path(args.output)
    print(f"Writing review data to {output_path}")
    with open(output_path, 'w') as f:
        json.dump(review_data, f, indent=2)

    print("\nPriority breakdown:")
    for p in sorted(priority_counts.keys()):
        desc = {
            0: "No field code",
            1: "No/unknown location",
            2: "No/unknown name",
            3: "Low confidence data",
            4: "Complete, high confidence"
        }.get(p, "Unknown")
        print(f"  Priority {p} ({desc}): {priority_counts[p]}")

    print(f"\nDone! Run 'python server.py' to start reviewing.")


if __name__ == '__main__':
    main()
