-- 2026 MHSAA Football Playoff Format
-- Classes 1A-4A: 8 regions, 32 teams, 5 rounds
-- Classes 5A-7A: 4 regions, 16 teams, 4 rounds
--
-- 5A-7A: Identical bracket pairings to 2025.
-- 1A-4A: Same bracket size, but first-round cross-region pairings changed.
--   2025: Regions 1v2 and 3v4 (adjacent pairs)
--   2026: Regions 1v3 and 2v4 (diagonal pairs); same change in South half (5v7, 6v8)
--
-- This seed is also included in sql/init.sql (run automatically on DB creation).
-- Re-running this file is idempotent (ON CONFLICT DO NOTHING).

INSERT INTO playoff_formats (season, class, num_regions, seeds_per_region, num_rounds, notes)
VALUES
  (2026, 1, 8, 4, 5, '1A — 32-team bracket'),
  (2026, 2, 8, 4, 5, '2A — 32-team bracket'),
  (2026, 3, 8, 4, 5, '3A — 32-team bracket'),
  (2026, 4, 8, 4, 5, '4A — 32-team bracket'),
  (2026, 5, 4, 4, 4, '5A — 16-team bracket'),
  (2026, 6, 4, 4, 4, '6A — 16-team bracket'),
  (2026, 7, 4, 4, 4, '7A — 16-team bracket')
ON CONFLICT (season, class) DO NOTHING;


-- 5A-7A first-round slots (identical pairing to 2025 for all three classes).
-- Regions 1 & 2 = North (slots 1-4), Regions 3 & 4 = South (slots 5-8).
-- Adjacent slot pairs feed the same round-2 game: (1,2), (3,4), (5,6), (7,8).

INSERT INTO playoff_format_slots (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
SELECT f.id, s.slot, s.home_region, s.home_seed, s.away_region, s.away_seed, s.north_south
FROM playoff_formats f
CROSS JOIN (VALUES
  -- Round-2 game A (North): winner of slot 1 vs winner of slot 2
  (1, 1, 1, 2, 4, 'N'),  -- R1#1 hosts R2#4
  (2, 2, 2, 1, 3, 'N'),  -- R2#2 hosts R1#3
  -- Round-2 game B (North): winner of slot 3 vs winner of slot 4
  (3, 2, 1, 1, 4, 'N'),  -- R2#1 hosts R1#4
  (4, 1, 2, 2, 3, 'N'),  -- R1#2 hosts R2#3
  -- Round-2 game C (South): winner of slot 5 vs winner of slot 6
  (5, 3, 1, 4, 4, 'S'),  -- R3#1 hosts R4#4
  (6, 4, 2, 3, 3, 'S'),  -- R4#2 hosts R3#3
  -- Round-2 game D (South): winner of slot 7 vs winner of slot 8
  (7, 4, 1, 3, 4, 'S'),  -- R4#1 hosts R3#4
  (8, 3, 2, 4, 3, 'S')   -- R3#2 hosts R4#3
) AS s(slot, home_region, home_seed, away_region, away_seed, north_south)
WHERE f.season = 2026 AND f.class IN (5, 6, 7)
ON CONFLICT DO NOTHING;


-- 1A-4A first-round slots (identical pairing for all four classes).
-- Regions 1-4 = North (slots 1-8), Regions 5-8 = South (slots 9-16).
-- Adjacent slot pairs feed the same round-2 game: (1,2), (3,4), …, (15,16).
-- NOTE: Cross-region pairing changed from 2025. North: 1v3, 2v4 (was 1v2, 3v4).
--       South: 5v7, 6v8 (was 5v6, 7v8).

INSERT INTO playoff_format_slots (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
SELECT f.id, s.slot, s.home_region, s.home_seed, s.away_region, s.away_seed, s.north_south
FROM playoff_formats f
CROSS JOIN (VALUES
  -- Round-2 game A (North): slots 1,2
  ( 1, 1, 1, 3, 4, 'N'),  -- R1#1 hosts R3#4
  ( 2, 4, 2, 2, 3, 'N'),  -- R4#2 hosts R2#3
  -- Round-2 game B (North): slots 3,4
  ( 3, 3, 1, 1, 4, 'N'),  -- R3#1 hosts R1#4
  ( 4, 2, 2, 4, 3, 'N'),  -- R2#2 hosts R4#3
  -- Round-2 game C (North): slots 5,6
  ( 5, 2, 1, 4, 4, 'N'),  -- R2#1 hosts R4#4
  ( 6, 3, 2, 1, 3, 'N'),  -- R3#2 hosts R1#3
  -- Round-2 game D (North): slots 7,8
  ( 7, 4, 1, 2, 4, 'N'),  -- R4#1 hosts R2#4
  ( 8, 1, 2, 3, 3, 'N'),  -- R1#2 hosts R3#3
  -- Round-2 game E (South): slots 9,10
  ( 9, 5, 1, 7, 4, 'S'),  -- R5#1 hosts R7#4
  (10, 8, 2, 6, 3, 'S'),  -- R8#2 hosts R6#3
  -- Round-2 game F (South): slots 11,12
  (11, 7, 1, 5, 4, 'S'),  -- R7#1 hosts R5#4
  (12, 6, 2, 8, 3, 'S'),  -- R6#2 hosts R8#3
  -- Round-2 game G (South): slots 13,14
  (13, 6, 1, 8, 4, 'S'),  -- R6#1 hosts R8#4
  (14, 7, 2, 5, 3, 'S'),  -- R7#2 hosts R5#3
  -- Round-2 game H (South): slots 15,16
  (15, 8, 1, 6, 4, 'S'),  -- R8#1 hosts R6#4
  (16, 5, 2, 7, 3, 'S')   -- R5#2 hosts R7#3
) AS s(slot, home_region, home_seed, away_region, away_seed, north_south)
WHERE f.season = 2026 AND f.class IN (1, 2, 3, 4)
ON CONFLICT DO NOTHING;
