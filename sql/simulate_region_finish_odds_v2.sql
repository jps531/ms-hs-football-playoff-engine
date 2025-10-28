CREATE OR REPLACE FUNCTION simulate_region_finish_odds_v2(
  p_class   INT,
  p_region  INT,
  p_season  INT DEFAULT 2025,
  p_trials  INT DEFAULT 20000
)
RETURNS TABLE (
  school              TEXT,
  class               INT,
  region              INT,
  season              INT,
  odds_1st            NUMERIC,
  odds_2nd            NUMERIC,
  odds_3rd            NUMERIC,
  odds_4th            NUMERIC,
  odds_playoffs       NUMERIC,
  final_odds_playoffs NUMERIC,
  clinched            BOOLEAN,
  eliminated          BOOLEAN
)
LANGUAGE plpgsql
SET plpgsql.variable_conflict = 'use_column'
AS $$
DECLARE
  t INT;
BEGIN
  -------------------------------------------------------------------
  -- Division roster
  -------------------------------------------------------------------
  CREATE TEMP TABLE _div_schools ON COMMIT DROP AS
  SELECT s.school, s.class, s.region, s.season
  FROM schools s
  WHERE s.class = p_class AND s.region = p_region AND s.season = p_season;

  -------------------------------------------------------------------
  -- Completed region games (final=TRUE) for this division (both sides
  -- exist in games); normalize to single row (a<b).
  -------------------------------------------------------------------
  CREATE TEMP TABLE _completed_pairs ON COMMIT DROP AS
  WITH comp AS (
    SELECT g.school, g.opponent, g.result, g.points_for, g.points_against
    FROM games g
    JOIN _div_schools d1 ON d1.school = g.school   AND d1.season = g.season
    JOIN _div_schools d2 ON d2.school = g.opponent AND d2.season = g.season
    WHERE g.final = TRUE AND g.region_game = TRUE
  ),
  norm AS (
    SELECT
      LEAST(school, opponent)  AS a,
      GREATEST(school, opponent) AS b,
      -- result from a's perspective: +1 a beat b, 0 tie, -1 a lost to b
      MAX(
        CASE
          WHEN school = LEAST(school,opponent) AND result='W' THEN  1
          WHEN school = GREATEST(school,opponent) AND result='L' THEN  1
          WHEN result='T' THEN 0
          ELSE -1
        END
      ) AS res_a,
      -- point diff from a's perspective
      MAX(
        CASE
          WHEN school = LEAST(school,opponent) THEN (points_for - points_against)
          ELSE (points_against - points_for)
        END
      ) AS pd_a
    FROM comp
    GROUP BY LEAST(school, opponent), GREATEST(school, opponent)
  )
  SELECT a, b, res_a, pd_a FROM norm;

  -------------------------------------------------------------------
  -- Remaining region games to simulate (unique pairs a<b)
  -------------------------------------------------------------------
  CREATE TEMP TABLE _remaining_pairs ON COMMIT DROP AS
  WITH candidates AS (
    SELECT
      LEAST(g.school, g.opponent)  AS a,
      GREATEST(g.school, g.opponent) AS b
    FROM games g
    JOIN _div_schools ds1 ON ds1.school = g.school   AND ds1.season = g.season
    JOIN _div_schools ds2 ON ds2.school = g.opponent AND ds2.season = g.season
    WHERE g.final = FALSE AND g.region_game = TRUE
  )
  SELECT DISTINCT a, b FROM candidates;

  -------------------------------------------------------------------
  -- Completed per-team totals (wins/losses/ties, points allowed)
  -------------------------------------------------------------------
  CREATE TEMP TABLE _base_region_totals ON COMMIT DROP AS
  WITH expl AS (
    SELECT
      cp.a, cp.b, cp.res_a,
      -- who is winner? res_a: +1 means a beat b, -1 means b beat a, 0 tie
      CASE WHEN cp.res_a =  1 THEN cp.a
           WHEN cp.res_a = -1 THEN cp.b
           ELSE NULL END AS winner,
      CASE WHEN cp.res_a =  1 THEN cp.b
           WHEN cp.res_a = -1 THEN cp.a
           ELSE NULL END AS loser,
      cp.pd_a
    FROM _completed_pairs cp
  ),
  rows AS (
    -- explode to two rows per completed matchup for per-team aggregation
    SELECT a AS school,
           CASE res_a WHEN  1 THEN 1 WHEN -1 THEN 0 ELSE 0 END AS w,
           CASE res_a WHEN -1 THEN 1 WHEN  1 THEN 0 ELSE 0 END AS l,
           CASE res_a WHEN  0 THEN 1 ELSE 0 END AS t,
           -- points allowed: if a beat b with pd_a, then a allowed (b_pts)
           -- but we only have differential; recover PA by:
           -- we can’t exactly recover both PF/PA from pd alone; for PA sums
           -- we’ll defer to original completed rows if you need precision.
           -- For Step 5 we need PA on all region games; we’ll rebuild it later
           0 AS pa_stub
    FROM expl
    UNION ALL
    SELECT b AS school,
           CASE res_a WHEN -1 THEN 1 WHEN  1 THEN 0 ELSE 0 END AS w,
           CASE res_a WHEN  1 THEN 1 WHEN -1 THEN 0 ELSE 0 END AS l,
           CASE res_a WHEN  0 THEN 1 ELSE 0 END AS t,
           0 AS pa_stub
    FROM expl
  )
  SELECT s.school,
         COALESCE(SUM(r.w),0) AS w,
         COALESCE(SUM(r.l),0) AS l,
         COALESCE(SUM(r.t),0) AS t,
         0::INT               AS pa  -- will fill from original completed later (see Step 5 compute path)
  FROM _div_schools s
  LEFT JOIN rows r ON r.school = s.school
  GROUP BY s.school;

  -- For accurate PA from completed games, get it directly:
  CREATE TEMP TABLE _completed_raw ON COMMIT DROP AS
  SELECT g.school, SUM(g.points_against)::INT AS pa
  FROM games g
  JOIN _div_schools ds ON ds.school = g.school AND ds.season = g.season
  WHERE g.final = TRUE AND g.region_game = TRUE
  GROUP BY g.school;

  UPDATE _base_region_totals t
  SET pa = COALESCE(cr.pa, 0)
  FROM _completed_raw cr
  WHERE cr.school = t.school;

  -------------------------------------------------------------------
  -- Aggregate odds counters
  -------------------------------------------------------------------
  CREATE TEMP TABLE _odds ON COMMIT DROP AS
  SELECT s.school,
         0::BIGINT AS first_ct,
         0::BIGINT AS second_ct,
         0::BIGINT AS third_ct,
         0::BIGINT AS fourth_ct
  FROM _div_schools s;

  -------------------------------------------------------------------
  -- Reusable working tables (TRUNCATE each trial)
  -------------------------------------------------------------------
  CREATE TEMP TABLE _trial_totals   (school TEXT, w INT, l INT, t INT, pa INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_results  (a TEXT, b TEXT, a_win INT, a_pts INT, b_pts INT) ON COMMIT DROP;
  CREATE TEMP TABLE _h2h_all        (a TEXT, b TEXT, res_a INT, pd_a INT) ON COMMIT DROP;

  CREATE TEMP TABLE _trial_base     (school TEXT, w INT, l INT, t INT, pa INT, gp INT, win_pct NUMERIC) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_sorted   (school TEXT, w INT, l INT, t INT, pa INT, win_pct NUMERIC, base_bucket INT) ON COMMIT DROP;

  CREATE TEMP TABLE _trial_h2h_group  (school TEXT, base_bucket INT, h2h_pts NUMERIC) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_h2h_pd_cap (school TEXT, base_bucket INT, h2h_pd_capped INT) ON COMMIT DROP;

  CREATE TEMP TABLE _outside          (tie_school TEXT, base_bucket INT, opp TEXT, opp_rank INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_step2_arr  (school TEXT, base_bucket INT, step2_arr INT[]) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_step4_arr  (school TEXT, base_bucket INT, step4_arr INT[]) ON COMMIT DROP;

  CREATE TEMP TABLE _trial_ranked   (
    school TEXT, w INT, l INT, t INT, pa INT, win_pct NUMERIC, base_bucket INT,
    h2h_pts NUMERIC, h2h_pd_capped INT, step2_arr INT[], step4_arr INT[],
    bucket_size INT
  ) ON COMMIT DROP;

  CREATE TEMP TABLE _bucket_sizes   (base_bucket INT, sz INT) ON COMMIT DROP;
  CREATE TEMP TABLE _bucket_offsets (base_bucket INT, start_place INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_places   (school TEXT, first_slot INT, last_slot INT, grp_sz INT) ON COMMIT DROP;

  -------------------------------------------------------------------
  -- Monte Carlo
  -------------------------------------------------------------------
  FOR t IN 1..p_trials LOOP
    TRUNCATE _trial_totals, _trial_results, _h2h_all,
             _trial_base, _trial_sorted,
             _trial_h2h_group, _trial_h2h_pd_cap,
             _outside, _trial_step2_arr, _trial_step4_arr,
             _trial_ranked, _bucket_sizes, _bucket_offsets, _trial_places;

    -- seed totals from completed
    INSERT INTO _trial_totals
    SELECT school, w, l, t, pa FROM _base_region_totals;

    -- simulate remaining region games with transparent score model
    -- winner: fair coin; margin from {3,7,10,14} with probs {0.4,0.3,0.2,0.1};
    -- loser points 10..30; winner = loser + margin
    INSERT INTO _trial_results (a, b, a_win, a_pts, b_pts)
    SELECT rp.a, rp.b,
           CASE WHEN random() < 0.5 THEN 1 ELSE 0 END,
           NULL::INT, NULL::INT
    FROM _remaining_pairs rp;

    -- assign points
    UPDATE _trial_results tr
    SET a_pts = CASE WHEN a_win=1 THEN (lp.l + m.margin) ELSE lp.l END,
        b_pts = CASE WHEN a_win=1 THEN lp.l ELSE (lp.l + m.margin) END
    FROM (
      SELECT a, b, 10 + FLOOR(random()*21)::INT AS l
      FROM _remaining_pairs
    ) lp
    JOIN (
      SELECT a, b,
        CASE
          WHEN r < 0.4 THEN 3
          WHEN r < 0.7 THEN 7
          WHEN r < 0.9 THEN 10
          ELSE 14
        END AS margin
      FROM (
        SELECT a, b, random() AS r FROM _remaining_pairs
      ) x
    ) m ON m.a = lp.a AND m.b = lp.b
    WHERE tr.a = lp.a AND tr.b = lp.b;

    -- update per-team totals (W/L/PA)
    UPDATE _trial_totals tt
    SET w = w + tr.a_win,
        l = l + (1 - tr.a_win),
        pa = pa + CASE WHEN tr.a_win=1 THEN tr.b_pts ELSE tr.a_pts END
    FROM _trial_results tr
    WHERE tt.school = tr.a;

    UPDATE _trial_totals tt
    SET w = w + (1 - tr.a_win),
        l = l + tr.a_win,
        pa = pa + CASE WHEN tr.a_win=1 THEN tr.a_pts ELSE tr.b_pts END
    FROM _trial_results tr
    WHERE tt.school = tr.b;

    -- unified H2H table: start with completed pairs, then add simulated
    INSERT INTO _h2h_all (a, b, res_a, pd_a)
    SELECT a, b, res_a, pd_a FROM _completed_pairs;

    -- add simulated to existing rows
    UPDATE _h2h_all h
    SET res_a = COALESCE(h.res_a,0) + CASE WHEN tr.a_win=1 THEN  1 ELSE -1 END,
        pd_a  = COALESCE(h.pd_a,0)  + (tr.a_pts - tr.b_pts)
    FROM _trial_results tr
    WHERE h.a = tr.a AND h.b = tr.b;

    -- insert purely simulated pairs (no completed)
    INSERT INTO _h2h_all (a,b,res_a,pd_a)
    SELECT tr.a, tr.b,
           CASE WHEN tr.a_win=1 THEN  1 ELSE -1 END,
           (tr.a_pts - tr.b_pts)
    FROM _trial_results tr
    LEFT JOIN _h2h_all h ON h.a=tr.a AND h.b=tr.b
    WHERE h.a IS NULL;

    -- base standings & buckets
    INSERT INTO _trial_base
    SELECT s.school,
           tt.w, tt.l, tt.t, tt.pa,
           (tt.w + tt.l + tt.t) AS gp,
           CASE WHEN (tt.w + tt.l + tt.t) > 0
                THEN (tt.w + 0.5*tt.t)::NUMERIC / (tt.w + tt.l + tt.t)
                ELSE 0 END AS win_pct
    FROM _div_schools s
    JOIN _trial_totals tt USING (school);

    INSERT INTO _trial_sorted (school, w, l, t, pa, win_pct, base_bucket)
    SELECT school, w, l, t, pa, win_pct,
           DENSE_RANK() OVER (ORDER BY win_pct DESC, l ASC, school)
    FROM _trial_base;

    -- STEP 1: H2H among tied teams (W=1, T=.5, L=0) via normalized pairs
    INSERT INTO _trial_h2h_group (school, base_bucket, h2h_pts)
    SELECT
      ts.school,
      ts.base_bucket,
      COALESCE(SUM(
        CASE
          WHEN h.a = ts.school AND h.b = other.school THEN
            CASE h.res_a WHEN  1 THEN 1.0 WHEN 0 THEN 0.5 ELSE 0.0 END
          WHEN h.a = other.school AND h.b = ts.school THEN
            CASE h.res_a WHEN  1 THEN 0.0 WHEN 0 THEN 0.5 ELSE 1.0 END
          ELSE 0.0
        END
      ), 0.0) AS h2h_pts
    FROM _trial_sorted ts
    JOIN _trial_sorted other
      ON other.base_bucket = ts.base_bucket AND other.school <> ts.school
    LEFT JOIN _h2h_all h
      ON (h.a = ts.school AND h.b = other.school)
      OR (h.a = other.school AND h.b = ts.school)
    GROUP BY ts.school, ts.base_bucket;

    -- STEP 3: capped PD (±12) among tied teams using normalized pairs
    INSERT INTO _trial_h2h_pd_cap (school, base_bucket, h2h_pd_capped)
    SELECT
      ts.school,
      ts.base_bucket,
      COALESCE(SUM(
        CASE
          WHEN h.a = ts.school AND h.b = other.school THEN
            GREATEST(LEAST(h.pd_a, 12), -12)
          WHEN h.a = other.school AND h.b = ts.school THEN
            GREATEST(LEAST(-h.pd_a, 12), -12)
          ELSE 0
        END
      ), 0) AS h2h_pd_capped
    FROM _trial_sorted ts
    JOIN _trial_sorted other
      ON other.base_bucket = ts.base_bucket AND other.school <> ts.school
    LEFT JOIN _h2h_all h
      ON (h.a = ts.school AND h.b = other.school)
      OR (h.a = other.school AND h.b = ts.school)
    GROUP BY ts.school, ts.base_bucket;

    -- Build ordered list of outside opponents (for Steps 2 & 4)
    INSERT INTO _outside (tie_school, base_bucket, opp, opp_rank)
    SELECT
      a.school AS tie_school,
      a.base_bucket,
      b.school AS opp,
      DENSE_RANK() OVER (ORDER BY b.win_pct DESC, b.l ASC, b.school) AS opp_rank
    FROM _trial_sorted a
    JOIN _trial_sorted b ON b.school <> a.school
    WHERE b.base_bucket <> a.base_bucket;

    -- STEP 2: results vs those higher-ranked outside opponents (lexicographic)
    INSERT INTO _trial_step2_arr (school, base_bucket, step2_arr)
    SELECT
      o.tie_school AS school,
      ts.base_bucket,
      ARRAY_AGG(
        CASE
          WHEN h.a=o.tie_school AND h.b=o.opp THEN
            CASE h.res_a WHEN  1 THEN 2 WHEN 0 THEN 1 ELSE 0 END
          WHEN h.a=o.opp AND h.b=o.tie_school THEN
            CASE h.res_a WHEN  1 THEN 0 WHEN 0 THEN 1 ELSE 2 END
          ELSE NULL
        END
        ORDER BY o.opp_rank
      ) AS step2_arr
    FROM _outside o
    JOIN _trial_sorted ts ON ts.school = o.tie_school
    LEFT JOIN _h2h_all h
      ON (h.a=o.tie_school AND h.b=o.opp)
      OR (h.a=o.opp AND h.b=o.tie_school)
    GROUP BY o.tie_school, ts.base_bucket;

    -- STEP 4: PD vs those higher-ranked outside opponents (lexicographic, uncapped)
    INSERT INTO _trial_step4_arr (school, base_bucket, step4_arr)
    SELECT
      o.tie_school AS school,
      ts.base_bucket,
      ARRAY_AGG(
        CASE
          WHEN h.a=o.tie_school AND h.b=o.opp THEN  h.pd_a
          WHEN h.a=o.opp       AND h.b=o.tie_school THEN -h.pd_a
          ELSE NULL
        END
        ORDER BY o.opp_rank
      ) AS step4_arr
    FROM _outside o
    JOIN _trial_sorted ts ON ts.school = o.tie_school
    LEFT JOIN _h2h_all h
      ON (h.a=o.tie_school AND h.b=o.opp)
      OR (h.a=o.opp       AND h.b=o.tie_school)
    GROUP BY o.tie_school, ts.base_bucket;

    -- Gather features for ranking inside buckets
    INSERT INTO _trial_ranked
    SELECT
      ts.school, ts.w, ts.l, ts.t, ts.pa, ts.win_pct, ts.base_bucket,
      h2.h2h_pts,
      pd.h2h_pd_capped,
      s2.step2_arr,
      s4.step4_arr,
      COUNT(*) OVER (PARTITION BY ts.base_bucket) AS bucket_size
    FROM _trial_sorted ts
    LEFT JOIN _trial_h2h_group  h2 USING (school, base_bucket)
    LEFT JOIN _trial_h2h_pd_cap pd USING (school, base_bucket)
    LEFT JOIN _trial_step2_arr  s2 USING (school, base_bucket)
    LEFT JOIN _trial_step4_arr  s4 USING (school, base_bucket);

    -- Map buckets to absolute place ranges
    INSERT INTO _bucket_sizes
    SELECT base_bucket, COUNT(*) FROM _trial_ranked GROUP BY base_bucket;

    INSERT INTO _bucket_offsets
    SELECT base_bucket,
           1 + COALESCE(SUM(sz) OVER (ORDER BY base_bucket
                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0)
    FROM _bucket_sizes;

    -- Split any remaining ties evenly across their covered slots
    WITH numbered AS (
      SELECT
        tr.school, tr.base_bucket, tr.h2h_pts, tr.h2h_pd_capped,
        tr.step2_arr, tr.step4_arr, tr.pa,
        bo.start_place,
        ROW_NUMBER() OVER (
          PARTITION BY tr.base_bucket
          ORDER BY tr.h2h_pts DESC,
                   tr.step2_arr DESC NULLS LAST,
                   tr.h2h_pd_capped DESC,
                   tr.step4_arr DESC NULLS LAST,
                   tr.pa ASC,
                   tr.school
        ) AS row_in_bucket,
        COUNT(*) OVER (
          PARTITION BY tr.base_bucket, tr.h2h_pts, tr.step2_arr, tr.h2h_pd_capped, tr.step4_arr, tr.pa
        ) AS grp_sz
      FROM _trial_ranked tr
      JOIN _bucket_offsets bo USING (base_bucket)
    )
    INSERT INTO _trial_places (school, first_slot, last_slot, grp_sz)
    SELECT school,
           start_place + MIN(row_in_bucket) - 1 AS first_slot,
           start_place + MAX(row_in_bucket) - 1 AS last_slot,
           MAX(grp_sz)                           AS grp_sz
    FROM numbered
    GROUP BY school, start_place;

    -- Credit 1..4 slots
    UPDATE _odds o
    SET first_ct  = first_ct  + CASE WHEN tp.first_slot <= 1 AND 1 <= tp.last_slot THEN 1 ELSE 0 END,
        second_ct = second_ct + CASE WHEN tp.first_slot <= 2 AND 2 <= tp.last_slot THEN 1 ELSE 0 END,
        third_ct  = third_ct  + CASE WHEN tp.first_slot <= 3 AND 3 <= tp.last_slot THEN 1 ELSE 0 END,
        fourth_ct = fourth_ct + CASE WHEN tp.first_slot <= 4 AND 4 <= tp.last_slot THEN 1 ELSE 0 END
    FROM _trial_places tp
    WHERE o.school = tp.school;
  END LOOP;

  -------------------------------------------------------------------
  -- Emit odds + renormalization + clamp/flags
  -------------------------------------------------------------------
  RETURN QUERY
  WITH base AS (
    SELECT
      ds.school, ds.class, ds.region, ds.season,
      (o.first_ct ::NUMERIC) / p_trials::NUMERIC AS odds_1st,
      (o.second_ct::NUMERIC) / p_trials::NUMERIC AS odds_2nd,
      (o.third_ct ::NUMERIC) / p_trials::NUMERIC AS odds_3rd,
      (o.fourth_ct::NUMERIC) / p_trials::NUMERIC AS odds_4th,
      ((o.first_ct + o.second_ct + o.third_ct + o.fourth_ct)::NUMERIC) / p_trials::NUMERIC AS odds_playoffs
    FROM _div_schools ds
    JOIN _odds o USING (school)
  ),
  flags AS (
    SELECT
      b.*,
      CASE WHEN b.odds_playoffs >= 0.999 THEN 1.0
           WHEN b.odds_playoffs <= 0.001 THEN 0.0
           ELSE b.odds_playoffs END AS adj_odds_playoffs,
      (b.odds_playoffs >= 0.999) AS clinched_flag,
      (b.odds_playoffs <= 0.001) AS eliminated_flag
    FROM base b
  ),
  playoff_spots AS (
    SELECT class, region, season, 4 AS total_spots
    FROM flags
    GROUP BY class, region, season
  ),
  region_totals AS (
    SELECT
      f.class, f.region, f.season,
      SUM(f.adj_odds_playoffs) FILTER (WHERE f.clinched_flag)   AS sum_clinched,
      SUM(f.adj_odds_playoffs) FILTER (WHERE f.eliminated_flag) AS sum_eliminated,
      SUM(f.adj_odds_playoffs) FILTER (WHERE NOT f.clinched_flag AND NOT f.eliminated_flag) AS sum_active
    FROM flags f
    GROUP BY f.class, f.region, f.season
  ),
  renorm AS (
    SELECT
      f.school, f.class, f.region, f.season,
      f.odds_1st, f.odds_2nd, f.odds_3rd, f.odds_4th, f.odds_playoffs,
      CASE
        WHEN f.clinched_flag THEN 1.0
        WHEN f.eliminated_flag THEN 0.0
        ELSE
          f.adj_odds_playoffs *
          (
            (p.total_spots
             - COALESCE(rt.sum_clinched,0)
             - COALESCE(rt.sum_eliminated,0))
            / NULLIF(COALESCE(rt.sum_active,0), 0)
          )
      END AS final_odds_playoffs,
      f.clinched_flag AS clinched,
      f.eliminated_flag AS eliminated
    FROM flags f
    JOIN playoff_spots p USING (class, region, season)
    JOIN region_totals rt USING (class, region, season)
  )
  SELECT
    school, class, region, season,
    ROUND(odds_1st, 5)  AS odds_1st,
    ROUND(odds_2nd, 5)  AS odds_2nd,
    ROUND(odds_3rd, 5)  AS odds_3rd,
    ROUND(odds_4th, 5)  AS odds_4th,
    ROUND(odds_playoffs, 5) AS odds_playoffs,
    ROUND(
      CASE
        WHEN final_odds_playoffs >= 0.999 THEN 1.000
        WHEN final_odds_playoffs <= 0.001 THEN 0.000
        ELSE final_odds_playoffs
      END, 5
    ) AS final_odds_playoffs,
    (final_odds_playoffs >= 0.999) AS clinched,
    (final_odds_playoffs <= 0.001) AS eliminated
  FROM renorm
  ORDER BY region, final_odds_playoffs DESC, school;
END;
$$;