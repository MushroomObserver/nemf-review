#!/usr/bin/env python3
"""
NEMF Photo Review Server - Multi-user version with authentication and locking.
"""

import csv
import json
import os
import sys
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from threading import Lock

# Add app directory to path for imports
# This allows importing mo_api_client from the same directory
# For a production package, this would be handled by proper package structure
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from flask import Flask, render_template, jsonify, request, send_from_directory, Response, session

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Global state
review_data = None
data_file = None
images_dir = None
all_names = None
all_locations = None
foray_dates = None  # {location_name: date_string}
mo_base_url = 'https://mushroomobserver.org'  # MO API base URL (configurable)

# Locking state
claims = {}  # {filename: {"user": username, "claimed_at": datetime, "heartbeat": datetime}}
claims_lock = Lock()

# View history per user (most recent first)
view_history = {}  # {username: [filename1, filename2, ...]}
view_history_lock = Lock()
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


# Helper functions for MO API response parsing
def extract_image_id(response):
    """
    Extract image ID from MO API response.

    MO API returns {"results": [1234]} where 1234 is the image ID.
    Handles different response formats defensively.
    """
    from mo_api_client import MOAPIError

    if 'results' in response and isinstance(response['results'], list):
        if not response['results']:
            raise MOAPIError("Empty results array in image upload response")
        return response['results'][0]  # ID is directly in array
    elif 'id' in response:
        return response['id']
    else:
        raise MOAPIError(f"Could not extract image ID from response: {response}")


def extract_observation_id(response):
    """
    Extract observation ID from MO API response.

    MO API returns {"results": [{"id": 123, ...}]} for observations.
    Handles both object and integer formats.
    """
    from mo_api_client import MOAPIError

    if 'results' in response and isinstance(response['results'], list):
        if not response['results']:
            raise MOAPIError("Empty results array in observation response")
        first_result = response['results'][0]
        if isinstance(first_result, dict):
            return first_result['id']
        else:
            return first_result  # In case it's just an ID
    elif 'id' in response:
        return response['id']
    else:
        raise MOAPIError(f"Could not extract observation ID from response: {response}")


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


def add_to_view_history(filename, username):
    """Add image to user's view history (most recent first)."""
    with view_history_lock:
        if username not in view_history:
            view_history[username] = []

        history = view_history[username]

        # Remove if already in history
        if filename in history:
            history.remove(filename)

        # Add to front
        history.insert(0, filename)

        # Keep history reasonable size (last 100 views)
        if len(history) > 100:
            view_history[username] = history[:100]


def get_view_history(username):
    """Get user's view history (most recent first)."""
    with view_history_lock:
        return view_history.get(username, []).copy()


def is_resolved(status):
    """Check if an image status is considered resolved."""
    return status in ('already_on_mo', 'excluded') or status is not None


def is_all_resolved():
    """Check if all images are resolved."""
    for img in review_data['images'].values():
        status = img['review'].get('status')
        mo_obs_id = img['review'].get('mo_observation_id')
        # Resolved if: has status (already_on_mo/excluded) or uploaded to MO
        if not status and not mo_obs_id:
            return False
    return True


