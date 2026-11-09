#!/usr/bin/env bash
# The deploy key's forced command (~/.ssh/authorized_keys on the server; docs/operations/VM_DEPLOYMENT.md):
# whatever the SSH client asks to run, this runs instead, and it only ever runs scripts/deploy.sh with the
# one commit sha the client sent. So the key can deploy a commit of main and do nothing else.
set -euo pipefail
sha=${SSH_ORIGINAL_COMMAND:-}
if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then
  echo "This key only deploys: send a 40-character commit sha." >&2
  exit 2
fi
exec "$(dirname "$0")/deploy.sh" "$sha"
