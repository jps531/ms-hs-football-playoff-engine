-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_region_games_from_alignment.sql
--
-- region_game is decided by the region alignment, not by the source site:
-- a regular-season game (no playoff round) is a region game exactly when both
-- teams are in the same class and region in school_seasons for that season.
-- AHSFHS marks region games per team page and can disagree between the two
-- teams' pages or lag a realignment (e.g. Leake Central's 2026 move to 5A-2),
-- so its flag in games.region_game is no longer used. An override
-- ('region_game' in overrides) still wins for a genuine exception.
CREATE OR REPLACE VIEW games_effective AS
SELECT
  school, date, season, opponent,
  COALESCE(overrides->>'result',      result)      AS result,
  final,
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
  COALESCE(overrides->>'ot_next_possession',      ot_next_possession) AS ot_next_possession
FROM games;
