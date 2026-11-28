-- Championship games' kickoffs, and two corrections to the championship stadiums.
--
-- 1. championship_venues.kickoff: when each class's championship game starts, beside where it's
--    played, so it can be set before the game is on AHSFHS (as the venue can). Set on /moderate
--    (Venues) or PUT /api/v1/admin/championship-venue/{season}/{class}/kickoff.
-- 2. The 2025 and 2026 kickoffs, from MHSAA's schedules (Central time).
-- 3. Vaught-Hemingway Stadium's spot: its longitude was M.M. Roberts Stadium's.
-- 4. M.M. Roberts Stadium is Renasant Stadium now.
-- Safe to run more than once.

ALTER TABLE championship_venues ADD COLUMN IF NOT EXISTS kickoff TIMESTAMPTZ;
COMMENT ON COLUMN championship_venues.kickoff IS
  'When the championship game starts (NULL: not known). Shown under its venue on the bracket. '
  'A moderator''s kickoff_time override on the Championship Game rows wins over it.';

UPDATE championship_venues cv
SET kickoff = k.kickoff::timestamptz
FROM (VALUES
  (2025, 1, '2025-12-04 16:00 America/Chicago'),
  (2025, 5, '2025-12-04 19:30 America/Chicago'),
  (2025, 4, '2025-12-05 16:00 America/Chicago'),
  (2025, 6, '2025-12-05 19:30 America/Chicago'),
  (2025, 3, '2025-12-06 12:00 America/Chicago'),
  (2025, 2, '2025-12-06 15:30 America/Chicago'),
  (2025, 7, '2025-12-06 19:00 America/Chicago'),
  (2026, 4, '2026-12-03 16:00 America/Chicago'),
  (2026, 6, '2026-12-03 19:30 America/Chicago'),
  (2026, 2, '2026-12-04 16:00 America/Chicago'),
  (2026, 7, '2026-12-04 19:30 America/Chicago'),
  (2026, 1, '2026-12-05 12:00 America/Chicago'),
  (2026, 3, '2026-12-05 15:30 America/Chicago'),
  (2026, 5, '2026-12-05 19:00 America/Chicago')
) AS k (season, class, kickoff)
WHERE cv.season = k.season AND cv.class = k.class AND cv.kickoff IS NULL;

-- (An override of its spot would hide the correction, so any is cleared.)
UPDATE locations
SET latitude = 34.361783, longitude = -89.534438, overrides = overrides - 'latitude' - 'longitude'
WHERE name = 'Vaught-Hemingway Stadium';

UPDATE locations o
SET name = 'Renasant Stadium'
WHERE o.name = 'M.M. Roberts Stadium'
  AND NOT EXISTS (
    SELECT 1 FROM locations n
    WHERE n.name = 'Renasant Stadium' AND n.city IS NOT DISTINCT FROM o.city AND n.home_team IS NOT DISTINCT FROM o.home_team
  );
