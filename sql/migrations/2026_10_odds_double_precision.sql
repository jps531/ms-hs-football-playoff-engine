-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_odds_double_precision.sql
--
-- ---------------------------------------------------------------------------
-- Odds at full precision
-- ---------------------------------------------------------------------------
-- The odds columns were REAL (32-bit, about 7 digits), so any chance within
-- about 6e-8 of 1 was stored as exactly 1.0: a 1-in-17-million long shot could
-- read as 100% or clinched. DOUBLE PRECISION keeps the pipeline's values as
-- computed (backend/helpers/certainty.py decides which are certain). Rows
-- already written keep their rounded values until they're recomputed: re-run
-- the backfills to rewrite past snapshots.
--
-- Rewrites region_standings in place (a full table rewrite, under a lock), so
-- run it between pipeline runs. Converting an existing DOUBLE PRECISION column
-- again is a no-op.

ALTER TABLE region_standings
  ALTER COLUMN odds_1st TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_2nd TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_3rd TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_4th TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_1st_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_2nd_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_3rd_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_4th_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_playoffs TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_second_round TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_quarterfinals TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_semifinals TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_finals TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_champion TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_playoffs_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_second_round_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_quarterfinals_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_semifinals_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_finals_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_champion_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_first_round_home TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_second_round_home TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_quarterfinals_home TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_semifinals_home TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_first_round_home_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_second_round_home_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_quarterfinals_home_weighted TYPE DOUBLE PRECISION,
  ALTER COLUMN odds_semifinals_home_weighted TYPE DOUBLE PRECISION;
