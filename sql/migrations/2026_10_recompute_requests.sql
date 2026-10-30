-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_recompute_requests.sql
--
-- ---------------------------------------------------------------------------
-- Recompute requests: approved corrections waiting to be worked into the numbers
-- ---------------------------------------------------------------------------
-- See sql/init.sql. The app roles get access through the default privileges
-- sql/app_roles.sql set on new tables.

CREATE TABLE IF NOT EXISTS recompute_requests (
    season       INTEGER     PRIMARY KEY,
    from_date    DATE        NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
