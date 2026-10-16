#!/bin/sh
# Nightly database backup: a compressed pg_dump of the app database, kept for
# KEEP_DAYS days. Run from the repo directory on the server, by cron:
#
#   17 3 * * * cd /home/ubuntu/ms-hs-football-playoff-engine && scripts/backup_db.sh >> /home/ubuntu/backups/backup.log 2>&1
#
# A backup on the same disk doesn't survive losing the server, so also copy
# them off it: Lightsail's automatic instance snapshots cover that, or set
# OFFSITE_CMD to a command that takes the new file's path as its last
# argument (for example a small wrapper around "aws s3 cp").
#
# Restore (into an empty database):
#   gunzip -c ~/backups/mshsfootball-YYYYMMDD-HHMMSS.sql.gz | \
#     docker compose --env-file .env.local --profile local-db exec -T db \
#     sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
set -eu

ENV_FILE="${ENV_FILE:-.env.local}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
NAME="${BACKUP_NAME:-mshsfootball}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
umask 077
stamp=$(date -u +%Y%m%d-%H%M%S)
out="$BACKUP_DIR/$NAME-$stamp.sql.gz"
tmp="$out.partial"

# The db container already has POSTGRES_USER and POSTGRES_DB (and trusts its
# own socket), so no password passes through this script. Written to a
# .partial file first so a failed dump never looks like a good one.
docker compose --env-file "$ENV_FILE" --profile local-db exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip -9 > "$tmp"
# pg_dump's exit status is lost in the pipe; a truncated dump lacks its last line.
if ! gunzip -c "$tmp" | tail -n 5 | grep -q 'PostgreSQL database dump complete'; then
  echo "$(date -u +%FT%TZ) backup FAILED: $tmp is incomplete" >&2
  rm -f "$tmp"
  exit 1
fi
mv "$tmp" "$out"
echo "$(date -u +%FT%TZ) backed up to $out ($(du -h "$out" | cut -f1))"

if [ -n "${OFFSITE_CMD:-}" ]; then
  # shellcheck disable=SC2086 # OFFSITE_CMD is a command line on purpose
  $OFFSITE_CMD "$out"
fi

find "$BACKUP_DIR" -name "$NAME-*.sql.gz" -mtime "+$KEEP_DAYS" -delete
