-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once.
--
--   docker compose exec -T db psql -U postgres -d mshsfootball < sql/migrations/2026_10_schema_comments.sql
--
-- ---------------------------------------------------------------------------
-- Corrected table and column comments
-- ---------------------------------------------------------------------------
-- Re-issues the comments init.sql corrected: region_standings, team_ratings,
-- region_scenarios and region_computation_state are written once per pipeline
-- run date (a same-day rerun replaces that day's rows), the scenario tiers are
-- R ≤ 5 / 6-15 / > 15, and there is no background margin upgrade. Comments
-- only; no data or schema changes.

COMMENT ON TABLE region_standings IS
  'Pre-computed seeding probabilities for each school, one snapshot per school per day '
  '(a same-day rerun replaces it; region_standings_archive keeps every version). '
  'Unweighted (Toss-up) odds treat every remaining winner as equally likely. '
  'Weighted (Projected) odds use each game''s win probability from Elo ratings.';

COMMENT ON COLUMN region_standings.as_of_date IS
  'Pipeline run date this snapshot was written. A same-day rerun replaces the row; query with as_of_date <= X to get historical odds.';

COMMENT ON TABLE team_ratings IS
  'Elo ratings and RPI for each school, one row per school per season per date. '
  'Each pipeline run writes its run date''s ratings (with RPI) and one row per earlier '
  'game date (RPI NULL); a rerun on the same day replaces that day''s rows.';

COMMENT ON COLUMN team_ratings.elo IS
  'Elo rating after processing all completed games for the season in chronological '
  'order. Starting rating blends the prior-season final Elo with the classification '
  'prior (1A=1000, 7A=1300, step 50) using EloConfig.carryover_factor (default 0.50). '
  'First-season teams (no prior row) start at the classification prior. '
  'Updates use a margin-of-victory multiplier loosely modelled on FiveThirtyEight''s.';

COMMENT ON COLUMN team_ratings.rpi IS
  'Rating Percentage Index: 0.25*WP + 0.50*OWP + 0.25*OOWP. '
  'Stored for display context only; does not affect win probability calculations. '
  'NULL when the team has fewer than 3 completed games, and on the per-game-date rows.';

COMMENT ON COLUMN team_ratings.computed_at IS
  'When the pipeline wrote this row.';

COMMENT ON TABLE region_scenarios IS
  'Pre-computed scenario data for each season/class/region, one row per pipeline run '
  'date (a same-day rerun replaces it). Avoids re-running the tiebreaker engine '
  'and boolean minimizer on every frontend request.';

COMMENT ON COLUMN region_scenarios.key_insights IS
  'Serialized list of KeyInsight objects extracted from scenario_atoms. '
  'Each insight is a simple, unconditionally-true conditional statement about a team''s '
  'seeding or playoff status (e.g. "Taylorsville clinches 1st seed: Taylorsville beats Stringer"). '
  'Each is checked against every winner, margin and score meeting its conditions. '
  'Shown as cards when 6 to 10 region games remain, and used in the region headline. '
  'Empty array when no actionable insights exist (always, past 10 games left).';

COMMENT ON TABLE region_computation_state IS
  'Whether each region''s stored scenarios account for margins, one row per '
  'season/class/region per pipeline run date, written with the matching region_scenarios '
  'row. The frontend reads only computed_at, for the "updated" time.';

COMMENT ON COLUMN region_computation_state.r_remaining IS
  'Number of unplayed region games at the time of last computation. '
  'Determines which tier applies: ≤5 margin-sensitive scenarios, 6-15 win/loss-only, '
  '>15 no scenarios (Monte Carlo odds).';

COMMENT ON COLUMN region_computation_state.margin_sensitive IS
  'TRUE when the stored scenarios account for margins (R≤5). FALSE when they are '
  'win/loss-only (R≥6): every game is then scored at a 7-point margin, in the '
  'scenarios and the odds.';

COMMENT ON COLUMN region_computation_state.margin_compute_status IS
  'not_needed: R≤5, scenarios account for margins. skipped: R≥6, win/loss-only. '
  'pending/running/complete are allowed but never written.';

COMMENT ON COLUMN region_computation_state.computed_at IS
  'When the pipeline wrote this row.';

COMMENT ON COLUMN region_computation_state.margin_computed_at IS
  'Never written; always NULL.';
