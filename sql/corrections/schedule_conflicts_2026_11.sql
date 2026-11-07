-- Schedule corrections found in November 2026: two wrong opponents, one game not played
--
-- Each game below is listed on one school's AHSFHS page and not on its opponent's.
--
--   Amanda Elzy, Aug 28, 2026: Amanda Elzy's page lists a 0-42 loss to Leflore
--     County. Charleston's page lists a 42-0 win over Amanda Elzy that night, and
--     Leflore County's lists a game against Shaw. Amanda Elzy played Charleston.
--   Bay Springs, Sep 12, 2025: Bay Springs' page lists a 20-22 loss to Jim Hill.
--     Forest Hill's page lists a 22-20 win over Bay Springs that night, and Jim
--     Hill's lists a game against Lanier. Bay Springs played Forest Hill.
--   West Tallahatchie, Sep 25, 2026: West Tallahatchie's page lists a 1-0 win over
--     Ashland. The game wasn't played and wasn't forfeited (the site's owner);
--     Ashland played Tupelo Christian that night. Marked canceled.
--
-- Needs sql/migrations/2026_11_opponent_corrections.sql first (set_game_opponent,
-- and games_effective showing a canceled game without a score). Safe to run more
-- than once.
--
-- To apply:
--   docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d mshsfootball < sql/corrections/schedule_conflicts_2026_11.sql
--
-- To verify (each game: both schools' rows, one game_id, the same score):
--   SELECT game_id, school, date, opponent, result, points_for, points_against, final, game_status
--     FROM games_effective
--     WHERE (school, date) IN (('Amanda Elzy', '2026-08-28'), ('Charleston', '2026-08-28'),
--                              ('Bay Springs', '2025-09-12'), ('Forest Hill', '2025-09-12'),
--                              ('West Tallahatchie', '2026-09-25'))
--     ORDER BY date, game_id, school;
--
-- To roll back:
--   SELECT clear_game_opponent('Amanda Elzy', '2026-08-28');
--   SELECT clear_game_opponent('Bay Springs', '2025-09-12');
--   SELECT clear_game_override('West Tallahatchie', '2026-09-25', 'game_status');

SELECT set_game_opponent('Amanda Elzy', '2026-08-28', 'Charleston');
SELECT set_game_opponent('Bay Springs', '2025-09-12', 'Forest Hill');
SELECT set_game_override('West Tallahatchie', '2026-09-25', 'game_status', 'canceled');

-- Work the 2026 changes into the numbers (the ratings, so the odds): the
-- recompute-after-corrections deployment picks this up within 10 minutes and
-- recomputes the season's snapshots from Aug 28.
INSERT INTO recompute_requests (season, from_date, requested_at)
VALUES (2026, '2026-08-28', NOW())
ON CONFLICT (season) DO UPDATE
SET from_date = LEAST(recompute_requests.from_date, EXCLUDED.from_date), requested_at = NOW();

-- 2025 is over, so its numbers only reach the site through 2026's starting
-- ratings, by a little. To recompute 2025 too (a whole-season backfill, so a
-- long run), uncomment:
-- INSERT INTO recompute_requests (season, from_date, requested_at)
-- VALUES (2025, '2025-09-12', NOW())
-- ON CONFLICT (season) DO UPDATE
-- SET from_date = LEAST(recompute_requests.from_date, EXCLUDED.from_date), requested_at = NOW();
