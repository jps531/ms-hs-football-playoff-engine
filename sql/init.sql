-- ---------------------------------------------------------------------------
-- Core school identity (static per school)
-- ---------------------------------------------------------------------------
-- One row per school — never duplicated across seasons. Stores metadata that
-- does not change year to year: location, mascot, MaxPreps identifiers, colors.
-- Class and region assignments (which can change) live in school_seasons.

CREATE TABLE IF NOT EXISTS schools (
  school          TEXT PRIMARY KEY,
  city            TEXT,
  zip             TEXT,
  latitude        REAL,
  longitude       REAL,
  mascot          TEXT,
  maxpreps_id     TEXT,
  maxpreps_url    TEXT,
  maxpreps_logo   TEXT,
  primary_color   TEXT,
  secondary_color TEXT
);


-- ---------------------------------------------------------------------------
-- Per-season class and region assignments
-- ---------------------------------------------------------------------------
-- One row per school per season. Tracks the MHSAA classification and region
-- for each school in each season, since these can change on a two-year cycle.
-- Acts as the anchor for games and region_standings foreign keys.

CREATE TABLE IF NOT EXISTS school_seasons (
  school  TEXT    NOT NULL REFERENCES schools(school),
  season  INTEGER NOT NULL,
  class   INTEGER NOT NULL,
  region  INTEGER NOT NULL,
  PRIMARY KEY (school, season)
);


-- ---------------------------------------------------------------------------
-- Physical game venues
-- ---------------------------------------------------------------------------
-- Shared lookup for stadiums and fields. Referenced by games.location_id.
-- home_team identifies which school uses this as their home field; NULL for
-- neutral sites (bowl games, playoff venues, etc.).

CREATE TABLE IF NOT EXISTS locations (
  id              SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  city            TEXT,
  home_team       TEXT,
  latitude        REAL,
  longitude       REAL,
  UNIQUE(name, city, home_team)
);


-- ---------------------------------------------------------------------------
-- Game results (school-perspective rows)
-- ---------------------------------------------------------------------------
-- One row per school per game. Each contest produces two rows — one for each
-- participating team — so points_for/against and result are always from the
-- perspective of the school column. Covers regular season and playoffs;
-- round is NULL for regular-season games.

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
  FOREIGN KEY (school, season) REFERENCES school_seasons(school, season),
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
  PRIMARY KEY (school, date)
);


-- ---------------------------------------------------------------------------
-- Region standings and playoff scenario odds
-- ---------------------------------------------------------------------------
-- One row per school per season. Recalculated after each game week by the
-- Prefect pipeline (region_scenarios_pipeline.py). Enumerates all 2^R
-- remaining-game outcomes and applies the 7-step MHSAA tiebreaker to derive
-- seeding probabilities.
--
-- Unweighted odds treat all remaining outcomes as equally likely.
-- Weighted odds (not yet implemented) will weight by per-game win probability
-- estimated from scoring margins.
--
-- Columns marked "Not yet implemented" default to 0.0 and are placeholders
-- for future bracket-odds and home-game-odds features.

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
  FOREIGN KEY (school, season) REFERENCES school_seasons(school, season)
);


-- ---------------------------------------------------------------------------
-- Pre-computed region scenario data
-- ---------------------------------------------------------------------------
-- One row per season/class/region. Updated by the Prefect pipeline after each
-- game-result batch. Stores all three artefacts needed to render scenario text
-- at request time without re-running the tiebreaker engine or boolean minimizer:
--   remaining_games    — ordered list of {a, b} game pairs; required to
--                        deserialize MarginCondition.satisfied_by at render time.
--   scenario_atoms     — minimized_scenarios dict (team → seed → condition-atom
--                        lists); source of truth for per-team "seed X if…" views.
--   complete_scenarios — output of enumerate_division_scenarios() (scenario_num,
--                        sub_label, game_winners, conditions_atom, seeding);
--                        source of truth for "Scenario N: … → 1. Team …" views.

CREATE TABLE IF NOT EXISTS region_scenarios (
  season              INT          NOT NULL,
  class               VARCHAR(10)  NOT NULL,
  region              INT          NOT NULL,
  computed_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  remaining_games     JSONB        NOT NULL,
  scenario_atoms      JSONB        NOT NULL,
  complete_scenarios  JSONB        NOT NULL,
  PRIMARY KEY (season, class, region)
);


-- ---------------------------------------------------------------------------
-- Playoff bracket format template
-- ---------------------------------------------------------------------------
-- One row per season/class combination.  The bracket tree is implicit from
-- slot ordering: adjacent slot pairs (1,2), (3,4), … produce the same
-- round-2 matchup, pairs of round-2 winners produce round-3 matchups, etc.

