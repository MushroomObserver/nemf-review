# NEMF Photo Review

A web-based tool for reviewing extracted field slip data from NEMF 2025 photos and uploading them to Mushroom Observer.

## Features

### Core Review Workflow
- Multi-user support with HTTP Basic Auth
- Image claiming/locking to prevent conflicts
- Autocomplete for MO locations and names
- Link related images (e.g., closeups to main shots)
- Mark images as "Already on MO" with ID verification
- Navigation between images with next/previous controls

### MO Integration (Phase 4 & 5)
- **Phase 4**: Add images to existing MO observations
- **Phase 5**: Create new MO observations with images
- Field slip code tracking (notes field until MO API implemented)
- Configurable MO server URL (production or local)

### Review Statuses
- `approved` - Ready for upload
- `corrected` - Fixed field slip data
- `discarded` - Invalid/duplicate image
- `already_on_mo` - Already uploaded to MO

## Local Development

```bash
# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create users file
cp users.json.example users.json
# Edit users.json with real credentials and MO API keys

# Run prepare script (requires MO database access)
python prepare_review_data.py --db

# Start server
python app/server.py --port 5001 --data data/review_data.json --users users.json

# Or use the restart script (stops existing server first)
bash scripts/restart.sh
```

### Server Options

```bash
python app/server.py \
  --port 5001 \                              # Port to run on (default: 5001)
  --host 127.0.0.1 \                         # Host to bind to (default: 127.0.0.1)
  --data data/review_data.json \             # Review data file
  --users users.json \                       # Users file with credentials
  --mo-url https://mushroomobserver.org      # MO API URL (default: production)

# For local MO testing:
--mo-url http://localhost:3000
```

## Deployment

### Initial Setup

See `scripts/deploy.sh` for Ubuntu server deployment.

1. Create DigitalOcean droplet (Ubuntu 24.04)
2. Upload code: `rsync -avz . user@server:/var/www/nemf-review/`
3. Upload data files to `/var/www/nemf-review/data/`
4. Upload images to `/var/www/nemf-review/data/images/`
5. Run `scripts/deploy.sh` on server
6. Configure nginx and systemd per script output

### Updates

To update the production server:

```bash
ssh user@server
cd /var/www/nemf-review
scripts/update
```

The update script:
- Pulls latest code from GitHub
- Updates Python dependencies
- Restarts the service
- Shows service status and recent logs

### Data Files Required

- `review_data.json` - Main review data
- `all_names.json` - MO names for autocomplete
- `all_locations.json` - MO locations for autocomplete
- `users.json` - User credentials with MO API keys
- `images/` - Photo directory

### Users File Format

```json
{
  "username": {
    "password": "hashed_password",
    "api_key": "mo_api_key_here"
  }
}
```

Each user needs an MO API key for Phase 4 & 5 functionality. Get your API key from your MO account settings.

## Architecture

### Components

- `app/server.py` - Flask web server with review API and MO integration endpoints
- `app/mo_api_client.py` - Python client for Mushroom Observer API2
- `templates/review.html` - Single-page application UI
- `scripts/deploy.sh` - Production deployment script
- `scripts/update` - Production update script
- `scripts/restart.sh` - Local development restart script

### MO API Client

The `mo_api_client.py` module provides a Python client for the Mushroom Observer API2:

- Image upload with metadata
- Observation creation and updates
- Field slip management (when API available)
- HTTP Basic Auth with API key
- Error handling with custom exceptions

Used by Phase 4 and Phase 5 endpoints to integrate with MO.

## API Endpoints

### Core Review
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/whoami` | GET | Current user info |
| `/api/status` | GET | Review progress summary |
| `/api/images` | GET | List all images |
| `/api/image/<filename>` | GET | Get image details (claims it) |
| `/api/image/<filename>/review` | POST | Submit review |
| `/api/image/<filename>/heartbeat` | POST | Refresh claim |
| `/api/image/<filename>/release` | POST | Release claim |
| `/api/next-unreviewed` | GET | Get next unreviewed image |
| `/api/adjacent/<filename>` | GET | Get previous/next images |

### Image Linking
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/link/<filename>` | POST | Link two images |

### Autocomplete & Lookup
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lookup/location` | GET | Location autocomplete |
| `/api/lookup/name` | GET | Name autocomplete |
| `/api/lookup/existing_observations` | GET | Search existing observations |
| `/api/verify_mo_id` | GET | Verify MO observation/image ID |

### MO Integration
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mo/add_to_existing` | POST | Phase 4: Add image to existing observation |
| `/api/mo/create_new` | POST | Phase 5: Create new observation with image |

### Settings
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings` | GET | Get user settings |
| `/api/settings` | POST | Update user settings |

## License

Copyright 2025 Mushroom Observer. All rights reserved.
