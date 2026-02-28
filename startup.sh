#!/bin/bash
set -e

# Ensure data dir exists on the volume
mkdir -p data

# If database is empty/new, run the data pipeline
if [ ! -f data/grants.db ] || [ "$(python3 -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('data/grants.db')
    count = conn.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0]
    print(count)
except:
    print(0)
")" = "0" ]; then
    echo "=== Populating database with real grant data ==="
    export PYTHONPATH=/app/src

    echo "Step 1: Initializing database..."
    python3 -m grant_intel.cli db-init

    echo "Step 2: Searching Grants.gov..."
    python3 -m grant_intel.cli search || echo "Search completed with warnings"

    echo "Step 3: Researching foundations..."
    python3 -m grant_intel.cli research || echo "Research completed with warnings"

    echo "=== Database populated ==="
    python3 -m grant_intel.cli status
else
    echo "Database already has data, skipping pipeline."
    PYTHONPATH=/app/src python3 -m grant_intel.cli status
fi

# Start the web server
echo "Starting gunicorn..."
exec gunicorn 'grant_intel.dashboard.app:create_app()' --bind 0.0.0.0:${PORT:-8000}
