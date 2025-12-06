# PowerShell script to start Celery worker and beat scheduler
# For distributed storage maintenance

Write-Host "Starting Celery worker with beat scheduler..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

Set-Location "$PSScriptRoot\backend"

# Start Celery worker with beat scheduler (combined for development)
celery -A core worker --beat --loglevel=info --pool=solo

# For production, run worker and beat separately in different terminals:
# Terminal 1: celery -A core worker --loglevel=info --pool=solo
# Terminal 2: celery -A core beat --loglevel=info
