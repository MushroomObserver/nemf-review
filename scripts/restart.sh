#!/bin/bash
# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
pip install -q -r requirements.txt

# Kill existing server
lsof -ti :5001 | xargs kill -9 2>/dev/null
sleep 1

# Start server with local MO instance
# Use --mo-url http://localhost:3000 for local MO server
# Use --mo-url https://mushroomobserver.org for production (default)
python app/server.py --port 5001 --data data/review_data.json --users users.json --mo-url http://localhost:3000
