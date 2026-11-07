-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_11_one_score_per_game.sql
--
-- ---------------------------------------------------------------------------
-- games_effective: one score per game
-- ---------------------------------------------------------------------------
-- Needs 2026_10_final_override.sql first. Adds two columns at the end
-- (score_from_opponent, scores_disagree); the others keep their names and types.
--
-- One game, one score. Each game has a row per school, each from that school's
-- AHSFHS page, and the two pages don't always update together. When one row is
-- final and the other isn't yet (its page hasn't posted the score), the other
-- row takes the final one's score (score_from_opponent), so both schools'
-- records, the standings and the odds count the game. When both rows are final
-- but their scores disagree, neither is trusted: both read as not final, with
-- no score (scores_disagree), and the daily update's email lists the game. A
-- correction (an override of final, result or the points) wins: on the row
-- itself, and failing that on the other school's row.

-- Same as sql/init.sql (game_date_sql_test keeps them identical).
CREATE OR REPLACE VIEW games_effective AS
SELECT
  games.school, games.date, games.season, games.opponent,
  CASE pick.mode
    WHEN 'disagree' THEN NULL
    WHEN 'borrow' THEN CASE other.result WHEN 'W' THEN 'L' WHEN 'L' THEN 'W' ELSE other.result END
    ELSE own.result
  END AS result,
  CASE pick.mode WHEN 'disagree' THEN FALSE WHEN 'borrow' THEN TRUE ELSE own.final END AS final,
  CASE pick.mode WHEN 'borrow' THEN other.overtime ELSE own.overtime END AS overtime,
  CASE pick.mode WHEN 'disagree' THEN NULL WHEN 'borrow' THEN other.game_status ELSE own.game_status END
    AS game_status,
  CASE pick.mode WHEN 'own' THEN COALESCE((games.overrides->>'game_quarter')::smallint, games.game_quarter) END
    AS game_quarter,
  CASE pick.mode WHEN 'own' THEN COALESCE(games.overrides->>'game_clock', games.game_clock) END AS game_clock,
  games.source,
  games.helmet_design_id,
  COALESCE(games.overrides->>'location',                games.location)       AS location,
  COALESCE((games.overrides->>'location_id')::int,      games.location_id)    AS location_id,
  CASE pick.mode WHEN 'disagree' THEN NULL WHEN 'borrow' THEN other.points_against ELSE own.points_for END
    AS points_for,
  CASE pick.mode WHEN 'disagree' THEN NULL WHEN 'borrow' THEN other.points_for ELSE own.points_against END
    AS points_against,
  COALESCE(
    (games.overrides->>'region_game')::boolean,
    COALESCE(games.overrides->>'round', games.round) IS NULL AND EXISTS (
      SELECT 1
      FROM school_seasons a
      JOIN school_seasons b
        ON b.season = a.season AND b.class = a.class AND b.region = a.region
      WHERE a.school = games.school AND a.season = games.season AND b.school = games.opponent
    )
  ) AS region_game,
  COALESCE(games.overrides->>'round',                   games.round)          AS round,
  COALESCE((games.overrides->>'kickoff_time')::timestamptz, games.kickoff_time) AS kickoff_time,
  games.overrides,
  games.pregame_prob, games.pregame_prob_computed_at,
  COALESCE((games.overrides->>'ot_period_start_score_for')::int,     games.ot_period_start_score_for)     AS ot_period_start_score_for,
  COALESCE((games.overrides->>'ot_period_start_score_against')::int, games.ot_period_start_score_against) AS ot_period_start_score_against,
  COALESCE(games.overrides->>'ot_next_possession',      games.ot_next_possession) AS ot_next_possession,
  -- The game's own date, the same in both schools' rows. The two rows of one
  -- game can carry dates a day apart (each school's page is scraped on its
  -- own), and anything cut off at a date must put both rows on the same side
  -- of it. The later of the two dates wins.
  (SELECT MAX(o.date) FROM games o WHERE o.game_id = games.game_id) AS game_date,
  games.game_id,
  pick.mode = 'borrow' AS score_from_opponent,
  pick.mode = 'disagree' AS scores_disagree
FROM games
-- This row as its school's page (and any correction) has it.
CROSS JOIN LATERAL (
  SELECT
    COALESCE((games.overrides->>'final')::boolean,      games.final)          AS final,
    COALESCE(games.overrides->>'result',                games.result)         AS result,
    COALESCE((games.overrides->>'points_for')::int,     games.points_for)     AS points_for,
    COALESCE((games.overrides->>'points_against')::int, games.points_against) AS points_against,
    COALESCE(games.overrides->>'game_status',           games.game_status)    AS game_status,
    COALESCE((games.overrides->>'overtime')::int,       games.overtime)       AS overtime,
    games.overrides ?| ARRAY['final', 'result', 'points_for', 'points_against'] AS corrected
) own
-- The other school's row of the same game, the same way (none for an out-of-state opponent).
LEFT JOIN LATERAL (
  SELECT
    COALESCE((o.overrides->>'final')::boolean,      o.final)          AS final,
    COALESCE(o.overrides->>'result',                o.result)         AS result,
    COALESCE((o.overrides->>'points_for')::int,     o.points_for)     AS points_for,
    COALESCE((o.overrides->>'points_against')::int, o.points_against) AS points_against,
    COALESCE(o.overrides->>'game_status',           o.game_status)    AS game_status,
    COALESCE((o.overrides->>'overtime')::int,       o.overtime)       AS overtime,
    o.overrides ?| ARRAY['final', 'result', 'points_for', 'points_against'] AS corrected
  FROM games o
  WHERE o.game_id = games.game_id AND o.school = games.opponent
) other ON TRUE
CROSS JOIN LATERAL (
  SELECT CASE
    WHEN own.corrected THEN 'own'
    WHEN other.corrected AND other.final IS TRUE THEN 'borrow'
    WHEN own.final IS TRUE AND other.final IS TRUE AND (
      own.points_for IS DISTINCT FROM other.points_against
      OR own.points_against IS DISTINCT FROM other.points_for
      OR own.result IS DISTINCT FROM
         (CASE other.result WHEN 'W' THEN 'L' WHEN 'L' THEN 'W' ELSE other.result END)
    ) THEN 'disagree'
    WHEN own.final IS NOT TRUE AND other.final IS TRUE AND other.result IS NOT NULL THEN 'borrow'
    ELSE 'own'
  END AS mode
) pick;
