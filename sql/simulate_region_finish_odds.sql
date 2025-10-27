CREATE OR REPLACE FUNCTION simulate_region_finish_odds(
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
  -- Base division setup (once)
  CREATE TEMP TABLE _div_schools AS
  SELECT s.school, s.class, s.region, s.season
  FROM schools s
  WHERE s.class = p_class AND s.region = p_region AND s.season = p_season;

  CREATE TEMP TABLE _completed AS
  SELECT
    g.school,
    g.opponent,
    (CASE g.result WHEN 'W' THEN 1 WHEN 'T' THEN 0.5 ELSE 0 END)::NUMERIC AS h2h_pts_for,
    (CASE g.result WHEN 'L' THEN 1 WHEN 'T' THEN 0.5 ELSE 0 END)::NUMERIC AS h2h_pts_against,
    (g.result = 'W')::INT AS w,
    (g.result = 'L')::INT AS l,
    (g.result = 'T')::INT AS t
  FROM games g
  JOIN _div_schools ds ON ds.school = g.school AND ds.season = g.season
  WHERE g.final = TRUE AND g.region_game = TRUE;

  CREATE TEMP TABLE _remaining_pairs AS
  WITH candidates AS (
    SELECT
      LEAST(g.school, g.opponent)  AS a,
      GREATEST(g.school, g.opponent) AS b,
      g.date
    FROM games g
    JOIN _div_schools ds1 ON ds1.school = g.school  AND ds1.season = g.season
    JOIN _div_schools ds2 ON ds2.school = g.opponent AND ds2.season = g.season
    WHERE g.final = FALSE AND g.region_game = TRUE
  )
  SELECT a, b, MIN(date) AS first_date
  FROM candidates
  GROUP BY a, b;

  CREATE TEMP TABLE _base_region_totals AS
  SELECT s.school,
         COALESCE(SUM(c.w), 0) AS w,
         COALESCE(SUM(c.l), 0) AS l,
         COALESCE(SUM(c.t), 0) AS t
  FROM _div_schools s
  LEFT JOIN _completed c ON c.school = s.school
  GROUP BY s.school;

  CREATE TEMP TABLE _odds AS
  SELECT s.school,
         0::BIGINT AS first_ct,
         0::BIGINT AS second_ct,
         0::BIGINT AS third_ct,
         0::BIGINT AS fourth_ct
  FROM _div_schools s;

  CREATE TEMP TABLE _h2h_completed AS
  SELECT a.school AS a, b.school AS b,
         COALESCE(SUM(
           CASE WHEN c.school = a.school AND c.opponent = b.school THEN c.h2h_pts_for
                WHEN c.school = b.school AND c.opponent = a.school THEN c.h2h_pts_against
                ELSE 0 END
         ), 0)::NUMERIC AS a_vs_b_pts
  FROM _div_schools a
  CROSS JOIN _div_schools b
  LEFT JOIN _completed c
         ON (c.school = a.school AND c.opponent = b.school)
         OR (c.school = b.school AND c.opponent = a.school)
  WHERE a.school <> b.school
  GROUP BY a.school, b.school;

  -- Reusable temp tables for simulation loop
  CREATE TEMP TABLE _trial_totals (school TEXT, w INT, l INT, t INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_results (school TEXT, opponent TEXT, a_win INT, b_win INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_h2h (a TEXT, b TEXT, a_vs_b_pts NUMERIC) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_base (school TEXT, w INT, l INT, t INT, gp INT, win_pct NUMERIC) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_sorted (school TEXT, w INT, l INT, t INT, win_pct NUMERIC, base_bucket INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_h2h_bucket (school TEXT, base_bucket INT, h2h_sum NUMERIC) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_ranked (school TEXT, w INT, l INT, t INT, win_pct NUMERIC,
                                   base_bucket INT, h2h_sum NUMERIC, h2h_rank INT, bucket_size INT) ON COMMIT DROP;
  CREATE TEMP TABLE _bucket_sizes (base_bucket INT, sz INT) ON COMMIT DROP;
  CREATE TEMP TABLE _bucket_offsets (base_bucket INT, start_place INT) ON COMMIT DROP;
  CREATE TEMP TABLE _trial_places (school TEXT, first_slot INT, last_slot INT, grp_sz INT) ON COMMIT DROP;

  -- Completed scores from real (final) region games (we need PF/PA for PD rules)
  CREATE TEMP TABLE _completed_scores (
    school   TEXT,
    opponent TEXT,
    pf       INT,
    pa       INT
  ) ON COMMIT DROP;

  INSERT INTO _completed_scores
  SELECT g.school, g.opponent, g.points_for, g.points_against
  FROM games g
  JOIN _div_schools ds ON ds.school = g.school AND ds.season = g.season
  WHERE g.final = TRUE AND g.region_game = TRUE;

  -- Reusable holders each iteration
  CREATE TEMP TABLE _trial_scores (       -- simulated PF/PA for remaining region games
    school   TEXT,
    opponent TEXT,
    pf       INT,
    pa       INT
  ) ON COMMIT DROP;

  CREATE TEMP TABLE _all_scores (         -- union of completed + simulated scores
    school   TEXT,
    opponent TEXT,
    pf       INT,
    pa       INT
  ) ON COMMIT DROP;

  CREATE TEMP TABLE _pair_totals (        -- per-(school,opponent) aggregates
    school   TEXT,
    opponent TEXT,
    wins     INT,
    ties     INT,
    losses   INT,
    pd       INT,         -- sum of (pf - pa)
    pts_allowed INT       -- sum of pa
  ) ON COMMIT DROP;

  -- Arrays for Step 2 and Step 4 (per tie-school vs highest-ranked opponents)
  CREATE TEMP TABLE _outside_opponents (
    tie_school TEXT,
    tie_group  INT,       -- base_bucket
    opp        TEXT,
    opp_rank   INT
  ) ON COMMIT DROP;

  CREATE TEMP TABLE _step2_arrays (
    school TEXT,
    tie_group INT,
    result_arr INT[]      -- per opp: Win=2, Tie=1, Loss=0, NULL=no game
  ) ON COMMIT DROP;

  CREATE TEMP TABLE _step4_arrays (
    school TEXT,
    tie_group INT,
    pd_arr INT[]          -- per opp: total PD (uncapped), NULL=no game
  ) ON COMMIT DROP;

  -- ================================
  -- Main Monte-Carlo loop
  -- ================================
  FOR t IN 1..p_trials LOOP
    -- Reset working tables
    TRUNCATE _trial_totals, _trial_results, _trial_h2h,
             _trial_base, _trial_sorted, _trial_h2h_bucket,
             _trial_ranked, _bucket_sizes, _bucket_offsets, _trial_places;

    -- Start with base totals
    INSERT INTO _trial_totals SELECT * FROM _base_region_totals;

    -- Simulate remaining region games
    INSERT INTO _trial_results (school, opponent, a_win, b_win)
    SELECT a, b,
           CASE WHEN random() < 0.5 THEN 1 ELSE 0 END,
           CASE WHEN random() < 0.5 THEN 0 ELSE 1 END
    FROM _remaining_pairs;

    -- Update totals for both teams
    UPDATE _trial_totals tt
    SET w = w + tr.a_win, l = l + (1 - tr.a_win)
    FROM _trial_results tr
    WHERE tt.school = tr.school;

    UPDATE _trial_totals tt
    SET w = w + tr.b_win, l = l + (1 - tr.b_win)
    FROM _trial_results tr
    WHERE tt.school = tr.opponent;

    -- Build H2H scores
    INSERT INTO _trial_h2h
    SELECT a.school AS a, b.school AS b, hc.a_vs_b_pts
    FROM _div_schools a
    CROSS JOIN _div_schools b
    JOIN _h2h_completed hc ON hc.a = a.school AND hc.b = b.school
    WHERE a.school <> b.school;

    UPDATE _trial_h2h h
    SET a_vs_b_pts = a_vs_b_pts + tr.a_win
    FROM _trial_results tr
    WHERE h.a = tr.school AND h.b = tr.opponent;

    UPDATE _trial_h2h h
    SET a_vs_b_pts = a_vs_b_pts + tr.b_win
    FROM _trial_results tr
    WHERE h.a = tr.opponent AND h.b = tr.school;

    -- Compute base standings
    INSERT INTO _trial_base
    SELECT s.school, tt.w, tt.l, tt.t,
           (tt.w + tt.l + tt.t),
           CASE WHEN (tt.w + tt.l + tt.t) > 0
                THEN (tt.w + 0.5*tt.t)::NUMERIC / (tt.w + tt.l + tt.t)
                ELSE 0 END
    FROM _div_schools s
    JOIN _trial_totals tt USING (school);

    INSERT INTO _trial_sorted (school, w, l, t, win_pct, base_bucket)
    SELECT school, w, l, t, win_pct,
          DENSE_RANK() OVER (ORDER BY win_pct DESC, l ASC) AS base_bucket
    FROM _trial_base;

    INSERT INTO _trial_h2h_bucket
    SELECT ts.school, ts.base_bucket, COALESCE(SUM(h.a_vs_b_pts), 0)
    FROM _trial_sorted ts
    JOIN _trial_sorted other
      ON other.base_bucket = ts.base_bucket AND other.school <> ts.school
    LEFT JOIN _trial_h2h h
      ON h.a = ts.school AND h.b = other.school
    GROUP BY ts.school, ts.base_bucket;

    INSERT INTO _trial_ranked
    SELECT ts.school, ts.w, ts.l, ts.t, ts.win_pct, ts.base_bucket, th.h2h_sum,
           DENSE_RANK() OVER (PARTITION BY ts.base_bucket ORDER BY th.h2h_sum DESC, ts.school),
           COUNT(*) OVER (PARTITION BY ts.base_bucket)
    FROM _trial_sorted ts
    JOIN _trial_h2h_bucket th USING (school, base_bucket);

    INSERT INTO _bucket_sizes
    SELECT base_bucket, COUNT(*) FROM _trial_ranked GROUP BY base_bucket;

    INSERT INTO _bucket_offsets
    SELECT base_bucket,
           1 + COALESCE(SUM(sz) OVER (ORDER BY base_bucket
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0)
    FROM _bucket_sizes;
    
    -- ==========================
    -- Compute placement ranges per team
    -- ==========================
    WITH numbered AS (
      SELECT
        tr.school,
        tr.base_bucket,
        tr.h2h_sum,
        bo.start_place,
        ROW_NUMBER() OVER (PARTITION BY tr.base_bucket ORDER BY tr.h2h_sum DESC, tr.school) AS row_in_bucket,
        COUNT(*) OVER (PARTITION BY tr.base_bucket, tr.h2h_sum) AS grp_sz
      FROM _trial_ranked tr
      JOIN _bucket_offsets bo USING (base_bucket)
    )
    INSERT INTO _trial_places (school, first_slot, last_slot, grp_sz)
    SELECT
      school,
      start_place + MIN(row_in_bucket) - 1 AS first_slot,
      start_place + MAX(row_in_bucket) - 1 AS last_slot,
      grp_sz
    FROM numbered
    GROUP BY school, start_place, grp_sz;

    -- Credit standings (same logic as before)
    UPDATE _odds o
    SET first_ct  = first_ct  + CASE WHEN tp.first_slot <= 1 AND 1 <= tp.last_slot THEN 1 ELSE 0 END,
        second_ct = second_ct + CASE WHEN tp.first_slot <= 2 AND 2 <= tp.last_slot THEN 1 ELSE 0 END,
        third_ct  = third_ct  + CASE WHEN tp.first_slot <= 3 AND 3 <= tp.last_slot THEN 1 ELSE 0 END,
        fourth_ct = fourth_ct + CASE WHEN tp.first_slot <= 4 AND 4 <= tp.last_slot THEN 1 ELSE 0 END
    FROM _trial_places tp
    WHERE o.school = tp.school;
  END LOOP;
  
  -----------------------------------------------------------------------
  -- [2]  return base simulation results + normalization + clinch flags
  -----------------------------------------------------------------------
  RETURN QUERY
  WITH base AS (
    SELECT
      ds.school,
      ds.class,
      ds.region,
      ds.season,
      (o.first_ct  ::NUMERIC) / p_trials::NUMERIC  AS odds_1st,
      (o.second_ct ::NUMERIC) / p_trials::NUMERIC  AS odds_2nd,
      (o.third_ct  ::NUMERIC) / p_trials::NUMERIC  AS odds_3rd,
      (o.fourth_ct ::NUMERIC) / p_trials::NUMERIC  AS odds_4th,
      ((o.first_ct + o.second_ct + o.third_ct + o.fourth_ct)::NUMERIC)
        / p_trials::NUMERIC AS odds_playoffs
    FROM _div_schools ds
    JOIN _odds o USING (school)
  ),
  flags AS (
    SELECT
      b.*,
      CASE WHEN b.odds_playoffs >= 0.99 THEN 1.0
           WHEN b.odds_playoffs <= 0.01 THEN 0.0
           ELSE b.odds_playoffs END AS adj_odds_playoffs,
      CASE WHEN b.odds_playoffs >= 0.99 THEN TRUE ELSE FALSE END AS clinched,
      CASE WHEN b.odds_playoffs <= 0.01 THEN TRUE ELSE FALSE END AS eliminated
    FROM base b
  ),
  region_sums AS (
    SELECT
      f.class,
      f.region,
      f.season,
      SUM(f.adj_odds_playoffs) AS total_odds,
      COUNT(*) FILTER (WHERE NOT f.clinched AND NOT f.eliminated) AS n_active
    FROM flags f
    GROUP BY f.class, f.region, f.season
  ),
  playoff_spots AS (
    SELECT class, region, season, 4 AS total_spots
    FROM flags
    GROUP BY class, region, season
  ),
  region_totals AS (
    SELECT
      f.class,
      f.region,
      f.season,
      SUM(f.adj_odds_playoffs) FILTER (WHERE f.clinched)   AS sum_clinched,
      SUM(f.adj_odds_playoffs) FILTER (WHERE f.eliminated) AS sum_eliminated,
      SUM(f.adj_odds_playoffs) FILTER (WHERE NOT f.clinched AND NOT f.eliminated) AS sum_active
    FROM flags f
    GROUP BY f.class, f.region, f.season
  ),
  renorm AS (
    SELECT
      f.school,
      f.class,
      f.region,
      f.season,
      f.odds_1st,
      f.odds_2nd,
      f.odds_3rd,
      f.odds_4th,
      f.odds_playoffs,
      f.clinched,
      f.eliminated,
      CASE
        WHEN f.clinched THEN 1.0
        WHEN f.eliminated THEN 0.0
        ELSE
          f.adj_odds_playoffs *
          (
            (p.total_spots - COALESCE(rt.sum_clinched,0) - COALESCE(rt.sum_eliminated,0))
            / NULLIF(COALESCE(rt.sum_active,0), 0)
          )
      END AS final_odds_playoffs
    FROM flags f
    JOIN playoff_spots p USING (class, region, season)
    JOIN region_totals rt USING (class, region, season)
  )
  SELECT
    school,
    class,
    region,
    season,
    ROUND(odds_1st, 5)  AS odds_1st,
    ROUND(odds_2nd, 5)  AS odds_2nd,
    ROUND(odds_3rd, 5)  AS odds_3rd,
    ROUND(odds_4th, 5)  AS odds_4th,
    ROUND(odds_playoffs, 5) AS odds_playoffs,
    ROUND(
      CASE
        WHEN final_odds_playoffs >= 0.99 THEN 1.000
        WHEN final_odds_playoffs <= 0.01 THEN 0.000
        ELSE final_odds_playoffs
      END, 5
    ) AS final_odds_playoffs,
    (final_odds_playoffs >= 0.99) AS clinched,
    (final_odds_playoffs <= 0.01) AS eliminated
  FROM renorm
  ORDER BY region, final_odds_playoffs DESC, school;

  -----------------------------------------------------------------------
  -- [3]  optional cleanup
  -----------------------------------------------------------------------
  DROP TABLE IF EXISTS
    _div_schools, _completed, _remaining_pairs, _base_region_totals,
    _odds, _h2h_completed, _trial_totals, _trial_results, _trial_h2h,
    _trial_base, _trial_sorted, _trial_h2h_bucket, _trial_ranked,
    _bucket_sizes, _bucket_offsets, _trial_places;
END;
$$;