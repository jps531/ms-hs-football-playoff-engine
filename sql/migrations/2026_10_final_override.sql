-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_final_override.sql
--
-- ---------------------------------------------------------------------------
-- games_effective.final can be overridden
-- ---------------------------------------------------------------------------
-- A score reported for a game the source hasn't finished yet is approved as
-- overrides on both schools' rows: the score, the result, and final = true,
-- so the game counts as played everywhere games_effective is read. Only the
-- final column changes; the rest is the view as 2026_10_game_id.sql made it.
-- Needs 2026_10_game_id.sql first (the view's game_id column).

-- Same as sql/init.sql (game_date_sql_test keeps them identical).
CREATE OR REPLACE VIEW games_effective AS
SELECT
  school, date, season, opponent,
  COALESCE(overrides->>'result',      result)      AS result,
  COALESCE((overrides->>'final')::boolean,        final)          AS final,
  COALESCE((overrides->>'overtime')::int,         overtime)       AS overtime,
  COALESCE(overrides->>'game_status', game_status) AS game_status,
  COALESCE((overrides->>'game_quarter')::smallint, game_quarter)  AS game_quarter,
  COALESCE(overrides->>'game_clock',               game_clock)    AS game_clock,
  source,
  helmet_design_id,
  COALESCE(overrides->>'location',                location)       AS location,
  COALESCE((overrides->>'location_id')::int,      location_id)    AS location_id,
  COALESCE((overrides->>'points_for')::int,       points_for)     AS points_for,
  COALESCE((overrides->>'points_against')::int,   points_against) AS points_against,
  COALESCE(
    (overrides->>'region_game')::boolean,
    COALESCE(overrides->>'round', round) IS NULL AND EXISTS (
      SELECT 1
      FROM school_seasons a
      JOIN school_seasons b
        ON b.season = a.season AND b.class = a.class AND b.region = a.region
      WHERE a.school = games.school AND a.season = games.season AND b.school = games.opponent
    )
  ) AS region_game,
  COALESCE(overrides->>'round',                   round)          AS round,
  COALESCE((overrides->>'kickoff_time')::timestamptz, kickoff_time) AS kickoff_time,
  overrides,
  pregame_prob, pregame_prob_computed_at,
  COALESCE((overrides->>'ot_period_start_score_for')::int,     ot_period_start_score_for)     AS ot_period_start_score_for,
  COALESCE((overrides->>'ot_period_start_score_against')::int, ot_period_start_score_against) AS ot_period_start_score_against,
  COALESCE(overrides->>'ot_next_possession',      ot_next_possession) AS ot_next_possession,
  -- The game's own date, the same in both schools' rows. The two rows of one
  -- game can carry dates a day apart (each school's page is scraped on its
  -- own), and anything cut off at a date must put both rows on the same side
  -- of it. The later of the two dates wins.
  (SELECT MAX(o.date) FROM games o WHERE o.game_id = games.game_id) AS game_date,
  game_id
FROM games;
