#!/bin/bash
set -e

echo "Starting TraceWise backend..."

# Initialize database if DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    echo "Initializing database..."
    python -m app.db.init_db || {
        echo "Database initialization failed, continuing anyway..."
    }
fi

# Start the application
echo "Starting uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
