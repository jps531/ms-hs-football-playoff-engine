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
  -- Completed region games (final=TRUE). We keep both result & scores.
  -------------------------------------------------------------------
  CREATE TEMP TABLE _completed ON COMMIT DROP AS
  SELECT
    g.school,
    g.opponent,
    g.result,
    g.points_for,
    g.points_against
  FROM games g
  JOIN _div_schools ds ON ds.school = g.school AND ds.season = g.season
  WHERE g.final = TRUE AND g.region_game = TRUE;

  -- Precompute completed W/L/T and points-allowed per team
  CREATE TEMP TABLE _base_region_totals ON COMMIT DROP AS
  SELECT s.school,
         COUNT(*) FILTER (WHERE c.result='W') AS w,
         COUNT(*) FILTER (WHERE c.result='L') AS l,
         COUNT(*) FILTER (WHERE c.result='T') AS t,
         COALESCE(SUM(c.points_against),0)    AS pa
  FROM _div_schools s
  LEFT JOIN _completed c ON c.school = s.school
  GROUP BY s.school;

  -- Completed head-to-head table with *both* normalized result points and differentials
  -- h2h_pts: W=1, T=0.5, L=0 (for Step 1 combined record math)
  -- h2h_pd : (points_for - points_against) signed (used for Step 3 cap later)
  CREATE TEMP TABLE _h2h_completed ON COMMIT DROP AS
  SELECT a.school AS a, b.school AS b,
         COALESCE(SUM(
           CASE WHEN c.school=a.school AND c.opponent=b.school THEN
                    CASE c.result WHEN 'W' THEN 1 WHEN 'T' THEN 0.5 ELSE 0 END
                WHEN c.school=b.school AND c.opponent=a.school THEN
                    CASE c.result WHEN 'L' THEN 1 WHEN 'T' THEN 0.5 ELSE 0 END
                ELSE 0 END
         ), 0)::NUMERIC AS a_vs_b_pts,
         COALESCE(SUM(
           CASE WHEN c.school=a.school AND c.opponent=b.school THEN (c.points_for - c.points_against)
                WHEN c.school=b.school AND c.opponent=a.school THEN (c.points_against - c.points_for)
                ELSE 0 END
         ), 0)::INT AS a_vs_b_pd
  FROM _div_schools a
  CROSS JOIN _div_schools b
  LEFT JOIN _completed c
         ON (c.school=a.school AND c.opponent=b.school)
         OR (c.school=b.school AND c.opponent=a.school)
  WHERE a.school <> b.school
  GROUP BY a.school, b.school;

  -------------------------------------------------------------------
  -- Remaining region games to simulate (unique pairs a<b)
  -------------------------------------------------------------------
  CREATE TEMP TABLE _remaining_pairs ON COMMIT DROP AS
  WITH candidates AS (
    SELECT
      LEAST(g.school, g.opponent)  AS a,
      GREATEST(g.school, g.opponent) AS b,
      g.date
    FROM games g
    JOIN _div_schools ds1 ON ds1.school = g.school   AND ds1.season = g.season
    JOIN _div_schools ds2 ON ds2.school = g.opponent AND ds2.season = g.season
    WHERE g.final = FALSE AND g.region_game = TRUE
  )
  SELECT a, b, MIN(date) AS first_date
  FROM candidates
  GROUP BY a, b;

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
  CREATE TEMP TABLE _trial_results  (a TEXT, b TEXT, a_win INT, margin INT, a_pts INT, b_pts INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_h2h      (a TEXT, b TEXT, a_vs_b_pts NUMERIC, a_vs_b_pd INT) ON COMMIT DROP;

  -- base + rankings
  CREATE TEMP TABLE _trial_base     (school TEXT, w INT, l INT, t INT, pa INT, gp INT, win_pct NUMERIC) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_sorted   (school TEXT, w INT, l INT, t INT, pa INT, win_pct NUMERIC, base_bucket INT) ON COMMIT DROP;

  -- tie-group metrics
  CREATE TEMP TABLE _trial_h2h_group    (school TEXT, base_bucket INT, h2h_pts NUMERIC) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_h2h_pd_cap   (school TEXT, base_bucket INT, h2h_pd_capped INT) ON COMMIT DROP;

  -- Step 2 / Step 4 arrays (lexicographic)
  CREATE TEMP TABLE _trial_step2_arr (school TEXT, base_bucket INT, step2_arr INT[]) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_step4_arr (school TEXT, base_bucket INT, step4_arr INT[]) ON COMMIT DROP;

  -- final rank materialization per trial
  CREATE TEMP TABLE _trial_ranked   (
    school TEXT, w INT, l INT, t INT, pa INT, win_pct NUMERIC, base_bucket INT,
    h2h_pts NUMERIC, h2h_pd_capped INT, step2_arr INT[], step4_arr INT[],
    bucket_size INT
  ) ON COMMIT DROP;

  CREATE TEMP TABLE _bucket_sizes  (base_bucket INT, sz INT) ON COMMIT DROP;
  CREATE TEMP TABLE _bucket_offsets(base_bucket INT, start_place INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_places  (school TEXT, first_slot INT, last_slot INT, grp_sz INT) ON COMMIT DROP;
  CREATE TEMP TABLE _outside (tie_school TEXT, base_bucket INT, opp TEXT, opp_rank INT) ON COMMIT DROP;


  -------------------------------------------------------------------
  -- Monte Carlo
  -------------------------------------------------------------------
  FOR t IN 1..p_trials LOOP
    TRUNCATE _trial_totals, _trial_results, _trial_h2h,
             _trial_base, _trial_sorted,
             _trial_h2h_group, _trial_h2h_pd_cap,
             _trial_step2_arr, _trial_step4_arr,
             _trial_ranked, _bucket_sizes, _bucket_offsets, _trial_places, _outside;

    -- Seed totals with completed counts/points-allowed
    INSERT INTO _trial_totals
    SELECT school, w, l, t, pa FROM _base_region_totals;

    -----------------------------------------------------------------
    -- Simulate remaining games with scores
    --  - winner: fair coin
    --  - margin: {3,7,10,14} with probs {0.4,0.3,0.2,0.1}
    --  - loser points L: 10..30 uniform; winner points = L + margin
    -----------------------------------------------------------------
    INSERT INTO _trial_results (a, b, a_win, margin, a_pts, b_pts)
    SELECT
      rp.a, rp.b,
      CASE WHEN random() < 0.5 THEN 1 ELSE 0 END AS a_win,
      CASE
        WHEN r1 < 0.4 THEN 3
        WHEN r1 < 0.7 THEN 7
        WHEN r1 < 0.9 THEN 10
        ELSE 14
      END AS margin,
      NULL::INT, NULL::INT
    FROM _remaining_pairs rp
    CROSS JOIN LATERAL (SELECT random() AS r1) p;

    -- set points using a second random draw
    UPDATE _trial_results tr
    SET a_pts = CASE WHEN a_win=1 THEN (lpts.l + tr.margin) ELSE lpts.l END,
        b_pts = CASE WHEN a_win=1 THEN lpts.l ELSE (lpts.l + tr.margin) END
    FROM (
      SELECT a, b, 10 + FLOOR(random()*21)::INT AS l
      FROM _remaining_pairs
    ) AS lpts
    WHERE tr.a = lpts.a AND tr.b = lpts.b;

    -- Update W/L and points allowed
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

    -----------------------------------------------------------------
    -- Build H2H map for this trial (completed + simulated)
    -----------------------------------------------------------------
    INSERT INTO _trial_h2h (a, b, a_vs_b_pts, a_vs_b_pd)
    SELECT hc.a, hc.b, hc.a_vs_b_pts, hc.a_vs_b_pd
    FROM _h2h_completed hc;

    -- add simulated A wins
    UPDATE _trial_h2h h
    SET a_vs_b_pts = a_vs_b_pts + 1,
        a_vs_b_pd  = a_vs_b_pd  + (tr.a_pts - tr.b_pts)
    FROM _trial_results tr
    WHERE h.a = tr.a AND h.b = tr.b AND tr.a_win=1;

    -- add simulated B wins
    UPDATE _trial_h2h h
    SET a_vs_b_pts = a_vs_b_pts + 1,
        a_vs_b_pd  = a_vs_b_pd  + (tr.b_pts - tr.a_pts)
    FROM _trial_results tr
    WHERE h.a = tr.b AND h.b = tr.a AND tr.a_win=0;

    -----------------------------------------------------------------
    -- Base standings & buckets (by region win%)
    -----------------------------------------------------------------
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

    INSERT INTO _outside (tie_school, base_bucket, opp, opp_rank)
    SELECT
      a.school               AS tie_school,
      a.base_bucket,
      b.school               AS opp,
      DENSE_RANK() OVER (ORDER BY b.win_pct DESC, b.l ASC, b.school) AS opp_rank
    FROM _trial_sorted a
    JOIN _trial_sorted b ON b.school <> a.school
    WHERE b.base_bucket <> a.base_bucket;

    -----------------------------------------------------------------
    -- Step 1: H2H among tie group (combined record)
    -----------------------------------------------------------------
    INSERT INTO _trial_h2h_group (school, base_bucket, h2h_pts)
    SELECT ts.school, ts.base_bucket,
           COALESCE(SUM(h.a_vs_b_pts), 0)
    FROM _trial_sorted ts
    JOIN _trial_sorted other
      ON other.base_bucket = ts.base_bucket AND other.school <> ts.school
    LEFT JOIN _trial_h2h h
      ON h.a = ts.school AND h.b = other.school
    GROUP BY ts.school, ts.base_bucket;

    -- ---------------------------------------------
    -- Step 2: results vs highest-ranked outside opponents (lexicographic)
    -- W=2, T=1, L=0, NULL if no game
    -- ---------------------------------------------
    INSERT INTO _trial_step2_arr (school, base_bucket, step2_arr)
    SELECT
      o.tie_school AS school,
      ts.base_bucket,
      ARRAY_AGG(
        CASE
          WHEN c.school=o.tie_school AND c.opponent=o.opp THEN
            CASE c.result WHEN 'W' THEN 2 WHEN 'T' THEN 1 WHEN 'L' THEN 0 END
          WHEN c.school=o.opp AND c.opponent=o.tie_school THEN
            CASE c.result WHEN 'W' THEN 0 WHEN 'T' THEN 1 WHEN 'L' THEN 2 END
          WHEN tr.a=o.tie_school AND tr.b=o.opp THEN
            CASE WHEN tr.a_win=1 THEN 2 ELSE 0 END
          WHEN tr.a=o.opp AND tr.b=o.tie_school THEN
            CASE WHEN tr.a_win=1 THEN 0 ELSE 2 END
          ELSE NULL
        END
        ORDER BY o.opp_rank
      ) AS step2_arr
    FROM _outside o
    JOIN _trial_sorted ts ON ts.school = o.tie_school
    LEFT JOIN _completed c
      ON (c.school=o.tie_school AND c.opponent=o.opp)
      OR (c.school=o.opp       AND c.opponent=o.tie_school)
    LEFT JOIN _trial_results tr
      ON (tr.a=o.tie_school AND tr.b=o.opp)
      OR (tr.a=o.opp       AND tr.b=o.tie_school)
    GROUP BY o.tie_school, ts.base_bucket;

    -----------------------------------------------------------------
    -- Step 3: capped PD (±12) among tied teams only
    -----------------------------------------------------------------
    INSERT INTO _trial_h2h_pd_cap (school, base_bucket, h2h_pd_capped)
    SELECT ts.school, ts.base_bucket,
           COALESCE(SUM(GREATEST(LEAST(h.a_vs_b_pd, 12), -12)), 0)
    FROM _trial_sorted ts
    JOIN _trial_sorted other
      ON other.base_bucket = ts.base_bucket AND other.school <> ts.school
    LEFT JOIN _trial_h2h h
      ON h.a = ts.school AND h.b = other.school
    GROUP BY ts.school, ts.base_bucket;

    -- ---------------------------------------------
    -- Step 4: point differential vs those same outside opponents (lexicographic, uncapped)
    -- ---------------------------------------------
    INSERT INTO _trial_step4_arr (school, base_bucket, step4_arr)
    SELECT
      o.tie_school AS school,
      ts.base_bucket,
      ARRAY_AGG(
        CASE
          WHEN c.school=o.tie_school AND c.opponent=o.opp THEN (c.points_for - c.points_against)
          WHEN c.school=o.opp       AND c.opponent=o.tie_school THEN (c.points_against - c.points_for)
          WHEN tr.a=o.tie_school AND tr.b=o.opp THEN (tr.a_pts - tr.b_pts)
          WHEN tr.a=o.opp       AND tr.b=o.tie_school THEN (tr.b_pts - tr.a_pts)
          ELSE NULL
        END
        ORDER BY o.opp_rank
      ) AS step4_arr
    FROM _outside o
    JOIN _trial_sorted ts ON ts.school = o.tie_school
    LEFT JOIN _completed c
      ON (c.school=o.tie_school AND c.opponent=o.opp)
      OR (c.school=o.opp       AND c.opponent=o.tie_school)
    LEFT JOIN _trial_results tr
      ON (tr.a=o.tie_school AND tr.b=o.opp)
      OR (tr.a=o.opp       AND tr.b=o.tie_school)
    GROUP BY o.tie_school, ts.base_bucket;

    -----------------------------------------------------------------
    -- Gather everything for ranking
    -----------------------------------------------------------------
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

    -----------------------------------------------------------------
    -- Map buckets to absolute place ranges and split ties evenly
    -----------------------------------------------------------------
    INSERT INTO _bucket_sizes
    SELECT base_bucket, COUNT(*) FROM _trial_ranked GROUP BY base_bucket;

    INSERT INTO _bucket_offsets
    SELECT base_bucket,
           1 + COALESCE(SUM(sz) OVER (ORDER BY base_bucket
                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0)
    FROM _bucket_sizes;

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
        COUNT(*) OVER (PARTITION BY tr.base_bucket, tr.h2h_pts, tr.step2_arr, tr.h2h_pd_capped, tr.step4_arr, tr.pa) AS grp_sz
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

    -- Credit playoff/places (1..4)
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