CREATE TABLE IF NOT EXISTS playoff_formats (
  id               SERIAL PRIMARY KEY,
  season           INTEGER NOT NULL,
  class            INTEGER NOT NULL,  -- MHSAA classification (1-7)
  num_regions      INTEGER NOT NULL,  -- 4 for 5A-7A, 8 for 1A-4A
  seeds_per_region INTEGER NOT NULL DEFAULT 4,
  num_rounds       INTEGER NOT NULL,  -- 4 for 5A-7A (16-team), 5 for 1A-4A (32-team)
  notes            TEXT,
  UNIQUE (season, class)
);

-- ---------------------------------------------------------------------------
-- Playoff bracket format slots
-- ---------------------------------------------------------------------------
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
-- Classes 1A-4A: 8 regions, 32 teams, 5 rounds.
-- Classes 5A-7A: 4 regions, 16 teams, 4 rounds.

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
-- Format: (slot, home_region, home_seed, away_region, away_seed, north_south)
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
-- Format: (slot, home_region, home_seed, away_region, away_seed, north_south)
-- Adjacent slot pairs feed the same round-2 game: (1,2), (3,4), …, (15,16).

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


-- ---------------------------------------------------------------------------
-- Table and column documentation
-- ---------------------------------------------------------------------------

-- schools

COMMENT ON TABLE schools IS
  'One row per school (ever). Stores static identity metadata sourced from '
  'MaxPreps: location, mascot, colors, and MaxPreps identifiers. '
  'Season-varying data (class, region) lives in school_seasons.';

COMMENT ON COLUMN schools.school IS
  'Canonical school name — primary key and join key throughout the schema. '
  'Normalized via name_normalize() in data_helpers.py.';
COMMENT ON COLUMN schools.maxpreps_id IS
  'MaxPreps internal school identifier, used to construct schedule URLs.';
COMMENT ON COLUMN schools.maxpreps_url IS
  'Full MaxPreps schedule page URL for scraping game results.';
COMMENT ON COLUMN schools.maxpreps_logo IS
  'URL of the school logo image hosted on MaxPreps.';
COMMENT ON COLUMN schools.primary_color IS
  'Hex color string for the school''s primary team color.';
COMMENT ON COLUMN schools.secondary_color IS
  'Hex color string for the school''s secondary team color.';


-- school_seasons

COMMENT ON TABLE school_seasons IS
  'One row per school per season. Tracks MHSAA classification and region '
  'assignments, which can change on a two-year reclassification cycle. '
  'FK anchor for games and region_standings.';

COMMENT ON COLUMN school_seasons.school IS
  'FK to schools(school). Canonical school name.';
COMMENT ON COLUMN school_seasons.season IS
  'Four-digit season year (e.g. 2025). Part of the primary key.';
COMMENT ON COLUMN school_seasons.class IS
  'MHSAA classification 1-7 (1A smallest enrollment, 7A largest).';
COMMENT ON COLUMN school_seasons.region IS
  'Region number within the classification for this season (1-indexed).';


-- locations

COMMENT ON TABLE locations IS
  'Physical venues where games are played. Referenced by games.location_id. '
  'Neutral-site games (e.g. playoff bowl games) may share a venue across many games.';

COMMENT ON COLUMN locations.name IS
  'Venue name (e.g. "Veterans Memorial Stadium").';
COMMENT ON COLUMN locations.home_team IS
  'School that uses this venue as its home field, if applicable. NULL for neutral sites.';


-- games

COMMENT ON TABLE games IS
  'One row per school per game. Each contest produces two rows — one for each team — '
  'so points_for/points_against are always from the perspective of the school column.';

COMMENT ON COLUMN games.school IS
  'The school this row describes. points_for/against and result are from this school''s perspective.';
COMMENT ON COLUMN games.date IS
  'Date the game was played. Part of the primary key with school.';
COMMENT ON COLUMN games.location IS
  'Whether this school was the home, away, or neutral-site team for this game.';
COMMENT ON COLUMN games.location_id IS
  'FK to locations. NULL if the venue is unknown or not yet geocoded.';
COMMENT ON COLUMN games.opponent IS
  'Name of the opposing school, normalized to match schools.school.';
COMMENT ON COLUMN games.points_for IS
  'Points scored by this school. NULL if the game has not yet been played.';
COMMENT ON COLUMN games.points_against IS
  'Points scored by the opponent. NULL if the game has not yet been played.';
COMMENT ON COLUMN games.result IS
  'W/L/T from this school''s perspective. NULL until the game is final.';
