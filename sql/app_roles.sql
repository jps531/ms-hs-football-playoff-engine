-- Least-privilege database roles for the API and the Prefect pipelines.
--
-- Both can read and write rows, and nothing else: no superuser, no creating
-- or altering tables, no disabling triggers (so the standings archive stays
-- append-only), no COPY ... PROGRAM or server-side file access. Schema
-- changes (init.sql, migrations) keep running as the database owner.
--
-- Idempotent: safe to re-run, e.g. to change a password. Run it as the owner
-- (POSTGRES_USER), passing the two passwords as psql variables:
--
--   psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--     -v api_password="$API_DB_PASSWORD" -v pipeline_password="$PIPELINE_DB_PASSWORD" \
--     -f sql/app_roles.sql
--
-- Fresh databases get it from sql/init_app_roles.sh. See docs/VM_DEPLOYMENT.md.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE mshsfootball_api LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mshsfootball_api') \gexec
SELECT 'CREATE ROLE mshsfootball_pipeline LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mshsfootball_pipeline') \gexec

ALTER ROLE mshsfootball_api WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'api_password';
ALTER ROLE mshsfootball_pipeline WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'pipeline_password';

SELECT format('GRANT CONNECT ON DATABASE %I TO mshsfootball_api, mshsfootball_pipeline', current_database()) \gexec

-- Nobody but the owner creates objects in public (Postgres 15+ already defaults to this).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO mshsfootball_api, mshsfootball_pipeline;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mshsfootball_api, mshsfootball_pipeline;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO mshsfootball_api, mshsfootball_pipeline;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO mshsfootball_api, mshsfootball_pipeline;

-- Tables, sequences and functions the owner adds later (migrations) get the same grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mshsfootball_api, mshsfootball_pipeline;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO mshsfootball_api, mshsfootball_pipeline;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO mshsfootball_api, mshsfootball_pipeline;
