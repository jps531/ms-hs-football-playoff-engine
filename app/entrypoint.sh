#!/usr/bin/env bash
set -euo pipefail

# If you run the "app" service directly (e.g., for manual test), you can:
#   docker compose run --rm app python /app/flow.py --run-once
# Otherwise, this script simply sleeps to keep the container alive if started.

echo "App container ready. To run once: python /app/flow.py --run-once"
tail -f /dev/null