COMMENT ON COLUMN games.final IS
  'TRUE once the game result is confirmed. A game can have a game_status without being final '
  '(e.g. postponed games show a status before they are rescheduled).';
COMMENT ON COLUMN games.game_status IS
  'Raw status string from the data source (e.g. "Final", "Postponed"). Not normalized.';
COMMENT ON COLUMN games.source IS
  'Data source that provided this game record (e.g. "maxpreps", "mhsaa").';
COMMENT ON COLUMN games.region_game IS
  'TRUE if this game counts toward region standings. Set during ingestion based on '
  'both schools sharing the same class and region in the same season.';
COMMENT ON COLUMN games.season IS
  'Four-digit season year. Needed to join back to schools.';
COMMENT ON COLUMN games.round IS
  'Playoff round label (e.g. "first_round", "quarterfinals"). NULL for regular-season games.';
COMMENT ON COLUMN games.kickoff_time IS
  'Scheduled kickoff timestamp with timezone. Defaults to current time at insert; '
  'may not reflect the actual kickoff until the data source provides it.';
COMMENT ON COLUMN games.overtime IS
  'Number of overtime periods played. 0 for regulation finishes.';


-- region_standings

COMMENT ON TABLE region_standings IS
  'Pre-computed seeding probabilities and scenario data for each school, recalculated '
  'after every game week. Unweighted odds treat all remaining outcomes as equally likely. '
  'Weighted odds apply a naive win-probability estimate from current scoring margins.';

COMMENT ON COLUMN region_standings.school IS
  'School name; FK to schools(school, season).';
COMMENT ON COLUMN region_standings.season IS
  'Season year; FK to schools(school, season).';
COMMENT ON COLUMN region_standings.class IS
  'Denormalized from schools for query convenience.';
COMMENT ON COLUMN region_standings.region IS
  'Denormalized from schools for query convenience.';
COMMENT ON COLUMN region_standings.wins IS
  'Overall wins (all games, including non-region).';
COMMENT ON COLUMN region_standings.losses IS
  'Overall losses (all games, including non-region).';
COMMENT ON COLUMN region_standings.ties IS
  'Overall ties (all games, including non-region).';
COMMENT ON COLUMN region_standings.region_wins IS
  'Wins in region games only. Used as the primary sort key for seeding.';
COMMENT ON COLUMN region_standings.region_losses IS
  'Losses in region games only.';
COMMENT ON COLUMN region_standings.region_ties IS
  'Ties in region games only.';

COMMENT ON COLUMN region_standings.odds_1st IS
  'Fraction of equally-weighted remaining-game outcome scenarios where this school '
  'finishes 1st in the region.';
COMMENT ON COLUMN region_standings.odds_2nd IS
  'Fraction of equally-weighted scenarios where this school finishes 2nd.';
COMMENT ON COLUMN region_standings.odds_3rd IS
  'Fraction of equally-weighted scenarios where this school finishes 3rd.';
COMMENT ON COLUMN region_standings.odds_4th IS
  'Fraction of equally-weighted scenarios where this school finishes 4th.';

COMMENT ON COLUMN region_standings.odds_1st_weighted IS
  'Like odds_1st but each scenario is weighted by the product of per-game win probabilities '
  'derived from scoring margin. Not yet implemented — placeholder 0.0.';
COMMENT ON COLUMN region_standings.odds_2nd_weighted IS
  'Weighted version of odds_2nd. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_3rd_weighted IS
  'Weighted version of odds_3rd. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_4th_weighted IS
  'Weighted version of odds_4th. Not yet implemented.';

COMMENT ON COLUMN region_standings.odds_playoffs IS
  'Probability of finishing in the top 4 (making the playoffs). '
  'Equals odds_1st + odds_2nd + odds_3rd + odds_4th before tiebreaker edge cases.';
COMMENT ON COLUMN region_standings.clinched IS
  'TRUE if the school has locked in a top-4 finish regardless of remaining results.';
COMMENT ON COLUMN region_standings.eliminated IS
  'TRUE if the school cannot finish top-4 regardless of remaining results.';
COMMENT ON COLUMN region_standings.coin_flip_needed IS
  'TRUE if at least one scenario requires a coin flip to resolve a tiebreaker '
  '(all 7 MHSAA tiebreaker steps exhausted).';

COMMENT ON COLUMN region_standings.odds_second_round IS
  'Probability of advancing past the first round of the playoffs. '
  'Not yet implemented — placeholder 0.0.';
COMMENT ON COLUMN region_standings.odds_quarterfinals IS
  'Probability of reaching the quarterfinals. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_semifinals IS
  'Probability of reaching the semifinals. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_finals IS
  'Probability of reaching the state championship game. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_champion IS
  'Probability of winning the state championship. Not yet implemented.';

