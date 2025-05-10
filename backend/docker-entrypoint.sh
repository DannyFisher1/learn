#!/bin/bash
set -e

# Watch for changes and restart Uvicorn
watchmedo auto-restart \
    --directory=/app \
    --patterns="*.py" \
    --ignore-patterns="*/__pycache__/*" \
    --recursive \
    --signal SIGTERM \
    -- \
    uvicorn app.main:app --host 0.0.0.0 --port 9000 &

# Wait for any process to exit
wait -n
exit $?