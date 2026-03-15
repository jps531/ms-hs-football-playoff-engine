CREATE TABLE IF NOT EXISTS schools (
  school          TEXT NOT NULL,
  season          INTEGER NOT NULL,
  class           INTEGER NOT NULL,
  region          INTEGER NOT NULL,
  city            TEXT,
  zip             TEXT,
  latitude        REAL,
  longitude       REAL,
  mascot          TEXT,
  maxpreps_id     TEXT,
  maxpreps_url    TEXT,
  maxpreps_logo   TEXT,
  primary_color   TEXT,
  secondary_color TEXT,
  PRIMARY KEY (school, season)
);


CREATE TABLE IF NOT EXISTS locations (
  id              SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  city            TEXT,
  home_team       TEXT,
  latitude        REAL,
  longitude       REAL,
  UNIQUE(name, city, home_team)
);


CREATE TABLE IF NOT EXISTS games (
  school          TEXT NOT NULL,
  date            DATE NOT NULL,
  location        TEXT NOT NULL CHECK (location IN ('home', 'away', 'neutral')),
  location_id     INTEGER,
  opponent        TEXT NOT NULL,
  points_for      INTEGER,
  points_against  INTEGER,
  result          TEXT CHECK (result IN ('W', 'L', 'T')),
  final           BOOLEAN NOT NULL DEFAULT FALSE,
  game_status     TEXT,
  source          TEXT,
  region_game     BOOLEAN NOT NULL DEFAULT FALSE,
  season          INTEGER NOT NULL,
  round           TEXT,
  kickoff_time    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  overtime        INTEGER DEFAULT 0,
  FOREIGN KEY (school, season) REFERENCES schools(school, season),
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
  PRIMARY KEY (school, date)
);


CREATE TABLE IF NOT EXISTS region_standings (
  school          TEXT NOT NULL,
  season          INTEGER NOT NULL,
  class           INTEGER NOT NULL,
  region          INTEGER NOT NULL,
  wins            INTEGER NOT NULL DEFAULT 0,
  losses          INTEGER NOT NULL DEFAULT 0,
  ties            INTEGER NOT NULL DEFAULT 0,
  region_wins     INTEGER NOT NULL DEFAULT 0,
  region_losses   INTEGER NOT NULL DEFAULT 0,
  region_ties     INTEGER NOT NULL DEFAULT 0,
  odds_1st        REAL NOT NULL DEFAULT 0.0,
  odds_2nd        REAL NOT NULL DEFAULT 0.0,
  odds_3rd        REAL NOT NULL DEFAULT 0.0,
  odds_4th        REAL NOT NULL DEFAULT 0.0,
  odds_1st_weighted REAL NOT NULL DEFAULT 0.0,
  odds_2nd_weighted REAL NOT NULL DEFAULT 0.0,
  odds_3rd_weighted REAL NOT NULL DEFAULT 0.0,
  odds_4th_weighted REAL NOT NULL DEFAULT 0.0,
  scenarios_1st   JSONB NOT NULL DEFAULT '{}'::JSONB,
  scenarios_2nd   JSONB NOT NULL DEFAULT '{}'::JSONB,
  scenarios_3rd   JSONB NOT NULL DEFAULT '{}'::JSONB,
  scenarios_4th   JSONB NOT NULL DEFAULT '{}'::JSONB,
  odds_playoffs   REAL NOT NULL DEFAULT 0.0,
  clinched        BOOLEAN NOT NULL DEFAULT FALSE,
  eliminated      BOOLEAN NOT NULL DEFAULT FALSE,
  coin_flip_needed BOOLEAN NOT NULL DEFAULT FALSE,
  odds_second_round REAL NOT NULL DEFAULT 0.0,
  odds_quarterfinals REAL NOT NULL DEFAULT 0.0,
  odds_semifinals REAL NOT NULL DEFAULT 0.0,
  odds_finals     REAL NOT NULL DEFAULT 0.0,
  odds_champion   REAL NOT NULL DEFAULT 0.0,
  odds_playoffs_weighted REAL NOT NULL DEFAULT 0.0,
  odds_second_round_weighted REAL NOT NULL DEFAULT 0.0,
  odds_quarterfinals_weighted REAL NOT NULL DEFAULT 0.0,
  odds_semifinals_weighted REAL NOT NULL DEFAULT 0.0,
  odds_finals_weighted REAL NOT NULL DEFAULT 0.0,
  odds_champion_weighted REAL NOT NULL DEFAULT 0.0,
  odds_first_round_home REAL NOT NULL DEFAULT 0.0,
  odds_second_round_home REAL NOT NULL DEFAULT 0.0,
  odds_quarterfinals_home REAL NOT NULL DEFAULT 0.0,
  odds_semifinals_home REAL NOT NULL DEFAULT 0.0,
  odds_first_round_home_weighted REAL NOT NULL DEFAULT 0.0,
  odds_second_round_home_weighted REAL NOT NULL DEFAULT 0.0,
  odds_quarterfinals_home_weighted REAL NOT NULL DEFAULT 0.0,
  odds_semifinals_home_weighted REAL NOT NULL DEFAULT 0.0,
  UNIQUE (school, season),
  FOREIGN KEY (school, season) REFERENCES schools(school, season)
);


