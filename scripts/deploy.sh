#!/bin/bash
# Deploy NEMF Review to Ubuntu server
# Run this on the server after uploading files

set -e

APP_DIR="/var/www/nemf-review"
APP_USER="www-data"

echo "=== NEMF Review Deployment ==="

# Install system dependencies
echo "Installing system packages..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx

# Create app directory
echo "Setting up application directory..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Create virtual environment
echo "Creating Python virtual environment..."
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python packages..."
pip install flask gunicorn

# Create data directory
mkdir -p $APP_DIR/data

echo ""
echo "=== Next Steps ==="
echo "1. Upload your data files to $APP_DIR/data/"
echo "   - review_data.json"
echo "   - all_names.json"
echo "   - all_locations.json"
echo "   - users.json"
echo ""
echo "2. Upload images to $APP_DIR/data/images/"
echo ""
echo "3. Copy nginx config:"
echo "   sudo cp $APP_DIR/config/nginx.conf /etc/nginx/sites-available/nemf-review"
echo "   sudo ln -s /etc/nginx/sites-available/nemf-review /etc/nginx/sites-enabled/"
echo "   sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "4. Copy systemd service:"
echo "   sudo cp $APP_DIR/config/nemf-review.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable nemf-review"
echo "   sudo systemctl start nemf-review"
echo ""
echo "5. Check status:"
echo "   sudo systemctl status nemf-review"
echo "   sudo journalctl -u nemf-review -f"
