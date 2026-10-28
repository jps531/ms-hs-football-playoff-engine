-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_game_date.sql
--
-- Adds games_effective.game_date: the game's own date, the same in both
-- schools' rows (the later of the two when they disagree by up to 3 days), and
-- re-creates get_standings_for_region to cut off by it. Then recompute the
-- dates whose snapshots counted a game on one side only (see PIPELINES.md,
-- "Backfill Historical Snapshots").
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
  COALESCE(overrides->>'ot_next_possession',      ot_next_possession) AS ot_next_possession,
  -- The game's own date, the same in both schools' rows. The two rows of one
  -- game can carry dates a day apart (each school's page is scraped on its
  -- own), and anything cut off at a date must put both rows on the same side
  -- of it. The later of the two dates wins. Rows of the same two schools more
  -- than 3 days apart are different games (a playoff rematch, say).
  GREATEST(date, (
    SELECT MAX(o.date)
    FROM games o
    WHERE o.season = games.season AND o.school = games.opponent AND o.opponent = games.school
      AND o.date BETWEEN games.date - 3 AND games.date + 3
  )) AS game_date
FROM games;


CREATE OR REPLACE FUNCTION public.get_standings_for_region(p_class integer, p_region integer, p_season integer DEFAULT 2025, p_cutoff_date date DEFAULT NULL)
 RETURNS TABLE(school text, class integer, region integer, season integer, wins integer, losses integer, ties integer, region_wins integer, region_losses integer, region_ties integer)
 LANGUAGE sql
 STABLE
