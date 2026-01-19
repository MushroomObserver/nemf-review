# NEMF Photo Review

A web-based tool for reviewing extracted field slip data from NEMF 2025 photos.

## Features

- Multi-user support with HTTP Basic Auth
- Image claiming/locking to prevent conflicts
- Autocomplete for MO locations and names
- Link related images (e.g., closeups to main shots)
- Mark images as "Already on MO" with ID verification
- Integration with MO field slip pages
- Keyboard-driven workflow

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `a` / `Enter` | Approve image |
| `m` | Mark as "Already on MO" |
| `d` | Discard image |
| `s` / `→` / `n` | Next image |
| `←` / `p` | Previous image |
| `j` | Jump to specific image |
| `f` | Focus field code input |
| `1-5` | Select NEMF date (Wed-Sun) |
| `z` | Zoom image |
| `?` | Show shortcuts |
| `Esc` | Close modal |

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Create users file
cp users.json.example users.json
# Edit users.json with real credentials

# Run prepare script (requires MO database access)
python prepare_review_data.py --db

# Start server
python -m app.server --data review_data.json --users users.json
```

## Deployment

See `scripts/deploy.sh` for Ubuntu server deployment.

### Quick Deploy

1. Create DigitalOcean droplet (Ubuntu 24.04)
2. Upload code: `rsync -avz . user@server:/var/www/nemf-review/`
3. Upload data files to `/var/www/nemf-review/data/`
4. Upload images to `/var/www/nemf-review/data/images/`
5. Run `scripts/deploy.sh` on server
6. Configure nginx and systemd per script output

### Data Files Required

- `review_data.json` - Main review data
- `all_names.json` - MO names for autocomplete
- `all_locations.json` - MO locations for autocomplete
- `users.json` - User credentials
- `images/` - Photo directory

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/whoami` | GET | Current user info |
| `/api/status` | GET | Review progress |
| `/api/images` | GET | List all images |
| `/api/image/<filename>` | GET | Get image details (claims it) |
| `/api/image/<filename>/review` | POST | Submit review |
| `/api/image/<filename>/heartbeat` | POST | Refresh claim |
| `/api/image/<filename>/release` | POST | Release claim |
| `/api/link/<filename>` | POST | Link two images |
| `/api/lookup/location` | GET | Location autocomplete |
| `/api/lookup/name` | GET | Name autocomplete |
| `/api/settings` | GET/POST | User settings |

## License

Copyright 2025 Mushroom Observer. All rights reserved.
