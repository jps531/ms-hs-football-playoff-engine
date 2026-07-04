-- Salem 2025 forfeit corrections
--
-- Context: AHSFHS recorded each of these games as a forfeit loss for Salem
-- (opponents shown as W, Salem shown as L, game_status = final_forfeit).
-- MHSAA later overruled the forfeits; actual game scores stand, making Salem
-- the winner of each contest.
--
-- This script uses the override system so corrections survive pipeline re-runs
-- without losing the original scraped data. The overrides JSONB column is
-- never written by the pipeline — only by scripts like this one.
--
-- To apply:
--   psql $DATABASE_URL -f sql/corrections/salem_forfeit_2025.sql
--
-- To verify:
--   SELECT * FROM list_overrides() WHERE source LIKE 'game:Salem:%';
--   SELECT school, date, opponent, result, game_status
--     FROM games_effective
--     WHERE (school = 'Salem' OR opponent = 'Salem') AND season = 2025
--     ORDER BY date;
--
-- To roll back a single game:
--   SELECT clear_game_override('Salem', '2025-08-29', 'result');
--   SELECT clear_game_override('Salem', '2025-08-29', 'game_status');
--   SELECT clear_game_override('McLaurin', '2025-08-29', 'result');
--   SELECT clear_game_override('McLaurin', '2025-08-29', 'game_status');


-- -------------------------------------------------------------------------
-- Salem's rows: forfeit loss → win, status → final
-- -------------------------------------------------------------------------

SELECT set_game_override('Salem', '2025-08-29', 'result', 'W');
SELECT set_game_override('Salem', '2025-08-29', 'game_status', 'final');

SELECT set_game_override('Salem', '2025-09-05', 'result', 'W');
SELECT set_game_override('Salem', '2025-09-05', 'game_status', 'final');

SELECT set_game_override('Salem', '2025-09-12', 'result', 'W');
SELECT set_game_override('Salem', '2025-09-12', 'game_status', 'final');

SELECT set_game_override('Salem', '2025-10-03', 'result', 'W');
SELECT set_game_override('Salem', '2025-10-03', 'game_status', 'final');

SELECT set_game_override('Salem', '2025-10-10', 'result', 'W');
SELECT set_game_override('Salem', '2025-10-10', 'game_status', 'final');

SELECT set_game_override('Salem', '2025-10-24', 'result', 'W');
SELECT set_game_override('Salem', '2025-10-24', 'game_status', 'final');


-- -------------------------------------------------------------------------
-- Opponent rows: forfeit win → loss, status → final
-- (Discovery Christian had no mirrored row in the games table)
-- -------------------------------------------------------------------------

SELECT set_game_override('McLaurin', '2025-08-29', 'result', 'L');
SELECT set_game_override('McLaurin', '2025-08-29', 'game_status', 'final');

SELECT set_game_override('Wilkinson County', '2025-09-05', 'result', 'L');
SELECT set_game_override('Wilkinson County', '2025-09-05', 'game_status', 'final');

SELECT set_game_override('Richton', '2025-09-12', 'result', 'L');
SELECT set_game_override('Richton', '2025-09-12', 'game_status', 'final');

SELECT set_game_override('West Lincoln', '2025-10-10', 'result', 'L');
SELECT set_game_override('West Lincoln', '2025-10-10', 'game_status', 'final');

SELECT set_game_override('Mount Olive', '2025-10-24', 'result', 'L');
SELECT set_game_override('Mount Olive', '2025-10-24', 'game_status', 'final');