COMMENT ON COLUMN region_standings.odds_playoffs_weighted IS
  'Weighted version of odds_playoffs. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_second_round_weighted IS
  'Weighted version of odds_second_round. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_quarterfinals_weighted IS
  'Weighted version of odds_quarterfinals. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_semifinals_weighted IS
  'Weighted version of odds_semifinals. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_finals_weighted IS
  'Weighted version of odds_finals. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_champion_weighted IS
  'Weighted version of odds_champion. Not yet implemented.';

COMMENT ON COLUMN region_standings.odds_first_round_home IS
  'Probability of hosting the first round of the playoffs (higher seed per MHSAA rules). '
  'Not yet implemented — placeholder 0.0.';
COMMENT ON COLUMN region_standings.odds_second_round_home IS
  'Probability of hosting a second-round playoff game. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_quarterfinals_home IS
  'Probability of hosting a quarterfinal game. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_semifinals_home IS
  'Probability of hosting a semifinal game. Not yet implemented.';

COMMENT ON COLUMN region_standings.odds_first_round_home_weighted IS
  'Weighted version of odds_first_round_home. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_second_round_home_weighted IS
  'Weighted version of odds_second_round_home. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_quarterfinals_home_weighted IS
  'Weighted version of odds_quarterfinals_home. Not yet implemented.';
COMMENT ON COLUMN region_standings.odds_semifinals_home_weighted IS
  'Weighted version of odds_semifinals_home. Not yet implemented.';


-- region_scenarios

COMMENT ON TABLE region_scenarios IS
  'Pre-computed scenario data for each season/class/region, updated by the Prefect '
  'pipeline after each game-result batch. Avoids re-running the tiebreaker engine '
  'and boolean minimizer on every frontend request.';

COMMENT ON COLUMN region_scenarios.remaining_games IS
  'Ordered JSON array of {a, b} game-pair objects for the remaining region games. '
  'Required to deserialize MarginCondition.satisfied_by correctly at render time.';

COMMENT ON COLUMN region_scenarios.scenario_atoms IS
  'Serialized minimized_scenarios dict: team → seed → list of condition-atom lists. '
  'Source of truth for the per-team "seed X if…" text view.';

COMMENT ON COLUMN region_scenarios.complete_scenarios IS
  'Serialized output of enumerate_division_scenarios(): list of scenario dicts '
  'with scenario_num, sub_label, game_winners, conditions_atom, and seeding. '
  'Source of truth for the "Scenario N: … → 1. Team …" complete-seedings view.';


-- playoff_formats

COMMENT ON TABLE playoff_formats IS
  'Bracket format template for each season/class combination. '
  'Defines bracket size and round count; slot-level matchups live in playoff_format_slots.';

COMMENT ON COLUMN playoff_formats.class IS
  'MHSAA classification (1-7). 1A-4A use 8-region 32-team brackets; '
  '5A-7A use 4-region 16-team brackets.';
COMMENT ON COLUMN playoff_formats.num_regions IS
  '4 for classes 5A-7A, 8 for classes 1A-4A.';
COMMENT ON COLUMN playoff_formats.seeds_per_region IS
  'Number of playoff qualifiers per region. Always 4 under current MHSAA rules.';
COMMENT ON COLUMN playoff_formats.num_rounds IS
  '4 for 16-team brackets (5A-7A), 5 for 32-team brackets (1A-4A).';


-- playoff_format_slots

COMMENT ON TABLE playoff_format_slots IS
  'First-round matchup slots for a given playoff format. '
  'Adjacent slot pairs (1,2), (3,4), … feed the same round-2 game, '
  'forming an implicit bracket tree.';

COMMENT ON COLUMN playoff_format_slots.slot IS
  '1-based slot index within the bracket. Adjacent pairs determine round-2 opponents.';
COMMENT ON COLUMN playoff_format_slots.home_region IS
  'Region of the designated home team per MHSAA seeding rules.';
COMMENT ON COLUMN playoff_format_slots.home_seed IS
  'Seed (1-4) of the designated home team within home_region.';
COMMENT ON COLUMN playoff_format_slots.away_region IS
  'Region of the designated away team.';
COMMENT ON COLUMN playoff_format_slots.away_seed IS
  'Seed (1-4) of the designated away team within away_region.';
COMMENT ON COLUMN playoff_format_slots.north_south IS
  'Which half of the bracket this slot belongs to (N=North, S=South). '
  'Used to apply the state-championship home-site rule: South hosts in odd years.';