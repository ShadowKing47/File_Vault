#!/bin/bash
# Start Celery worker and beat scheduler for distributed storage maintenance

echo "Starting Celery worker with beat scheduler..."
echo "Press Ctrl+C to stop"
echo ""

cd "$(dirname "$0")/backend"

# Start Celery worker with beat scheduler (combined for development)
celery -A core worker --beat --loglevel=info --pool=solo

# For production, run worker and beat separately:
# Terminal 1: celery -A core worker --loglevel=info --concurrency=4
# Terminal 2: celery -A core beat --loglevel=info
