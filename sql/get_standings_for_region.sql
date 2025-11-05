-- DROP FUNCTION public.get_standings_for_region(int4, int4, int4);

CREATE OR REPLACE FUNCTION public.get_standings_for_region(p_class integer, p_region integer, p_season integer DEFAULT 2025)
 RETURNS TABLE(school text, class integer, region integer, season integer, wins integer, losses integer, ties integer, region_wins integer, region_losses integer, region_ties integer)
 LANGUAGE sql
 STABLE
AS $function$
WITH division_schools AS (
  SELECT s.school, s.class, s.region, s.season
  FROM schools s
  WHERE s.class  = p_class
    AND s.region = p_region
    AND s.season = p_season
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
  LEFT JOIN games g
    ON g.school = ds.school
   AND g.season = ds.season
  GROUP BY ds.school, ds.class, ds.region, ds.season
),
overall_records AS (
  SELECT
    ds.school,
    COUNT(*) FILTER (WHERE g.final AND g.result = 'W') AS wins,
    COUNT(*) FILTER (WHERE g.final AND g.result = 'L') AS losses,
    COUNT(*) FILTER (WHERE g.final AND g.result = 'T') AS ties
  FROM division_schools ds
  LEFT JOIN games g
    ON g.school = ds.school
   AND g.season = ds.season
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
  LEFT JOIN games g
    ON g.school       = t1.school
   AND g.season       = t1.season
   AND g.final        = TRUE
   AND g.region_game  = TRUE
   AND g.opponent     = t2.school
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
  LEFT JOIN games g
    ON g.school       = t1.school
   AND g.season       = t1.season
   AND g.final        = TRUE
   AND g.region_game  = TRUE
   AND g.opponent     = t2.school
  GROUP BY t1.school, t1.tie_group_key
),
region_points_allowed AS (
  SELECT
    ds.school,
    COALESCE(SUM(g.points_against) FILTER (WHERE g.final AND g.region_game), 0) AS region_pts_allowed
  FROM division_schools ds
  LEFT JOIN games g
    ON g.school = ds.school
   AND g.season = ds.season
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
