#!/usr/bin/env bash
# Create a GitHub release for every version main has had that has none yet, oldest first, each tagged at the
# main commit where it first appeared, with its CHANGELOG.md entry as its notes (scripts/release.py).
#
# Run it once, from a checkout of main, with the GitHub CLI signed in as you (`gh auth login`):
#
#     git checkout main && git pull && scripts/backfill_releases.sh
#
# It runs here rather than in Actions: an old version's commit has different workflow files from main's,
# and the Actions token isn't allowed to create a tag on such a commit (HTTP 403, "Resource not
# accessible by integration"). New versions don't need this: the Release workflow tags each version bump
# on main as it merges.
set -euo pipefail
cd "$(dirname "$0")/.."

current=$(python3 scripts/release.py version)
notes=$(mktemp)
trap 'rm -f "$notes"' EXIT
python3 scripts/release.py history main | while read -r version sha; do
  if gh release view "v$version" >/dev/null 2>&1 </dev/null; then
    echo "v$version: already released"
    continue
  fi
  # The commit the tag points at (an annotated tag's "^{}" line, listed last, when there is one).
  tagged=$(git ls-remote --tags origin "refs/tags/v$version" "refs/tags/v$version^{}" | tail -n 1 | cut -f1)
  if [ -n "$tagged" ] && [ "$tagged" != "$sha" ]; then
    echo "v$version: the tag is on ${tagged:0:7}, not ${sha:0:7}, where this version first appeared on main." >&2
    echo "  Delete it (git push origin :refs/tags/v$version) and run this again; skipping it for now." >&2
    continue
  fi
  python3 scripts/release.py notes "$version" > "$notes" || echo "See CHANGELOG.md." > "$notes"
  latest=$([ "$version" = "$current" ] && echo true || echo false)
  gh release create "v$version" --target "$sha" --title "v$version" --notes-file "$notes" --latest="$latest" </dev/null
  echo "v$version: released at ${sha:0:7}"
done
