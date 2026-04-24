-- 2025 MHSAA Football Playoff Format
-- Classes 1A-4A: 8 regions, 32 teams, 5 rounds
-- Classes 5A-7A: 4 regions, 16 teams, 4 rounds
--
-- This seed is also included in sql/init.sql (run automatically on DB creation).
-- Re-running this file is idempotent (ON CONFLICT DO NOTHING).

INSERT INTO playoff_formats (season, class, num_regions, seeds_per_region, num_rounds, notes)
VALUES
  (2025, 1, 8, 4, 5, '1A — 32-team bracket'),
  (2025, 2, 8, 4, 5, '2A — 32-team bracket'),
  (2025, 3, 8, 4, 5, '3A — 32-team bracket'),
  (2025, 4, 8, 4, 5, '4A — 32-team bracket'),
  (2025, 5, 4, 4, 4, '5A — 16-team bracket'),
  (2025, 6, 4, 4, 4, '6A — 16-team bracket'),
  (2025, 7, 4, 4, 4, '7A — 16-team bracket')
ON CONFLICT (season, class) DO NOTHING;


-- 5A-7A first-round slots (identical pairing for all three classes).
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
WHERE f.season = 2025 AND f.class IN (5, 6, 7)
ON CONFLICT DO NOTHING;


-- 1A-4A first-round slots (identical pairing for all four classes).
-- Regions 1-4 = North (slots 1-8), Regions 5-8 = South (slots 9-16).
-- Adjacent slot pairs feed the same round-2 game: (1,2), (3,4), ..., (15,16).

INSERT INTO playoff_format_slots (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
SELECT f.id, s.slot, s.home_region, s.home_seed, s.away_region, s.away_seed, s.north_south
FROM playoff_formats f
CROSS JOIN (VALUES
  -- Round-2 game A (North): slots 1,2
  ( 1, 1, 1, 2, 4, 'N'),  -- R1#1 hosts R2#4
  ( 2, 3, 2, 4, 3, 'N'),  -- R3#2 hosts R4#3
  -- Round-2 game B (North): slots 3,4
  ( 3, 2, 1, 1, 4, 'N'),  -- R2#1 hosts R1#4
  ( 4, 4, 2, 3, 3, 'N'),  -- R4#2 hosts R3#3
  -- Round-2 game C (North): slots 5,6
  ( 5, 3, 1, 4, 4, 'N'),  -- R3#1 hosts R4#4
  ( 6, 1, 2, 2, 3, 'N'),  -- R1#2 hosts R2#3
  -- Round-2 game D (North): slots 7,8
  ( 7, 4, 1, 3, 4, 'N'),  -- R4#1 hosts R3#4
  ( 8, 2, 2, 1, 3, 'N'),  -- R2#2 hosts R1#3
  -- Round-2 game E (South): slots 9,10
  ( 9, 5, 1, 6, 4, 'S'),  -- R5#1 hosts R6#4
  (10, 7, 2, 8, 3, 'S'),  -- R7#2 hosts R8#3
  -- Round-2 game F (South): slots 11,12
  (11, 6, 1, 5, 4, 'S'),  -- R6#1 hosts R5#4
  (12, 8, 2, 7, 3, 'S'),  -- R8#2 hosts R7#3
  -- Round-2 game G (South): slots 13,14
  (13, 7, 1, 8, 4, 'S'),  -- R7#1 hosts R8#4
  (14, 5, 2, 6, 3, 'S'),  -- R5#2 hosts R6#3
  -- Round-2 game H (South): slots 15,16
  (15, 8, 1, 7, 4, 'S'),  -- R8#1 hosts R7#4
  (16, 6, 2, 5, 3, 'S')   -- R6#2 hosts R5#3
) AS s(slot, home_region, home_seed, away_region, away_seed, north_south)
WHERE f.season = 2025 AND f.class IN (1, 2, 3, 4)
ON CONFLICT DO NOTHING;