def get_next_unreviewed_for_user(username, current_filename=None, exclude_history=None):
    """
    Get next unreviewed image for user in priority order.
    Skips images locked by other users.
    Prioritizes user's own soft-locked images first.
    If current_filename is provided, starts searching after that image.
    If exclude_history is provided, skips images in that list.
    """
    import sys
    sorted_images = get_sorted_images()

    # If current_filename provided, start searching after it
    start_index = 0
    if current_filename and current_filename in sorted_images:
        start_index = sorted_images.index(current_filename) + 1

    sys.stderr.write(f"DEBUG: get_next_unreviewed_for_user: current={current_filename}, start_index={start_index}\n")
    sys.stderr.write(f"DEBUG: Total sorted images: {len(sorted_images)}\n")
    if start_index < len(sorted_images):
        sys.stderr.write(f"DEBUG: Image at start_index ({start_index}): {sorted_images[start_index]}\n")
    sys.stderr.write(f"DEBUG: exclude_history: {len(exclude_history) if exclude_history else 0} images\n")
    sys.stderr.flush()

    # Create search list (from start_index onwards, then wrap around)
    # Exclude current_filename from the search to avoid returning the same image
    search_list = sorted_images[start_index:] + sorted_images[:start_index]
    if current_filename:
        search_list = [f for f in search_list if f != current_filename]

    sys.stderr.write(f"DEBUG: search_list length: {len(search_list)}, first 5: {search_list[:5]}\n")
    sys.stderr.flush()

    # Exclude images already in history to prevent cycling
    if exclude_history:
        search_list = [f for f in search_list if f not in exclude_history]
        sys.stderr.write(f"DEBUG: After excluding history: {len(search_list)} images remaining\n")
        sys.stderr.flush()

    # Look for unreviewed/unresolved images not locked by others
    checked = 0
    skipped_resolved = 0
    for filename in search_list:
        img = review_data['images'][filename]
        status = img['review'].get('status')
        mo_obs_id = img['review'].get('mo_observation_id')
        resolved = status in ('already_on_mo', 'excluded', 'approved', 'corrected') or mo_obs_id

        if not resolved:
            claim = get_claim(filename)
            if not claim or claim['user'] == username:
                sys.stderr.write(f"DEBUG: Found next unreviewed: {filename} (checked {checked} images, skipped {skipped_resolved} resolved)\n")
                sys.stderr.flush()
                return filename
        else:
            skipped_resolved += 1
        checked += 1

    sys.stderr.write(f"DEBUG: No unreviewed images found (checked {checked} images)\n")
    sys.stderr.flush()
    return None


