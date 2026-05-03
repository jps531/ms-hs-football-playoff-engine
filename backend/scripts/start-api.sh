#!/bin/bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PORT=8000
LOG=api.log
PIDFILE=.api.pid

if lsof -i ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Error: port $PORT is already in use." >&2
    echo "Run backend/scripts/stop-api.sh first, or check: lsof -i :$PORT" >&2
    exit 1
fi

if [ ! -f .env.non-docker.local ]; then
    echo "Error: .env.non-docker.local not found. Copy .env.example and fill it in." >&2
    exit 1
fi

set -a
source .env.non-docker.local
set +a

uv run fastapi run backend/api/main.py --host 0.0.0.0 --port "$PORT" > "$LOG" 2>&1 &
echo $! > "$PIDFILE"

echo "Starting API on http://localhost:$PORT ..."

for i in $(seq 1 20); do
    if lsof -i ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "Ready. Swagger UI: http://localhost:$PORT/docs"
        echo "Logs: tail -f $LOG  |  Stop: backend/scripts/stop-api.sh"
        exit 0
    fi
    sleep 0.5
done

echo "Warning: server did not come up within 10s. Check: tail -f $LOG" >&2
exit 1
