#!/usr/bin/env python3
"""
NEMF Photo Review Server - Multi-user version with authentication and locking.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from threading import Lock

import requests
from flask import Flask, render_template, jsonify, request, send_from_directory, Response

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Global state
review_data = None
data_file = None
images_dir = None
all_names = None
all_locations = None

# Locking state
claims = {}  # {filename: {"user": username, "claimed_at": datetime, "heartbeat": datetime}}
claims_lock = Lock()
CLAIM_TIMEOUT_MINUTES = 10
CLAIM_OVERRIDE_MINUTES = 30

# User configuration
users = {}  # {username: {"password": "...", "api_key": "..."}}


def load_users(path):
    """Load users from JSON file."""
    global users
    if os.path.exists(path):
        with open(path) as f:
            users = json.load(f)
        print(f"Loaded {len(users)} users")
    else:
        print(f"Warning: {path} not found, creating default")
        users = {
            "admin": {"password": "changeme", "api_key": ""}
        }
        save_users(path)


def save_users(path):
    """Save users to JSON file."""
    with open(path, 'w') as f:
        json.dump(users, f, indent=2)


def check_auth(username, password):
    """Verify username/password."""
    if username in users:
        return users[username].get('password') == password
    return False


def authenticate():
    """Send 401 response for authentication."""
    return Response(
        'Authentication required', 401,
        {'WWW-Authenticate': 'Basic realm="NEMF Review"'}
    )


def requires_auth(f):
    """Decorator for routes that require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Get the current authenticated username."""
    auth = request.authorization
    return auth.username if auth else None


# Claim/Locking functions
def cleanup_expired_claims():
    """Remove expired claims."""
    now = datetime.now()
    expired = []
    for filename, claim in claims.items():
        heartbeat = datetime.fromisoformat(claim['heartbeat'])
        if now - heartbeat > timedelta(minutes=CLAIM_TIMEOUT_MINUTES):
            expired.append(filename)
    for filename in expired:
        del claims[filename]


def get_claim(filename):
    """Get current claim on an image, or None if unclaimed."""
    with claims_lock:
        cleanup_expired_claims()
        return claims.get(filename)


def try_claim(filename, username, force=False):
    """
    Try to claim an image.
    Returns: (success, message, claimed_by)
    """
    with claims_lock:
        cleanup_expired_claims()
        now = datetime.now()

        existing = claims.get(filename)
        if existing:
            if existing['user'] == username:
                # Refresh own claim
                existing['heartbeat'] = now.isoformat()
                return (True, "Claim refreshed", username)

            # Check if can override
            claimed_at = datetime.fromisoformat(existing['claimed_at'])
            if force or (now - claimed_at > timedelta(minutes=CLAIM_OVERRIDE_MINUTES)):
                # Override old claim
                claims[filename] = {
                    'user': username,
                    'claimed_at': now.isoformat(),
                    'heartbeat': now.isoformat()
                }
                return (True, f"Claimed (was held by {existing['user']})", username)
            else:
                return (False, f"Claimed by {existing['user']}", existing['user'])

        # Unclaimed, claim it
        claims[filename] = {
            'user': username,
            'claimed_at': now.isoformat(),
            'heartbeat': now.isoformat()
        }
        return (True, "Claimed", username)


def release_claim(filename, username):
    """Release a claim on an image."""
    with claims_lock:
        if filename in claims and claims[filename]['user'] == username:
            del claims[filename]
            return True
    return False


def try_claim_multiple(filenames, username):
    """
    Try to claim multiple images (for linking).
    Returns: (success, failed_claims)
    Where failed_claims is a list of (filename, claimed_by) tuples.
    """
    failed = []
    with claims_lock:
        cleanup_expired_claims()
        now = datetime.now()

        # First check if all can be claimed
        for filename in filenames:
            existing = claims.get(filename)
            if existing and existing['user'] != username:
                claimed_at = datetime.fromisoformat(existing['claimed_at'])
                if now - claimed_at <= timedelta(minutes=CLAIM_OVERRIDE_MINUTES):
                    failed.append((filename, existing['user']))

        if failed:
            return (False, failed)

        # All can be claimed, do it
        for filename in filenames:
            claims[filename] = {
                'user': username,
                'claimed_at': now.isoformat(),
                'heartbeat': now.isoformat()
            }

        return (True, [])


# Data loading functions
def load_data(path):
    """Load review data from JSON file."""
    global review_data, data_file, images_dir, all_names, all_locations
    data_file = path
    with open(path) as f:
        review_data = json.load(f)
    images_dir = Path(review_data['metadata'].get('images_dir', '../nemf-photos/scaled-25pct'))

    # Load all names for autocomplete if available
    names_path = Path(path).parent / 'all_names.json'
    if names_path.exists():
        with open(names_path) as f:
            all_names = json.load(f)
        print(f"Loaded {len(all_names)} names for autocomplete")
    else:
        all_names = None
        print("No all_names.json found - using limited name lookup")

    # Load all locations for autocomplete if available
    locations_path = Path(path).parent / 'all_locations.json'
    if locations_path.exists():
        with open(locations_path) as f:
            all_locations = json.load(f)
        print(f"Loaded {len(all_locations)} locations for autocomplete")
    else:
        all_locations = None
        print("No all_locations.json found - using limited location lookup")

    return review_data


def save_data():
    """Save review data to JSON file."""
    if review_data and data_file:
        # Update summary
        summary = review_data['review_summary']
        summary['reviewed'] = 0
        summary['approved'] = 0
        summary['corrected'] = 0
        summary['discarded'] = 0
        summary['already_on_mo'] = 0

        for img in review_data['images'].values():
            status = img['review'].get('status')
            if status:
                summary['reviewed'] += 1
                if status == 'approved':
                    summary['approved'] += 1
                elif status == 'corrected':
                    summary['corrected'] += 1
                elif status == 'discarded':
                    summary['discarded'] += 1
                elif status == 'already_on_mo':
                    summary['already_on_mo'] += 1

        with open(data_file, 'w') as f:
            json.dump(review_data, f, indent=2)


def get_sorted_images():
    """Get images sorted by priority tuple, then filename."""
    images = review_data['images']
    return sorted(
        images.keys(),
        key=lambda k: (tuple(images[k]['priority']), k)
    )


def get_navigation_context(current_filename):
    """Get prev/next context for navigation."""
    sorted_images = get_sorted_images()
    try:
        idx = sorted_images.index(current_filename)
    except ValueError:
        idx = 0

    return {
        'current_index': idx,
        'total': len(sorted_images),
        'prev': sorted_images[idx - 1] if idx > 0 else None,
        'next': sorted_images[idx + 1] if idx < len(sorted_images) - 1 else None
    }


# Routes
@app.route('/')
@requires_auth
def index():
    """Main review page."""
    return render_template('review.html')


@app.route('/api/whoami')
@requires_auth
def api_whoami():
    """Get current user info."""
    username = get_current_user()
    user_data = users.get(username, {})
    return jsonify({
        'username': username,
        'has_api_key': bool(user_data.get('api_key'))
    })


@app.route('/api/status')
@requires_auth
def api_status():
    """Get overall review status."""
    return jsonify({
        'metadata': review_data['metadata'],
        'summary': review_data['review_summary'],
        'reference': {
            'nemf_dates': review_data['reference']['nemf_dates']
        }
    })


@app.route('/api/images')
@requires_auth
def api_images():
    """Get list of all images with basic info."""
    username = get_current_user()
    sorted_images = get_sorted_images()
    result = []
    for filename in sorted_images:
        img = review_data['images'][filename]
        priority = img['priority']
        claim = get_claim(filename)
        result.append({
            'filename': filename,
            'field_code': img['source'].get('field_code'),
            'location': img['source'].get('location'),
            'priority_class': priority[0] if isinstance(priority, (list, tuple)) else priority,
            'priority': priority,
            'status': img['review'].get('status'),
            'claimed_by': claim['user'] if claim else None,
            'is_mine': claim['user'] == username if claim else False
        })
    return jsonify(result)


@app.route('/api/image/<path:filename>')
@requires_auth
def api_image(filename):
    """Get full data for a specific image and claim it."""
    username = get_current_user()

    if filename not in review_data['images']:
        return jsonify({'error': 'Image not found'}), 404

    # Try to claim the image
    success, message, claimed_by = try_claim(filename, username)

    img = review_data['images'][filename]
    nav = get_navigation_context(filename)

    return jsonify({
        'filename': filename,
        'source': img['source'],
        'review': img['review'],
        'priority': img['priority'],
        'nav': nav,
        'claim': {
            'success': success,
            'message': message,
            'claimed_by': claimed_by,
            'is_mine': claimed_by == username
        }
    })


@app.route('/api/image/<path:filename>/heartbeat', methods=['POST'])
@requires_auth
def api_heartbeat(filename):
    """Refresh claim on an image."""
    username = get_current_user()
    success, message, claimed_by = try_claim(filename, username)
    return jsonify({
        'success': success,
        'message': message,
        'claimed_by': claimed_by
    })


@app.route('/api/image/<path:filename>/release', methods=['POST'])
@requires_auth
def api_release(filename):
    """Release claim on an image."""
    username = get_current_user()
    released = release_claim(filename, username)
    return jsonify({'released': released})


@app.route('/api/image/<path:filename>/review', methods=['POST'])
@requires_auth
def api_review_image(filename):
    """Update review data for an image."""
    username = get_current_user()

    if filename not in review_data['images']:
        return jsonify({'error': 'Image not found'}), 404

    # Verify user has claim
    claim = get_claim(filename)
    if claim and claim['user'] != username:
        return jsonify({
            'error': f'Image is claimed by {claim["user"]}',
            'claimed_by': claim['user']
        }), 409

    data = request.json
    img = review_data['images'][filename]

    # Update review fields
    review = img['review']
    review['status'] = data.get('status', review.get('status'))
    review['field_code'] = data.get('field_code', review.get('field_code'))
    review['date'] = data.get('date', review.get('date'))
    review['location'] = data.get('location', review.get('location'))
    review['location_id'] = data.get('location_id', review.get('location_id'))
    review['name'] = data.get('name', review.get('name'))
    review['name_id'] = data.get('name_id', review.get('name_id'))
    review['notes'] = data.get('notes', review.get('notes'))
    review['linked_images'] = data.get('linked_images', review.get('linked_images', []))
    review['mo_id_type'] = data.get('mo_id_type', review.get('mo_id_type'))
    review['mo_id_value'] = data.get('mo_id_value', review.get('mo_id_value'))
    review['reviewed_at'] = datetime.now().isoformat()
    review['reviewer'] = username  # Track who reviewed

    # Handle bidirectional linking
    linked_images = review.get('linked_images', [])
    for linked_filename in linked_images:
        if linked_filename in review_data['images']:
            linked_img = review_data['images'][linked_filename]
            linked_review = linked_img['review']
            linked_links = linked_review.get('linked_images', [])
            if filename not in linked_links:
                linked_links.append(filename)
                linked_review['linked_images'] = linked_links

    # Propagate approved/corrected data to all linked images
    if review['status'] in ('approved', 'corrected') and linked_images:
        for linked_filename in linked_images:
            if linked_filename in review_data['images']:
                propagate_review_data(filename, linked_filename, review, username)

    # Release claim after successful review
    release_claim(filename, username)

    # Also release claims on linked images
    for linked_filename in linked_images:
        release_claim(linked_filename, username)

    save_data()

    nav = get_navigation_context(filename)
    return jsonify({
        'success': True,
        'review': review,
        'nav': nav,
        'summary': review_data['review_summary']
    })


def propagate_review_data(source_filename, target_filename, source_review, username):
    """Propagate review data from source to target image."""
    target_img = review_data['images'][target_filename]
    target_review = target_img['review']

    # Only propagate if target hasn't been reviewed yet
    if target_review.get('status'):
        return

    # Copy the review data
    target_review['field_code'] = source_review.get('field_code')
    target_review['date'] = source_review.get('date')
    target_review['location'] = source_review.get('location')
    target_review['location_id'] = source_review.get('location_id')
    target_review['name'] = source_review.get('name')
    target_review['name_id'] = source_review.get('name_id')
    target_review['status'] = 'approved'
    target_review['reviewed_at'] = datetime.now().isoformat()
    target_review['reviewer'] = f'{username}:propagated_from:{source_filename}'

    linked = target_review.get('linked_images', [])
    if source_filename not in linked:
        linked.append(source_filename)
    target_review['linked_images'] = linked


@app.route('/api/link/<path:filename>', methods=['POST'])
@requires_auth
def api_link_image(filename):
    """Link an image to the current image, claiming both."""
    username = get_current_user()
    data = request.json
    target_filename = data.get('target')

    if not target_filename:
        return jsonify({'error': 'Target filename required'}), 400

    if filename not in review_data['images']:
        return jsonify({'error': 'Source image not found'}), 404

    if target_filename not in review_data['images']:
        return jsonify({'error': 'Target image not found'}), 404

    # Try to claim both images
    success, failed = try_claim_multiple([filename, target_filename], username)

    if not success:
        failed_info = [{'filename': f, 'claimed_by': u} for f, u in failed]
        return jsonify({
            'error': 'Could not claim all images',
            'failed_claims': failed_info
        }), 409

    return jsonify({
        'success': True,
        'message': f'Claimed both {filename} and {target_filename}'
    })


@app.route('/api/next-unreviewed')
@requires_auth
def api_next_unreviewed():
    """Get the next unreviewed image by priority."""
    sorted_images = get_sorted_images()
    for filename in sorted_images:
        if not review_data['images'][filename]['review'].get('status'):
            return jsonify({'filename': filename})
    return jsonify({'filename': None, 'message': 'All images reviewed!'})


@app.route('/api/lookup/location')
@requires_auth
def api_lookup_location():
    """Search for location matches."""
    query = request.args.get('q', '')
    if not query or len(query) < 2:
        return jsonify([])

    results = []
    query_lower = query.lower()

    if all_locations:
        for loc in all_locations:
            if query_lower in loc['name'].lower():
                results.append({
                    'name': loc['name'],
                    'id': loc['id'],
                    'match': 'exact'
                })
                if len(results) >= 10:
                    break
    else:
        lookup = review_data['reference'].get('location_lookup', {})
        for loc_name, info in lookup.items():
            if query_lower in loc_name.lower():
                if info.get('id'):
                    results.append({
                        'name': loc_name,
                        'id': info['id'],
                        'match': info['match']
                    })
                elif info.get('candidates'):
                    for c in info['candidates']:
                        results.append({
                            'name': c['name'],
                            'id': c['id'],
                            'match': 'candidate'
                        })

    return jsonify(results[:10])


@app.route('/api/lookup/name')
@requires_auth
def api_lookup_name():
    """Search for name matches."""
    query = request.args.get('q', '')
    if not query or len(query) < 2:
        return jsonify([])

    results = []
    query_lower = query.lower()

    if all_names:
        for name in all_names:
            if query_lower in name['text_name'].lower():
                results.append({
                    'text_name': name['text_name'],
                    'id': name['id'],
                    'author': name.get('author', ''),
                    'match': 'exact'
                })
                if len(results) >= 10:
                    break
    else:
        lookup = review_data['reference'].get('name_lookup', {})
        for name_str, info in lookup.items():
            if query_lower in name_str.lower():
                if info.get('id'):
                    results.append({
                        'text_name': info.get('text_name', name_str),
                        'id': info['id'],
                        'author': info.get('author', ''),
                        'match': info['match']
                    })
                elif info.get('candidates'):
                    for c in info['candidates']:
                        results.append({
                            'text_name': c['text_name'],
                            'id': c['id'],
                            'author': c.get('author', ''),
                            'match': 'candidate'
                        })

    return jsonify(results[:10])


@app.route('/api/lookup/existing_observations')
@requires_auth
def api_lookup_existing_observations():
    """Look up existing MO observations by field code."""
    code = request.args.get('code', '')
    if not code:
        return jsonify([])

    # Search through all images for matching field codes
    seen = set()
    results = []
    for img in review_data['images'].values():
        src = img.get('source', {})
        if src.get('field_code') == code:
            for obs in src.get('existing_observations', []):
                # Deduplicate by observation_id
                obs_id = obs.get('observation_id')
                if obs_id and obs_id not in seen:
                    seen.add(obs_id)
                    results.append(obs)

    return jsonify(results)


@app.route('/api/verify_mo_id')
@requires_auth
def api_verify_mo_id():
    """Verify that an MO observation or image ID exists."""
    id_type = request.args.get('type', '')
    id_value = request.args.get('id', '')

    if not id_type or not id_value:
        return jsonify({'error': 'Missing type or id'}), 400

    if id_type not in ('observation', 'image'):
        return jsonify({'error': 'Invalid type'}), 400

    try:
        # Call MO API to verify the ID exists
        if id_type == 'observation':
            url = f'https://mushroomobserver.org/api2/observations/{id_value}'
        else:
            url = f'https://mushroomobserver.org/api2/images/{id_value}'

        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            return jsonify({'exists': True, 'id': id_value, 'type': id_type})
        elif response.status_code == 404:
            return jsonify({'exists': False, 'id': id_value, 'type': id_type})
        else:
            return jsonify({
                'error': f'MO API returned status {response.status_code}'
            }), 500

    except requests.Timeout:
        return jsonify({'error': 'Request to MO API timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to verify: {str(e)}'}), 500


@app.route('/api/adjacent/<path:filename>')
@requires_auth
def api_adjacent(filename):
    """Get adjacent images (for finding related images like closeups)."""
    username = get_current_user()
    sorted_filenames = sorted(review_data['images'].keys())
    try:
        idx = sorted_filenames.index(filename)
    except ValueError:
        return jsonify([])

    start = max(0, idx - 5)
    end = min(len(sorted_filenames), idx + 6)

    result = []
    for i in range(start, end):
        fn = sorted_filenames[i]
        img = review_data['images'][fn]
        claim = get_claim(fn)
        result.append({
            'filename': fn,
            'field_code': img['source'].get('field_code'),
            'is_current': fn == filename,
            'claimed_by': claim['user'] if claim else None,
            'is_mine': claim['user'] == username if claim else False
        })

    return jsonify(result)


@app.route('/images/<path:filename>')
@requires_auth
def serve_image(filename):
    """Serve an image file."""
    return send_from_directory(images_dir, filename)


# User settings
@app.route('/api/settings', methods=['GET'])
@requires_auth
def api_get_settings():
    """Get current user settings."""
    username = get_current_user()
    user_data = users.get(username, {})
    return jsonify({
        'username': username,
        'api_key': user_data.get('api_key', '')
    })


@app.route('/api/settings', methods=['POST'])
@requires_auth
def api_update_settings():
    """Update current user settings."""
    username = get_current_user()
    data = request.json

    if username not in users:
        return jsonify({'error': 'User not found'}), 404

    if 'api_key' in data:
        users[username]['api_key'] = data['api_key']

    if 'password' in data and data['password']:
        users[username]['password'] = data['password']

    # Save users file
    users_path = Path(data_file).parent / 'users.json'
    save_users(users_path)

    return jsonify({'success': True})


def create_app(data_path='review_data.json', users_path='users.json'):
    """Factory function to create and configure the app."""
    load_data(data_path)
    load_users(users_path)
    return app


def main():
    import argparse
    parser = argparse.ArgumentParser(description='NEMF Photo Review Server')
    parser.add_argument('--port', type=int, default=5001, help='Port to run on')
    parser.add_argument('--data', default='review_data.json', help='Review data file')
    parser.add_argument('--users', default='users.json', help='Users file')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    args = parser.parse_args()

    if not os.path.exists(args.data):
        print(f"Error: {args.data} not found")
        sys.exit(1)

    print(f"Loading data from {args.data}...")
    load_data(args.data)

    users_path = Path(args.data).parent / args.users
    print(f"Loading users from {users_path}...")
    load_users(users_path)

    summary = review_data['review_summary']
    print(f"Total images: {summary['total']}")
    print(f"Already reviewed: {summary['reviewed']}")

    print(f"\nStarting server at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop\n")

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
