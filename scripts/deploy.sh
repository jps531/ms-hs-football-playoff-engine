#!/usr/bin/env bash
# Deploy one commit of main to this server: the commit's code checked out, its images (built and pushed by
# .github/workflows/deploy.yml) pulled, the database migrated, the services restarted, and the site checked.
# If the check fails, the previous commit and images come back (the migrations stay: they're forward-only
# and each is safe to run twice).
#
#     scripts/deploy.sh <40-character commit sha>
#
# Run from GitHub Actions over SSH (scripts/deploy_ssh.sh is the deploy key's forced command), or by hand.
# It waits, up to DEPLOY_WAIT_MINUTES (default 60), for running pipelines to finish first: the worker runs
# the flows in-process, so restarting it mid-run would kill the daily update.
set -euo pipefail

# All of it in one block, which bash reads whole before running any of it. The script checks out another
# commit as it goes, which can change this very file; git replaces a file rather than editing it, so a
# running script keeps reading the old one anyway, but this holds even if that ever changes.
{
sha=${1:-}
if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: scripts/deploy.sh <40-character commit sha>" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
compose=(docker compose --env-file .env.local --profile local-db)
log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

# One deploy at a time.
exec 9>"${DEPLOY_LOCK:-/tmp/mshsfootball-deploy.lock}"
if ! flock -n 9; then
  echo "Another deploy is running." >&2
  exit 1
fi

previous_sha=$(git rev-parse HEAD)
previous_tag=$(cat .deployed-image-tag 2>/dev/null || echo local)

# Only commits on main: whatever reaches this script, it never deploys a branch.
git fetch --quiet origin main
if ! git merge-base --is-ancestor "$sha" origin/main; then
  echo "$sha isn't on origin/main; not deploying it." >&2
  exit 1
fi

# Wait for the pipelines: no flow run running or about to (Prefect), and the update lock (run_lock.py's
# advisory lock, 2026_10_30) free.
busy() {
  local runs locks
  runs=$("${compose[@]}" exec -T prefect-worker python -c '
import json, urllib.request
body = json.dumps({"flow_runs": {"state": {"type": {"any_": ["RUNNING", "PENDING", "CANCELLING"]}}}}).encode()
req = urllib.request.Request("http://prefect-server:4200/api/flow_runs/count", data=body,
                             headers={"Content-Type": "application/json"})
print(json.load(urllib.request.urlopen(req, timeout=10)))' 2>/dev/null || echo 0)
  locks=$("${compose[@]}" exec -T db sh -c \
    'psql -X -q -A -t -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM pg_locks WHERE locktype = '"'"'advisory'"'"' AND classid = 0 AND objid = 20261030 AND granted"' \
    2>/dev/null || echo 0)
  [[ ${runs//[[:space:]]/} != 0 || ${locks//[[:space:]]/} != 0 ]]
}
waited=0
while busy; do
  if (( waited >= ${DEPLOY_WAIT_MINUTES:-60} )); then
    echo "Pipelines still running after ${waited} minutes; not deploying. Try again once they finish." >&2
    exit 1
  fi
  (( waited == 0 )) && log "A pipeline is running; waiting for it to finish"
  sleep 60
  waited=$((waited + 1))
done

start() {
  # $1: commit, $2: image tag. The checkout (nginx's config and pages, the SQL, the scripts) and the images.
  git checkout --quiet --detach "$1"
  IMAGE_TAG=$2 "${compose[@]}" up -d --no-build
}

healthy() {
  # The API answers through nginx, the front page is served, and every service is up.
  local i
  for i in $(seq 1 "${DEPLOY_HEALTH_TRIES:-24}"); do
    if curl -fsS --max-time 5 --resolve mshsfootball.com:443:127.0.0.1 https://mshsfootball.com/api/v1/seasons >/dev/null &&
       curl -fsS --max-time 5 --resolve mshsfootball.com:443:127.0.0.1 https://mshsfootball.com/ >/dev/null &&
       ! "${compose[@]}" ps -a --format '{{.Service}} {{.State}}' | grep -v ' running$' | grep -q .; then
      return 0
    fi
    sleep "${DEPLOY_HEALTH_PAUSE:-5}"
  done
  return 1
}

log "Deploying ${sha:0:7} (was ${previous_sha:0:7}, images ${previous_tag:0:7})"
IMAGE_TAG=$sha "${compose[@]}" pull --quiet api prefect-worker
git checkout --quiet --detach "$sha"
log "Migrating"
scripts/migrate.py
log "Starting"
IMAGE_TAG=$sha "${compose[@]}" up -d --no-build
# nginx reads its config once; a new one needs the container recreated (it's bind-mounted as one file).
if ! git diff --quiet "$previous_sha" "$sha" -- nginx/nginx.conf; then
  log "nginx.conf changed; recreating nginx"
  IMAGE_TAG=$sha "${compose[@]}" up -d --no-deps --force-recreate nginx
fi

if healthy; then
  echo "$sha" > .deployed-image-tag
  log "Deployed ${sha:0:7}"
  exit 0
fi

log "The site didn't come up healthy; rolling back to ${previous_sha:0:7}"
"${compose[@]}" ps >&2 || true
start "$previous_sha" "$previous_tag"
if ! git diff --quiet "$previous_sha" "$sha" -- nginx/nginx.conf; then
  IMAGE_TAG=$previous_tag "${compose[@]}" up -d --no-deps --force-recreate nginx
fi
if healthy; then
  log "Rolled back to ${previous_sha:0:7}; ${sha:0:7} was not deployed"
else
  log "Rolled back to ${previous_sha:0:7}, but the site still isn't healthy: look now"
fi
exit 1
}