# Data loading functions
def load_data(path, images_directory=None):
    """Load review data from JSON file."""
    global review_data, data_file, images_dir, all_names, all_locations, foray_dates
    data_file = path
    with open(path) as f:
        review_data = json.load(f)

    # Use provided images_directory, or default to data/images relative to data file
    if images_directory:
        images_dir = Path(images_directory).resolve()
    else:
        # Default to 'images' subdirectory next to the data file
        images_dir = (Path(path).parent / 'images').resolve()

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

    # Load foray dates from CSV if available
    forays_path = Path(path).parent / 'forays.csv'
    if forays_path.exists():
        foray_dates = {}
        with open(forays_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                location = row['Site Name'].strip()
                date_str = row['Date'].strip()
                # Convert "9/18" format to "2024-09-18" (NEMF 2024 dates)
                if '/' in date_str:
                    month, day = date_str.split('/')
                    full_date = f"2024-{int(month):02d}-{int(day):02d}"
                    foray_dates[location] = full_date
        print(f"Loaded {len(foray_dates)} foray dates")
    else:
        foray_dates = None
        print("No forays.csv found - date auto-fill disabled")

    return review_data


def save_data():
    """Save review data to JSON file."""
    if review_data and data_file:
        # Update summary
        summary = review_data['review_summary']
        summary['reviewed'] = 0
        summary['approved'] = 0
        summary['corrected'] = 0
        summary['excluded'] = 0
        summary['already_on_mo'] = 0

        for img in review_data['images'].values():
            status = img['review'].get('status')
            if status:
                summary['reviewed'] += 1
                if status == 'approved':
                    summary['approved'] += 1
                elif status == 'corrected':
                    summary['corrected'] += 1
                elif status == 'excluded':
                    summary['excluded'] += 1
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
    return render_template('review.html', mo_base_url=mo_base_url)


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
    """Get full data for a specific image and optionally claim it."""
    username = get_current_user()

    if filename not in review_data['images']:
        return jsonify({'error': 'Image not found'}), 404

    # Track view history only if requested (to avoid adding Back/Forward nav to history)
    add_to_history = request.args.get('add_to_history', 'false').lower() == 'true'
    if add_to_history:
        add_to_view_history(filename, username)

    # Only claim the image if actually loading it for review (not peeking)
    if add_to_history:
        success, message, claimed_by = try_claim(filename, username)
    else:
        # Just check current claim status without claiming
        claim = get_claim(filename)
        success = True
        message = ''
        claimed_by = claim['user'] if claim else None

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


@app.route('/api/navigation/<path:filename>')
@requires_auth
def api_navigation(filename):
    """Get navigation info for current image based on user's view history."""
    import sys
    username = get_current_user()
    history = get_view_history(username)

    sys.stderr.write(f"\n{'='*80}\n")
    sys.stderr.write(f"DEBUG: /api/navigation called for {filename} by {username}\n")
    sys.stderr.write(f"DEBUG: History length: {len(history)}, current in history: {filename in history}\n")
    sys.stderr.flush()

    # Find current position in history
    current_index = history.index(filename) if filename in history else -1

    # Determine navigation options
    can_go_back = current_index >= 0 and current_index < len(history) - 1
    can_go_forward_in_history = current_index > 0

    # Get back/forward targets
    back_target = history[current_index + 1] if can_go_back else None
    forward_target_history = history[current_index - 1] if can_go_forward_in_history else None

    # Check if there's an unreviewed image ahead in history
    next_unreviewed_in_history = None
    if current_index >= 0:
        for i in range(current_index - 1, -1, -1):
            hist_filename = history[i]
            img = review_data['images'].get(hist_filename)
            if img:
                status = img['review'].get('status')
                mo_obs_id = img['review'].get('mo_observation_id')
                resolved = status in ('already_on_mo', 'excluded', 'approved', 'corrected') or mo_obs_id
                if not resolved:
                    next_unreviewed_in_history = hist_filename
                    break

    # Get next unreviewed image after current (priority order, skip others' locks)
    # Don't exclude history - the resolved check already handles skipping reviewed images
    next_unreviewed_priority = get_next_unreviewed_for_user(username, current_filename=filename)

    # Determine next unreviewed target (prefer history, then priority)
    next_unreviewed = next_unreviewed_in_history or next_unreviewed_priority
    next_unreviewed_mode = 'history' if next_unreviewed_in_history else 'priority'

    # Check if all resolved
    all_resolved = is_all_resolved()

    sys.stderr.write(f"DEBUG: next_unreviewed_in_history: {next_unreviewed_in_history}\n")
    sys.stderr.write(f"DEBUG: next_unreviewed_priority: {next_unreviewed_priority}\n")
    sys.stderr.write(f"DEBUG: next_unreviewed (final): {next_unreviewed} (mode: {next_unreviewed_mode})\n")
    sys.stderr.flush()

    return jsonify({
        'current_index': current_index,
        'history_length': len(history),
        'can_go_back': can_go_back,
        'can_go_forward': can_go_forward_in_history,
        'back_target': back_target,
        'forward_target': forward_target_history,
        'next_unreviewed': next_unreviewed,
        'next_unreviewed_mode': next_unreviewed_mode,
        'all_resolved': all_resolved
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
    review['mo_observation_id'] = data.get('mo_observation_id', review.get('mo_observation_id'))
    review['mo_image_id'] = data.get('mo_image_id', review.get('mo_image_id'))
    review['mo_observation_url'] = data.get('mo_observation_url', review.get('mo_observation_url'))
    review['field_locks'] = data.get('field_locks', review.get('field_locks', {}))
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

    # Propagate status to all linked images (for any resolved status)
    if review['status'] in ('approved', 'corrected', 'already_on_mo', 'excluded') and linked_images:
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
    target_review['mo_observation_id'] = source_review.get('mo_observation_id')
    target_review['mo_id_type'] = source_review.get('mo_id_type')
    target_review['mo_id_value'] = source_review.get('mo_id_value')
    # Use source status if it's a final status, otherwise default to 'approved'
    if source_review.get('status') in ('already_on_mo', 'excluded'):
        target_review['status'] = source_review.get('status')
    else:
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

    # Add bidirectional link
    source_img = review_data['images'][filename]
    source_review = source_img['review']
    source_linked = source_review.get('linked_images', [])
    if target_filename not in source_linked:
        source_linked.append(target_filename)
        source_review['linked_images'] = source_linked

    target_img = review_data['images'][target_filename]
    target_review = target_img['review']
    target_linked = target_review.get('linked_images', [])
    if filename not in target_linked:
        target_linked.append(filename)
        target_review['linked_images'] = target_linked

    save_data()

    return jsonify({
        'success': True,
        'message': f'Claimed both {filename} and {target_filename}',
        'linked_images': source_linked
    })


@app.route('/api/unlink/<path:filename>', methods=['POST'])
@requires_auth
def api_unlink_image(filename):
    """Unlink an image from the current image."""
    username = get_current_user()
    data = request.json
    target_filename = data.get('target')

    if not target_filename:
        return jsonify({'error': 'Target filename required'}), 400

    if filename not in review_data['images']:
        return jsonify({'error': 'Source image not found'}), 404

    if target_filename not in review_data['images']:
        return jsonify({'error': 'Target image not found'}), 404

    # Verify user has claim on current image
    claim = get_claim(filename)
    if not claim or claim['user'] != username:
        return jsonify({
            'error': 'You must have claimed this image to unlink'
        }), 403

    # Remove bidirectional link
    source_img = review_data['images'][filename]
    source_review = source_img['review']
    source_linked = source_review.get('linked_images', [])
    if target_filename in source_linked:
        source_linked.remove(target_filename)
        source_review['linked_images'] = source_linked

    target_img = review_data['images'][target_filename]
    target_review = target_img['review']
    target_linked = target_review.get('linked_images', [])
    if filename in target_linked:
        target_linked.remove(filename)
        target_review['linked_images'] = target_linked

    save_data()

    return jsonify({
        'success': True,
        'message': f'Unlinked {filename} from {target_filename}',
        'linked_images': source_linked
    })


@app.route('/api/next-unreviewed')
@requires_auth
def api_next_unreviewed():
    """Get the next unreviewed image for this user (skips others' locks)."""
    import sys
    username = get_current_user()

    sys.stderr.write(f"\n{'='*80}\n")
    sys.stderr.write(f"DEBUG: /api/next-unreviewed called by {username}\n")
    sys.stderr.flush()

    filename = get_next_unreviewed_for_user(username)

    sys.stderr.write(f"DEBUG: get_next_unreviewed_for_user returned: {filename}\n")
    sys.stderr.flush()

    if filename:
        return jsonify({'filename': filename})
    else:
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


@app.route('/api/lookup/foray_date')
@requires_auth
def api_lookup_foray_date():
    """Look up foray date by location name."""
    location = request.args.get('location', '')
    if not location or not foray_dates:
        return jsonify({'date': None})

    # Try exact match first
    if location in foray_dates:
        return jsonify({'date': foray_dates[location]})

    # Try case-insensitive match
    location_lower = location.lower()
    for foray_loc, date in foray_dates.items():
        if foray_loc.lower() == location_lower:
            return jsonify({'date': date})

    return jsonify({'date': None})


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


@app.route('/api/lookup/field_slip_observation')
@requires_auth
def api_lookup_field_slip_observation():
    """Look up observation ID for a field slip code using MO API."""
    code = request.args.get('code', '')
    if not code:
        return jsonify({'error': 'Missing code parameter'}), 400

    try:
        from mo_api_client import MOAPIClient, MOAPIError
        import sys

        username = get_current_user()
        user_config = users.get(username)
        if not user_config:
            return jsonify({'error': 'User not found'}), 401

        client = MOAPIClient(
            base_url=mo_base_url,
            api_key=user_config.get('api_key')
        )

        sys.stderr.write(f"Looking up field slip: {code} with detail=low\n")
        sys.stderr.flush()

        field_slip = client.get_field_slip_by_code(code, detail='low')
        sys.stderr.write(f"Field slip response type: {type(field_slip)}\n")
        sys.stderr.write(f"Field slip response: {field_slip}\n")
        sys.stderr.flush()

        if field_slip:
            # Try multiple possible field names for observation_id
            observation_id = None

            if isinstance(field_slip, dict):
                # Try common field names
                observation_id = (
                    field_slip.get('observation_id') or
                    field_slip.get('observation') or
                    field_slip.get('obs_id')
                )

                sys.stderr.write(f"Extracted observation_id: {observation_id}\n")
                sys.stderr.write(f"Field slip keys: {list(field_slip.keys())}\n")
                sys.stderr.flush()
            else:
                sys.stderr.write(f"Field slip response is not a dict, it's a {type(field_slip)}\n")
                sys.stderr.flush()

            if observation_id:
                return jsonify({
                    'observation_id': observation_id,
                    'field_slip_code': code
                })

        sys.stderr.write(f"No observation_id found for field slip {code}\n")
        sys.stderr.flush()

        return jsonify({
            'observation_id': None,
            'message': 'Field slip not linked to an observation',
            'debug_data': field_slip if field_slip else None
        })

    except MOAPIError as e:
        sys.stderr.write(f"MOAPIError in field slip lookup: {e}\n")
        sys.stderr.flush()
        return jsonify({'error': f'MO API error: {str(e)}'}), 500
    except Exception as e:
        import traceback
        sys.stderr.write(f"Exception in field slip lookup: {e}\n")
        traceback.print_exc()
        sys.stderr.flush()
        return jsonify({'error': f'Lookup failed: {str(e)}'}), 500


@app.route('/api/verify_mo_id')
@requires_auth
def api_verify_mo_id():
    """Verify that an MO observation or field slip exists."""
    id_type = request.args.get('type', '')
    id_value = request.args.get('id', '')

    print(f"DEBUG: Verifying {id_type} = {id_value}")

    if not id_type or not id_value:
        return jsonify({'error': 'Missing type or id'}), 400

    if id_type not in ('observation', 'field_slip'):
        return jsonify({'error': 'Invalid type'}), 400

    try:
        from mo_api_client import MOAPIClient, MOAPIError

        if id_type == 'observation':
            # Call MO API to verify the observation exists
            url = f'{mo_base_url}/api2/observations/{id_value}'
            response = requests.get(
                url,
                timeout=10,
                headers={'Accept': 'application/json'}
            )

            if response.status_code == 200:
                return jsonify({'exists': True, 'id': id_value, 'type': id_type})
            elif response.status_code == 404:
                return jsonify({'exists': False, 'id': id_value, 'type': id_type})
            else:
                return jsonify({
                    'error': f'MO API returned status {response.status_code}'
                }), 500

        elif id_type == 'field_slip':
            # Use MOApiClient to check if field slip exists
            username = get_current_user()
            user_config = users.get(username)
            if not user_config:
                return jsonify({'error': 'User not found'}), 401

            try:
                print(f"DEBUG: Creating MOAPIClient for field_slip check")
                client = MOAPIClient(
                    base_url=mo_base_url,
                    api_key=user_config.get('api_key')
                )

                print(f"DEBUG: Calling get_field_slip_by_code({id_value})")
                field_slip = client.get_field_slip_by_code(id_value)
                print(f"DEBUG: Field slip result: {field_slip}")

                if field_slip:
                    print(f"DEBUG: Field slip exists, returning True")
                    return jsonify({'exists': True, 'id': id_value, 'type': id_type})
                else:
                    print(f"DEBUG: Field slip not found, returning False")
                    return jsonify({'exists': False, 'id': id_value, 'type': id_type})
            except MOAPIError as e:
                print(f"ERROR: Field slip verification error: {e}")
                return jsonify({'error': f'Field slip API error: {str(e)}'}), 500

    except requests.Timeout:
        print(f"ERROR: Request timeout")
        return jsonify({'error': 'Request to MO API timed out'}), 504
    except requests.RequestException as e:
        print(f"ERROR: Request exception: {e}")
        return jsonify({'error': f'Failed to verify: {str(e)}'}), 500
    except MOAPIError as e:
        print(f"ERROR: MOAPIError: {e}")
        return jsonify({'error': f'MO API error: {str(e)}'}), 500
    except Exception as e:
        print(f"ERROR: Unexpected exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Verification failed: {str(e)}'}), 500


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
    import sys
    sys.stderr.write(f"DEBUG: serve_image called with filename: {filename}\n")
    sys.stderr.write(f"DEBUG: images_dir = {images_dir}\n")
    sys.stderr.write(f"DEBUG: images_dir type = {type(images_dir)}\n")
    sys.stderr.write(f"DEBUG: images_dir exists = {images_dir.exists() if hasattr(images_dir, 'exists') else 'N/A'}\n")
    sys.stderr.write(f"DEBUG: full path would be: {images_dir / filename if hasattr(images_dir, '__truediv__') else 'N/A'}\n")
    sys.stderr.flush()
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


# Phase 4 & 5: MO API Integration Routes
@app.route('/api/mo/add_to_existing', methods=['POST'])
@requires_auth
def api_mo_add_to_existing():
    """
    Add image to existing observation (Phase 4).

    Request body:
    {
        "filename": "IMG_1234.jpg",
        "observation_id": 123456,
        "field_code": "NEMF-12345",
        "project_id": 42
    }
    """
    from mo_api_client import MOAPIClient, MOAPIError, MOAPIConflictError

    username = get_current_user()
    user_data = users.get(username, {})

    # Ensure user_data is a dictionary
    if not isinstance(user_data, dict):
        return jsonify({
            'error': 'Invalid user configuration. Please check users.json format.'
        }), 500

    api_key = user_data.get('api_key')

    if not api_key:
        return jsonify({
            'error': 'No API key configured. Please set your API key in Settings.'
        }), 400

    data = request.json
    filename = data.get('filename')
    observation_id = data.get('observation_id')
    field_code = data.get('field_code')
    project_id = data.get('project_id')

    if not filename or not observation_id:
        return jsonify({'error': 'filename and observation_id required'}), 400

    # Validate observation_id is a positive integer
    try:
        observation_id = int(observation_id)
        if observation_id <= 0:
            raise ValueError("observation_id must be positive")
    except (TypeError, ValueError) as e:
        return jsonify({'error': f'Invalid observation_id: must be a positive integer'}), 400

    if filename not in review_data['images']:
        return jsonify({'error': 'Image not found'}), 404

    # Verify user has claim
    claim = get_claim(filename)
    if claim and claim['user'] != username:
        return jsonify({
            'error': f'Image is claimed by {claim["user"]}'
        }), 409

    # Get linked images
    img = review_data['images'][filename]
    linked_images = img['review'].get('linked_images', [])
    all_images = [filename] + linked_images

    import sys
    sys.stderr.write(f"Phase 4: Main image: {filename}\n")
    sys.stderr.write(f"Phase 4: Linked images: {linked_images}\n")
    sys.stderr.write(f"Phase 4: All images to upload: {all_images}\n")
    sys.stderr.flush()

    try:
        client = MOAPIClient(api_key, base_url=mo_base_url)

        # Step 1: Verify observation exists
        if not client.verify_observation_exists(observation_id):
            return jsonify({
                'error': f'Observation {observation_id} not found on MO'
            }), 404

        uploaded_images = []

        # Step 2: Upload all images (main + linked)
        for img_filename in all_images:
            sys.stderr.write(f"Phase 4: Processing image: {img_filename}\n")
            sys.stderr.flush()
            if img_filename not in review_data['images']:
                continue

            img_path = images_dir / img_filename
            sys.stderr.write(f"Phase 4: Uploading {img_filename} from path: {img_path}\n")
            sys.stderr.flush()

            copyright_holder = username
            upload_result = client.upload_image(
                str(img_path),
                copyright_holder=copyright_holder,
                notes=f"Field slip: {field_code}" if field_code else "",
                original_name=img_filename
            )

            # Extract image ID from response
            img_id = extract_image_id(upload_result)
            sys.stderr.write(f"Phase 4: Uploaded {img_filename} -> Image ID: {img_id}\n")
            sys.stderr.flush()

            # Add image to observation
            client.add_image_to_observation(observation_id, img_id)
            sys.stderr.write(f"Phase 4: Added image {img_id} to observation {observation_id}\n")
            sys.stderr.flush()

            uploaded_images.append({
                'filename': img_filename,
                'image_id': img_id
            })

            # Update review data for this image
            img_data = review_data['images'][img_filename]
            img_data['review']['mo_image_id'] = img_id
            img_data['review']['mo_observation_id'] = observation_id
            img_data['review']['uploaded_at'] = datetime.now().isoformat()
            img_data['review']['uploaded_by'] = username

        # Step 3: Update observation notes with field slip code
        if field_code:
            notes_update = f"Field slip: {field_code}"
            client.update_observation_notes(observation_id, notes_update)

        # Step 4: Create or link field slip
        field_slip_result = None
        if field_code:
            try:
                field_slip_result = client.create_or_link_field_slip(
                    field_code,
                    observation_id,
                    project_id
                )
            except MOAPIConflictError as e:
                print(f"Field slip conflict: {e}")
                field_slip_result = {'warning': str(e)}
            except MOAPIError as e:
                print(f"Field slip API error (may not be implemented): {e}")
                field_slip_result = {'warning': f'Field slip API unavailable: {e}'}

        # Step 5: Add observation to project
        if project_id:
            try:
                sys.stderr.write(f"Phase 4: Adding observation {observation_id} to project {project_id}\n")
                sys.stderr.flush()
                client.add_observation_to_project(observation_id, project_id)
            except MOAPIError as e:
                sys.stderr.write(f"Phase 4: Warning - could not add to project: {e}\n")
                sys.stderr.flush()

        # Release claim
        release_claim(filename, username)
        save_data()

        return jsonify({
            'success': True,
            'image_id': uploaded_images[0]['image_id'],  # Main image ID
            'observation_id': observation_id,
            'observation_url': f'{mo_base_url}/{observation_id}',
            'uploaded_images': uploaded_images,
            'field_slip': field_slip_result if field_code else None
        })

    except MOAPIError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


@app.route('/api/mo/create_new', methods=['POST'])
@requires_auth
def api_mo_create_new():
    """
    Create new observation (Phase 5).

    Request body:
    {
        "filename": "IMG_1234.jpg",
        "field_code": "NEMF-12345",
        "date": "2024-09-15",
        "location_id": 12345,
        "name_id": 67890,
        "notes": "Additional notes",
        "project_id": 42
    }
    """
    from mo_api_client import MOAPIClient, MOAPIError, MOAPIConflictError

    username = get_current_user()
    user_data = users.get(username, {})

    # Ensure user_data is a dictionary
    if not isinstance(user_data, dict):
        return jsonify({
            'error': 'Invalid user configuration. Please check users.json format.'
        }), 500

    api_key = user_data.get('api_key')

    if not api_key:
        return jsonify({
            'error': 'No API key configured. Please set your API key in Settings.'
        }), 400

    data = request.json
    filename = data.get('filename')
    field_code = data.get('field_code')
    date = data.get('date')
    location_id = data.get('location_id')
    name_id = data.get('name_id')
    notes = data.get('notes', '')
    project_id = data.get('project_id')

    if not filename or not date:
        return jsonify({'error': 'filename and date required'}), 400

    if filename not in review_data['images']:
        return jsonify({'error': 'Image not found'}), 404

    # Verify user has claim
    claim = get_claim(filename)
    if claim and claim['user'] != username:
        return jsonify({
            'error': f'Image is claimed by {claim["user"]}'
        }), 409

    # Get linked images
    img = review_data['images'][filename]
    linked_images = img['review'].get('linked_images', [])
    all_images = [filename] + linked_images

    import sys
    sys.stderr.write(f"Phase 5: Main image: {filename}\n")
    sys.stderr.write(f"Phase 5: Linked images: {linked_images}\n")
    sys.stderr.write(f"Phase 5: All images to upload: {all_images}\n")
    sys.stderr.flush()

    try:
        client = MOAPIClient(api_key, base_url=mo_base_url)

        uploaded_images = []

        # Step 1: Upload main image
        sys.stderr.write(f"Phase 5: Processing main image: {filename}\n")
        sys.stderr.flush()

        img_path = images_dir / filename
        copyright_holder = username
        upload_result = client.upload_image(
            str(img_path),
            copyright_holder=copyright_holder,
            notes=f"Field slip: {field_code}" if field_code else "",
            original_name=filename
        )

        # Extract image ID from response
        image_id = extract_image_id(upload_result)
        sys.stderr.write(f"Phase 5: Uploaded main {filename} -> Image ID: {image_id}\n")
        sys.stderr.flush()

        uploaded_images.append({
            'filename': filename,
            'image_id': image_id
        })

        # Step 2: Create observation with main image
        obs_notes = notes
        if field_code:
            field_slip_note = f"Field slip: {field_code}"
            obs_notes = f"{field_slip_note}\n\n{notes}" if notes else field_slip_note

        # If location_id not provided, try to look it up from location text
        location_text = img['review'].get('location') or img['source'].get('location')
        final_location_id = location_id
        final_location_name = None

        if not final_location_id and location_text and all_locations:
            # Try to find exact match in all_locations
            location_text_lower = location_text.lower().strip()
            for loc in all_locations:
                if loc['name'].lower().strip() == location_text_lower:
                    final_location_id = loc['id']
                    sys.stderr.write(f"Phase 5: Found location match: '{location_text}' -> ID {final_location_id}\n")
                    sys.stderr.flush()
                    break

        # If still no location_id, use text as place_name
        if not final_location_id and location_text:
            final_location_name = location_text
            sys.stderr.write(f"Phase 5: No location match found, using place_name: '{location_text}'\n")
            sys.stderr.flush()

        obs_result = client.create_observation(
            date=date,
            location_id=final_location_id,
            location_name=final_location_name,
            name_id=name_id,
            notes=obs_notes,
            image_ids=[image_id],
            project_ids=[project_id] if project_id else None
        )

        # Extract observation ID from response
        observation_id = extract_observation_id(obs_result)
        sys.stderr.write(f"Phase 5: Created observation ID: {observation_id}\n")
        sys.stderr.flush()

        # Step 3: Upload and add linked images
        sys.stderr.write(f"Phase 5: Starting to upload {len(linked_images)} linked images\n")
        sys.stderr.flush()

        for linked_filename in linked_images:
            sys.stderr.write(f"Phase 5: Processing linked image: {linked_filename}\n")
            sys.stderr.flush()
            if linked_filename not in review_data['images']:
                continue

            linked_path = images_dir / linked_filename
            sys.stderr.write(f"Phase 5: Uploading {linked_filename} from path: {linked_path}\n")
            sys.stderr.flush()

            linked_upload_result = client.upload_image(
                str(linked_path),
                copyright_holder=copyright_holder,
                notes=f"Field slip: {field_code}" if field_code else "",
                original_name=linked_filename
            )

            linked_img_id = extract_image_id(linked_upload_result)
            sys.stderr.write(f"Phase 5: Uploaded {linked_filename} -> Image ID: {linked_img_id}\n")
            sys.stderr.flush()

            # Add linked image to observation
            client.add_image_to_observation(observation_id, linked_img_id)
            sys.stderr.write(f"Phase 5: Added image {linked_img_id} to observation {observation_id}\n")
            sys.stderr.flush()

            uploaded_images.append({
                'filename': linked_filename,
                'image_id': linked_img_id
            })

            # Update review data for linked image
            linked_img_data = review_data['images'][linked_filename]
            linked_img_data['review']['mo_image_id'] = linked_img_id
            linked_img_data['review']['mo_observation_id'] = observation_id
            linked_img_data['review']['uploaded_at'] = datetime.now().isoformat()
            linked_img_data['review']['uploaded_by'] = username

        # Step 4: Create field slip
        field_slip_result = None
        if field_code:
            try:
                field_slip_result = client.create_field_slip(
                    field_code,
                    observation_id,
                    project_id
                )
            except MOAPIConflictError as e:
                # Field slip code already exists - this is a real error for new observations
                return jsonify({
                    'error': f'Field slip code {field_code} already exists. '
                           f'Please use a different code or add to existing observation.'
                }), 409
            except MOAPIError as e:
                # Field slip API might not be implemented yet
                # Log but don't fail - observation is already created
                print(f"Field slip API error (may not be implemented): {e}")
                field_slip_result = {'warning': f'Field slip API unavailable: {e}'}

        # Update review data for main image
        img = review_data['images'][filename]
        img['review']['mo_image_id'] = image_id
        img['review']['mo_observation_id'] = observation_id
        img['review']['uploaded_at'] = datetime.now().isoformat()
        img['review']['uploaded_by'] = username

        # Release claim
        release_claim(filename, username)
        save_data()

        return jsonify({
            'success': True,
            'image_id': image_id,
            'observation_id': observation_id,
            'observation_url': f'{mo_base_url}/{observation_id}',
            'uploaded_images': uploaded_images,
            'field_slip': field_slip_result if field_code else None
        })

    except MOAPIError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


def create_app(data_path='review_data.json', users_path='users.json', images_directory=None):
    """Factory function to create and configure the app."""
    load_data(data_path, images_directory)
    load_users(users_path)
    return app


def main():
    global mo_base_url

    import argparse
    parser = argparse.ArgumentParser(description='NEMF Photo Review Server')
    parser.add_argument('--port', type=int, default=5001, help='Port to run on')
    parser.add_argument('--data', default='review_data.json', help='Review data file')
    parser.add_argument('--users', default='users.json', help='Users file')
    parser.add_argument('--images', default=None,
                        help='Images directory (default: data/images relative to data file)')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--mo-url', default='https://mushroomobserver.org',
                        help='Mushroom Observer base URL (default: production)')
    args = parser.parse_args()

    if not os.path.exists(args.data):
        print(f"Error: {args.data} not found")
        sys.exit(1)

    # Set MO base URL
    mo_base_url = args.mo_url
    print(f"MO API URL: {mo_base_url}")

    print(f"Loading data from {args.data}...")
    load_data(args.data, args.images)
    print(f"Images directory: {images_dir}")
    print(f"Images directory type: {type(images_dir)}")
    print(f"Images directory exists: {images_dir.exists()}")
    print(f"Images directory is absolute: {images_dir.is_absolute()}")
    if images_dir.is_symlink():
        print(f"Images directory is symlink, resolves to: {images_dir.resolve()}")

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