AS $function$
WITH division_schools AS (
  SELECT ss.school, ss.class, ss.region, ss.season
  FROM school_seasons ss
  WHERE ss.class     = p_class
    AND ss.region    = p_region
    AND ss.season    = p_season
    AND ss.is_active = TRUE
),
region_records AS (
  SELECT
    ds.school,
    ds.class,
    ds.region,
    ds.season,
    COUNT(*) FILTER (WHERE g.final AND g.region_game AND g.result = 'W') AS region_wins,
    COUNT(*) FILTER (WHERE g.final AND g.region_game AND g.result = 'L') AS region_losses,
    COUNT(*) FILTER (WHERE g.final AND g.region_game AND g.result = 'T') AS region_ties
  FROM division_schools ds
  LEFT JOIN games_effective g
    ON g.school = ds.school
   AND g.season = ds.season
   AND (p_cutoff_date IS NULL OR g.game_date <= p_cutoff_date)
  GROUP BY ds.school, ds.class, ds.region, ds.season
),
overall_records AS (
  SELECT
    ds.school,
    COUNT(*) FILTER (WHERE g.final AND g.result = 'W') AS wins,
    COUNT(*) FILTER (WHERE g.final AND g.result = 'L') AS losses,
    COUNT(*) FILTER (WHERE g.final AND g.result = 'T') AS ties
  FROM division_schools ds
  LEFT JOIN games_effective g
    ON g.school = ds.school
   AND g.season = ds.season
   AND (p_cutoff_date IS NULL OR g.game_date <= p_cutoff_date)
  GROUP BY ds.school
),
region_base AS (
  SELECT
    rr.*,
    (COALESCE(region_wins,0) + COALESCE(region_losses,0) + COALESCE(region_ties,0)) AS region_gp,
    CASE
      WHEN (COALESCE(region_wins,0) + COALESCE(region_losses,0) + COALESCE(region_ties,0)) > 0
        THEN (COALESCE(region_wins,0) + 0.5 * COALESCE(region_ties,0))::numeric
             / (COALESCE(region_wins,0) + COALESCE(region_losses,0) + COALESCE(region_ties,0))
      ELSE 0
    END AS region_win_pct
  FROM region_records rr
),
base_with_tie_groups AS (
  SELECT
    rb.*,
    CONCAT(rb.region_wins, '-', rb.region_losses, '-', rb.region_ties) AS tie_group_key,
    DENSE_RANK() OVER (
      ORDER BY rb.region_win_pct DESC, rb.region_losses ASC, rb.school
    ) AS base_rank
  FROM region_base rb
),
h2h AS (
  SELECT
    t1.school,
    t1.tie_group_key,
    COUNT(*) FILTER (WHERE g.final AND g.region_game AND g.result = 'W') AS h2h_wins,
    COUNT(*) FILTER (WHERE g.final AND g.region_game AND g.result = 'L') AS h2h_losses,
    COUNT(*) FILTER (WHERE g.final AND g.region_game AND g.result = 'T') AS h2h_ties
  FROM base_with_tie_groups t1
  JOIN base_with_tie_groups t2
    ON t2.tie_group_key = t1.tie_group_key
   AND t2.school       <> t1.school
  LEFT JOIN games_effective g
    ON g.school       = t1.school
   AND g.season       = t1.season
   AND g.final        = TRUE
   AND g.region_game  = TRUE
   AND g.opponent     = t2.school
   AND (p_cutoff_date IS NULL OR g.game_date <= p_cutoff_date)
  GROUP BY t1.school, t1.tie_group_key
),
h2h_pd_capped AS (
  SELECT
    t1.school,
    t1.tie_group_key,
    COALESCE(SUM(GREATEST(LEAST(g.points_for - g.points_against, 12), -12)), 0) AS h2h_pd_capped
  FROM base_with_tie_groups t1
  JOIN base_with_tie_groups t2
    ON t2.tie_group_key = t1.tie_group_key
   AND t2.school       <> t1.school
  LEFT JOIN games_effective g
    ON g.school       = t1.school
   AND g.season       = t1.season
   AND g.final        = TRUE
   AND g.region_game  = TRUE
   AND g.opponent     = t2.school
   AND (p_cutoff_date IS NULL OR g.game_date <= p_cutoff_date)
  GROUP BY t1.school, t1.tie_group_key
),
region_points_allowed AS (
  SELECT
    ds.school,
    COALESCE(SUM(g.points_against) FILTER (WHERE g.final AND g.region_game), 0) AS region_pts_allowed
  FROM division_schools ds
  LEFT JOIN games_effective g
    ON g.school = ds.school
   AND g.season = ds.season
   AND (p_cutoff_date IS NULL OR g.game_date <= p_cutoff_date)
  GROUP BY ds.school
),
ranked AS (
  SELECT
    bw.school,
    bw.class,
    bw.region,
    bw.season,
    ov.wins,
    ov.losses,
    ov.ties,
    bw.region_wins,
    bw.region_losses,
    bw.region_ties,
    bw.region_win_pct,
    (COALESCE(h2h.h2h_wins,0) + 0.5*COALESCE(h2h.h2h_ties,0)) AS h2h_value,
    h2h_pd_capped.h2h_pd_capped,
    rpa.region_pts_allowed,
    ROW_NUMBER() OVER (
      ORDER BY
        bw.region_win_pct DESC,
        bw.region_losses ASC,
        (COALESCE(h2h.h2h_wins,0) + 0.5*COALESCE(h2h.h2h_ties,0)) DESC,
        h2h_pd_capped.h2h_pd_capped DESC,
        rpa.region_pts_allowed ASC,
        bw.school
    ) AS order_rank,
    ROW_NUMBER() OVER (
      PARTITION BY
        bw.region_win_pct,
        bw.region_losses,
        (COALESCE(h2h.h2h_wins,0) + 0.5*COALESCE(h2h.h2h_ties,0)),
        h2h_pd_capped.h2h_pd_capped,
        rpa.region_pts_allowed
      ORDER BY bw.school
    ) AS group_pos,
    COUNT(*) OVER (
      PARTITION BY
        bw.region_win_pct,
        bw.region_losses,
        (COALESCE(h2h.h2h_wins,0) + 0.5*COALESCE(h2h.h2h_ties,0)),
        h2h_pd_capped.h2h_pd_capped,
        rpa.region_pts_allowed
    ) AS tie_group_size
  FROM base_with_tie_groups bw
  LEFT JOIN overall_records ov USING (school)
  LEFT JOIN h2h USING (school, tie_group_key)
  LEFT JOIN h2h_pd_capped USING (school, tie_group_key)
  LEFT JOIN region_points_allowed rpa USING (school)
)
SELECT
  school,
  class,
  region,
  season,
  COALESCE(wins,0)           AS wins,
  COALESCE(losses,0)         AS losses,
  COALESCE(ties,0)           AS ties,
  COALESCE(region_wins,0)    AS region_wins,
  COALESCE(region_losses,0)  AS region_losses,
  COALESCE(region_ties,0)    AS region_ties
FROM ranked
ORDER BY order_rank;
$function$
;
