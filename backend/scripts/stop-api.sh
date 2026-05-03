#!/bin/bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PIDFILE=.api.pid

if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill "$PID" 2>/dev/null; then
        echo "API stopped (PID $PID)."
    else
        echo "Process $PID was not running."
    fi
    rm "$PIDFILE"
else
    echo "No .api.pid file found. Trying pkill..."
    pkill -f "fastapi run backend/api/main.py" && echo "Stopped." || echo "Nothing running."
fi