-- ---------------------------------------------------------------------------
-- Playoff bracket format templates
-- ---------------------------------------------------------------------------
-- One row per season/class combination.  The bracket tree is implicit from
-- slot ordering: adjacent slot pairs (1,2), (3,4), … produce the same
-- round-2 matchup, pairs of round-2 winners produce round-3 matchups, etc.

CREATE TABLE IF NOT EXISTS playoff_formats (
  id               SERIAL PRIMARY KEY,
  season           INTEGER NOT NULL,
  class            INTEGER NOT NULL,  -- MHSAA classification (1–7)
  num_regions      INTEGER NOT NULL,  -- 4 for 5A–7A, 8 for 1A–4A
  seeds_per_region INTEGER NOT NULL DEFAULT 4,
  num_rounds       INTEGER NOT NULL,  -- 4 for 5A–7A (16-team), 5 for 1A–4A (32-team)
  notes            TEXT,
  UNIQUE (season, class)
);


-- One row per first-round game slot.
-- home_region/home_seed is the designated home team (higher seed per rules).
-- north_south marks which half of the bracket the slot belongs to,
-- used to apply the state-championship home site rule (South hosts odd years).

CREATE TABLE IF NOT EXISTS playoff_format_slots (
  format_id    INTEGER NOT NULL REFERENCES playoff_formats(id) ON DELETE CASCADE,
  slot         INTEGER NOT NULL,  -- 1-based; adjacent pairs feed the same round-2 game
  home_region  INTEGER NOT NULL,
  home_seed    INTEGER NOT NULL,
  away_region  INTEGER NOT NULL,
  away_seed    INTEGER NOT NULL,
  north_south  TEXT NOT NULL CHECK (north_south IN ('N', 'S')),
  PRIMARY KEY (format_id, slot)
);


-- ---------------------------------------------------------------------------
-- 2025 playoff format seed data
-- ---------------------------------------------------------------------------

-- Insert format headers for all 7 classes.
-- Classes 1A–4A: 8 regions, 32 teams, 5 rounds.
-- Classes 5A–7A: 4 regions, 16 teams, 4 rounds.

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


-- 5A–7A first-round slots (identical pairing for all three classes).
-- Regions 1 & 2 = North (slots 1–4), Regions 3 & 4 = South (slots 5–8).

INSERT INTO playoff_format_slots (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
SELECT f.id, s.slot, s.home_region, s.home_seed, s.away_region, s.away_seed, s.north_south
FROM playoff_formats f
CROSS JOIN (VALUES
  (1, 1, 1, 2, 4, 'N'),
  (2, 2, 2, 1, 3, 'N'),
  (3, 2, 1, 1, 4, 'N'),
  (4, 1, 2, 2, 3, 'N'),
  (5, 3, 1, 4, 4, 'S'),
  (6, 4, 2, 3, 3, 'S'),
  (7, 4, 1, 3, 4, 'S'),
  (8, 3, 2, 4, 3, 'S')
) AS s(slot, home_region, home_seed, away_region, away_seed, north_south)
WHERE f.season = 2025 AND f.class IN (5, 6, 7)
ON CONFLICT DO NOTHING;


-- 1A–4A first-round slots (identical pairing for all four classes).
-- Regions 1–4 = North (slots 1–8), Regions 5–8 = South (slots 9–16).

INSERT INTO playoff_format_slots (format_id, slot, home_region, home_seed, away_region, away_seed, north_south)
SELECT f.id, s.slot, s.home_region, s.home_seed, s.away_region, s.away_seed, s.north_south
FROM playoff_formats f
CROSS JOIN (VALUES
  ( 1, 1, 1, 2, 4, 'N'),
  ( 2, 3, 2, 4, 3, 'N'),
  ( 3, 2, 1, 1, 4, 'N'),
  ( 4, 4, 2, 3, 3, 'N'),
  ( 5, 3, 1, 4, 4, 'N'),
  ( 6, 1, 2, 2, 3, 'N'),
  ( 7, 4, 1, 3, 4, 'N'),
  ( 8, 2, 2, 1, 3, 'N'),
  ( 9, 5, 1, 6, 4, 'S'),
  (10, 7, 2, 8, 3, 'S'),
  (11, 6, 1, 5, 4, 'S'),
  (12, 8, 2, 7, 3, 'S'),
  (13, 7, 1, 8, 4, 'S'),
  (14, 5, 2, 6, 3, 'S'),
  (15, 8, 1, 7, 4, 'S'),
  (16, 6, 2, 5, 3, 'S')
) AS s(slot, home_region, home_seed, away_region, away_seed, north_south)
WHERE f.season = 2025 AND f.class IN (1, 2, 3, 4)
ON CONFLICT DO NOTHING;