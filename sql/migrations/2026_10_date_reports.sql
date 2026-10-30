-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_date_reports.sql
--
-- ---------------------------------------------------------------------------
-- Date reports: a 'date' submission type
-- ---------------------------------------------------------------------------
-- The site's "Wrong date?" link files a 'date' submission (POST
-- /api/v1/submissions/dates). Approving one moves both schools' rows of the
-- game to the reported date and records the date AHSFHS had in
-- overrides.ahsfhs_date, which the schedule pipeline then respects.
--
-- psql runs this outside a transaction block (no BEGIN), which ADD VALUE
-- needs to be usable right away.

ALTER TYPE submission_type ADD VALUE IF NOT EXISTS 'date';
