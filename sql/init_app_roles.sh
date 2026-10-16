#!/bin/sh
# Fresh databases only (docker-entrypoint-initdb.d runs this once, after the
# schema): create the API and pipeline roles from sql/app_roles.sql. Skipped
# when their passwords aren't set, in which case every service keeps using
# POSTGRES_USER. No `exit` or `set -e`: the entrypoint may source this file.
if [ -z "${API_DB_PASSWORD:-}" ] || [ -z "${PIPELINE_DB_PASSWORD:-}" ]; then
  echo "init_app_roles: API_DB_PASSWORD / PIPELINE_DB_PASSWORD not set; skipping app roles"
else
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -v api_password="$API_DB_PASSWORD" -v pipeline_password="$PIPELINE_DB_PASSWORD" \
    -f /docker-entrypoint-initdb.d/app_roles.sql.inc
fi
