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
  secondary_color TEXT,
  overrides       JSONB NOT NULL DEFAULT '{}'::jsonb
);


-- ---------------------------------------------------------------------------
-- Helmet design history (static per design, spans multiple seasons)
-- ---------------------------------------------------------------------------
-- One row per distinct helmet design worn by a school. Not season-keyed —
-- year_first_worn / year_last_worn span multiple seasons. years_worn is a
-- JSONB array of {start, end} range objects to represent non-contiguous spans.

CREATE TABLE IF NOT EXISTS helmet_designs (
  id              SERIAL PRIMARY KEY,
  school          TEXT    NOT NULL REFERENCES schools(school),
  year_first_worn INTEGER NOT NULL,
  year_last_worn  INTEGER,                   -- NULL = currently in use
  years_worn      JSONB,                     -- [{start: 2001, end: 2005}, {start: 2007, end: 2007}]
  image_left      TEXT,                      -- URL to 2D mockup facing left
  image_right     TEXT,                      -- URL to 2D mockup facing right
  photo           TEXT,                      -- URL to real-life photo
  color           TEXT,
  finish          TEXT,                      -- e.g. 'matte', 'gloss', 'chrome', 'satin'
  facemask_color  TEXT,
  logo            TEXT,                      -- description, e.g. 'outlined script W'
  stripe          TEXT,                      -- description, e.g. 'single center stripe'
  tags            TEXT[],                    -- queryable metadata tags
  notes           TEXT                       -- free-text catch-all
);

CREATE INDEX IF NOT EXISTS idx_helmet_designs_school
  ON helmet_designs (school);


-- ---------------------------------------------------------------------------
-- Per-season class and region assignments
-- ---------------------------------------------------------------------------
-- One row per school per season. Tracks the MHSAA classification and region
-- for each school in each season, since these can change on a two-year cycle.
-- Acts as the anchor for games and region_standings foreign keys.

CREATE TABLE IF NOT EXISTS school_seasons (
  school    TEXT    NOT NULL REFERENCES schools(school),
  season    INTEGER NOT NULL,
  class     INTEGER NOT NULL,
  region    INTEGER NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
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
  overrides       JSONB NOT NULL DEFAULT '{}'::jsonb,
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
  game_status     TEXT CHECK (game_status IS NULL OR game_status IN (
                    'final', 'final_forfeit',
                    'end_1q', 'halftime', 'end_3q', 'end_4q',
                    'in_progress', 'end_ot',
                    'postponed', 'canceled', 'suspended', 'not_started'
                  )),
  game_quarter    SMALLINT,
  game_clock      TEXT,
  source          TEXT,
  region_game     BOOLEAN NOT NULL DEFAULT FALSE,
  season          INTEGER NOT NULL,
  round           TEXT,
  kickoff_time    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  overtime        INTEGER DEFAULT 0,
  overrides       JSONB NOT NULL DEFAULT '{}'::jsonb,
  helmet_design_id INTEGER REFERENCES helmet_designs(id) ON DELETE SET NULL,
  FOREIGN KEY (school, season) REFERENCES school_seasons(school, season),
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
  PRIMARY KEY (school, date)
);


CREATE INDEX IF NOT EXISTS idx_games_helmet_design
  ON games (helmet_design_id)
  WHERE helmet_design_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Effective views — merge overrides JSONB over raw column values.
-- All reads (API and pipeline) should use these views.
-- All writes go to the base tables only; the overrides column is never written
-- by any pipeline task.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW schools_effective AS
SELECT
  school, city, zip, maxpreps_id, maxpreps_url, maxpreps_logo
  COALESCE((overrides->>'latitude')::float,    latitude)        AS latitude,
  COALESCE((overrides->>'longitude')::float,   longitude)       AS longitude,
  COALESCE(overrides->>'mascot',               mascot)          AS mascot,
  COALESCE(overrides->>'primary_color',        primary_color)   AS primary_color,
  COALESCE(overrides->>'secondary_color',      secondary_color) AS secondary_color,
  COALESCE(overrides->>'display_name',         school)          AS display_name,
  COALESCE(overrides->>'display_logo',         maxpreps_logo)   AS display_logo,
  overrides
FROM schools;

CREATE OR REPLACE VIEW locations_effective AS
SELECT
  id, name, city,
  COALESCE(overrides->>'home_team',           home_team)  AS home_team,
  COALESCE((overrides->>'latitude')::float,   latitude)   AS latitude,
  COALESCE((overrides->>'longitude')::float,  longitude)  AS longitude,
  overrides
FROM locations;

CREATE OR REPLACE VIEW games_effective AS
SELECT
  school, date, season, opponent, result, final, overtime,
  game_status, game_quarter, game_clock, source,
  helmet_design_id,
  COALESCE(overrides->>'location',                location)       AS location,
  COALESCE((overrides->>'location_id')::int,      location_id)    AS location_id,
  COALESCE((overrides->>'points_for')::int,       points_for)     AS points_for,
  COALESCE((overrides->>'points_against')::int,   points_against) AS points_against,
  COALESCE((overrides->>'region_game')::boolean,  region_game)    AS region_game,
  COALESCE(overrides->>'round',                   round)          AS round,
  COALESCE((overrides->>'kickoff_time')::timestamptz, kickoff_time) AS kickoff_time,
  overrides
FROM games;


-- ---------------------------------------------------------------------------
-- Region standings and playoff scenario odds
-- ---------------------------------------------------------------------------
-- One row per school per season per pipeline run date (as_of_date). The
-- Prefect pipeline appends a new snapshot after each game week rather than
-- overwriting, so the API can answer "what were the odds as of date X?" by
-- finding the most recent row with as_of_date <= X.
--
-- Unweighted odds treat all remaining outcomes as equally likely.
-- Weighted odds apply per-game win probability estimated from scoring margins.
--
-- Columns marked "Not yet implemented" default to 0.0 and are placeholders
-- for future bracket-odds and home-game-odds features.

CREATE TABLE IF NOT EXISTS region_standings (
  school          TEXT NOT NULL,
  season          INTEGER NOT NULL,
  as_of_date      DATE NOT NULL DEFAULT CURRENT_DATE,
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
  UNIQUE (school, season, as_of_date),
  FOREIGN KEY (school, season) REFERENCES school_seasons(school, season)
);

CREATE INDEX IF NOT EXISTS idx_region_standings_lookup
  ON region_standings (school, season, as_of_date DESC);

-- ---------------------------------------------------------------------------
-- Materialized Elo ratings and RPI per school per season
-- ---------------------------------------------------------------------------
-- One row per school per season. Overwritten on every pipeline run so the
-- frontend always reads ratings that are consistent with the seeding odds
-- stored in region_standings (both written in the same pipeline execution).
-- computed_at lets the frontend show a "ratings as of [time]" freshness indicator,
-- which is especially important during live-score-update runs.

CREATE TABLE IF NOT EXISTS team_ratings (
  school        TEXT    NOT NULL REFERENCES schools(school),
  season        INTEGER NOT NULL,
  as_of_date    DATE    NOT NULL DEFAULT CURRENT_DATE,
  elo           REAL    NOT NULL,
  rpi           REAL,                   -- NULL if team has < 3 completed games
  games_played  INTEGER NOT NULL,
  computed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (school, season, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_team_ratings_lookup
  ON team_ratings (school, season, as_of_date DESC);


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
  as_of_date          DATE         NOT NULL DEFAULT CURRENT_DATE,
  computed_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  remaining_games     JSONB        NOT NULL,
  scenario_atoms      JSONB        NOT NULL,
  complete_scenarios  JSONB        NOT NULL,
  PRIMARY KEY (season, class, region, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_region_scenarios_lookup
  ON region_scenarios (season, class, region, as_of_date DESC);


-- ---------------------------------------------------------------------------
-- Region computation state
-- ---------------------------------------------------------------------------
-- One row per season/class/region. Tracks the margin-sensitivity mode and
-- pipeline status for each region's scenario computation.
--
-- Two-phase computation tiers:
--   R ≤ 4  — always margin-sensitive; computed synchronously; status = 'not_needed'
--   R = 5–6 — win/loss-only first (margin_sensitive=FALSE, status='pending'),
--              then upgraded in the background (status='running' → 'complete',
--              margin_sensitive flips to TRUE once the upgrade lands)
--   R ≥ 7  — win/loss-only permanently; status = 'skipped'
--
-- The frontend uses margin_sensitive + margin_compute_status to decide whether
-- to show a "refining scenarios…" indicator.

CREATE TABLE IF NOT EXISTS region_computation_state (
  season                  INTEGER NOT NULL,
  class                   INTEGER NOT NULL,
  region                  INTEGER NOT NULL,
  as_of_date              DATE    NOT NULL DEFAULT CURRENT_DATE,
  r_remaining             INTEGER NOT NULL,
  margin_sensitive        BOOLEAN NOT NULL DEFAULT FALSE,
  margin_compute_status   TEXT    NOT NULL DEFAULT 'not_needed'
                          CHECK (margin_compute_status IN (
                            'not_needed',  -- R ≤ 4: always synchronous, no background job
                            'pending',     -- R 5-6: win/loss data stored, background job queued
                            'running',     -- R 5-6: background margin computation in progress
                            'complete',    -- R 5-6: margin-sensitive data has been stored
                            'skipped'      -- R ≥ 7: margin sensitivity permanently disabled
                          )),
  computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  margin_computed_at      TIMESTAMPTZ,        -- NULL until margin-sensitive computation completes
  PRIMARY KEY (season, class, region, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_region_computation_state_lookup
  ON region_computation_state (season, class, region, as_of_date DESC);


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
COMMENT ON COLUMN schools.city IS
  'City where the school is located.';
COMMENT ON COLUMN schools.zip IS
  'ZIP code for the school''s address.';
COMMENT ON COLUMN schools.latitude IS
  'Latitude of the school in decimal degrees. Used for drive-time / distance calculations.';
COMMENT ON COLUMN schools.longitude IS
  'Longitude of the school in decimal degrees.';
COMMENT ON COLUMN schools.mascot IS
  'Team mascot name (e.g. "Bulldogs", "Tigers").';
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
COMMENT ON COLUMN schools.overrides IS
  'User-managed JSONB patch applied on read via the schools_effective view. Any key here shadows '
  'the corresponding raw column (latitude, longitude, mascot, maxpreps_logo, primary_color, secondary_color). '
  'Known override keys: display_name (frontend-only label; falls back to school when absent), '
  'display_logo (frontend-only logo URL; falls back to maxpreps_logo when absent), '
  'latitude, longitude, mascot, primary_color, secondary_color. '
  'Written only through set_school_override() / clear_school_override(); never by the pipeline.';


-- helmet_designs

COMMENT ON TABLE helmet_designs IS
  'One row per distinct helmet design variant worn by a school. Not season-keyed — '
  'a single design may span multiple seasons with gaps. year_first_worn / year_last_worn '
  'are the outer bounds; years_worn encodes non-contiguous spans in detail. '
  'id is the sole unique identifier; no composite uniqueness constraint is enforced '
  'because teams can wear multiple distinct helmets within the same year.';

COMMENT ON COLUMN helmet_designs.school IS
  'FK to schools(school). Canonical school name.';
COMMENT ON COLUMN helmet_designs.year_first_worn IS
  'First season this design was worn. The lower bound of the wear span.';
COMMENT ON COLUMN helmet_designs.year_last_worn IS
  'Last season this design was worn. NULL means the design is still in current use.';
COMMENT ON COLUMN helmet_designs.years_worn IS
  'JSONB array of {start, end} range objects encoding non-contiguous wear spans '
  '(e.g. [{"start": 2001, "end": 2005}, {"start": 2007, "end": 2007}]). '
  'NULL if the school wore the design continuously from year_first_worn to year_last_worn.';
COMMENT ON COLUMN helmet_designs.image_left IS
  'URL to a 2D mockup image of the helmet facing left.';
COMMENT ON COLUMN helmet_designs.image_right IS
  'URL to a 2D mockup image of the helmet facing right.';
COMMENT ON COLUMN helmet_designs.photo IS
  'URL to a real-life photograph of the helmet.';
COMMENT ON COLUMN helmet_designs.color IS
  'Primary helmet shell color (e.g. "matte black", "metallic gold").';
COMMENT ON COLUMN helmet_designs.finish IS
  'Surface finish of the helmet shell (e.g. "matte", "gloss", "chrome", "satin").';
COMMENT ON COLUMN helmet_designs.facemask_color IS
  'Color of the facemask (e.g. "white", "black", "gray").';
COMMENT ON COLUMN helmet_designs.logo IS
  'Free-text description of the helmet logo (e.g. "outlined script W", "block G with shadow").';
COMMENT ON COLUMN helmet_designs.stripe IS
  'Free-text description of any stripe pattern (e.g. "single center stripe", "dual side stripes").';
COMMENT ON COLUMN helmet_designs.tags IS
  'Array of metadata tags for filtering and discovery '
  '(e.g. ARRAY[''throwback'', ''alternate'', ''special edition'']). '
  'Queryable via: %s = ANY(tags).';
COMMENT ON COLUMN helmet_designs.notes IS
  'Free-text catch-all for details that do not fit a structured column '
  '(e.g. "worn only for rivalry games", "limited-edition homecoming helmet").';


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
COMMENT ON COLUMN school_seasons.is_active IS
  'FALSE for schools that withdrew, merged, or were otherwise removed mid-season. '
  'Inactive schools are excluded from standings and scenario calculations.';


-- locations

COMMENT ON TABLE locations IS
  'Physical venues where games are played. Referenced by games.location_id. '
  'Neutral-site games (e.g. playoff bowl games) may share a venue across many games.';

COMMENT ON COLUMN locations.name IS
  'Venue name (e.g. "Veterans Memorial Stadium").';
COMMENT ON COLUMN locations.city IS
  'City where the venue is located.';
COMMENT ON COLUMN locations.home_team IS
  'School that uses this venue as its home field, if applicable. NULL for neutral sites.';
COMMENT ON COLUMN locations.latitude IS
  'Latitude of the venue in decimal degrees. Used for drive-time / distance calculations.';
COMMENT ON COLUMN locations.longitude IS
  'Longitude of the venue in decimal degrees.';
COMMENT ON COLUMN locations.overrides IS
  'User-managed JSONB patch applied on read via the locations_v view. Any key here shadows '
  'the corresponding raw column (home_team, latitude, longitude). '
  'Written only through set_location_override() / clear_location_override(); never by the pipeline.';


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
  'Normalized game status. One of: final, final_forfeit, end_1q, halftime, end_3q, end_4q, '
  'in_progress, end_ot, postponed, canceled, suspended, not_started. '
  'NULL for legacy rows inserted before normalization was enforced.';
COMMENT ON COLUMN games.game_quarter IS
  'Current quarter (1–4 for regulation; 5 = OT1, 6 = OT2, etc.). '
  'Only populated when game_status is in_progress or end_ot. NULL otherwise.';
COMMENT ON COLUMN games.game_clock IS
  'Clock remaining within the current regulation quarter in "MM:SS" format. '
  'Always NULL for OT (MSHAA overtime is untimed alternating possessions). '
  'Only populated when game_status is in_progress during regulation.';
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
COMMENT ON COLUMN games.overrides IS
  'User-managed JSONB patch applied on read via the games_v view. Any key here shadows '
  'the corresponding raw column (home_team, latitude, longitude, location, location_id, '
  'points_for, points_against, region_game, round, kickoff_time). '
  'Written only through set_game_override() / clear_game_override(); never by the pipeline.';
COMMENT ON COLUMN games.helmet_design_id IS
  'FK to helmet_designs(id). The helmet design this school wore in this game. '
  'NULL until manually designated. Not written by any pipeline — updated manually only.';


-- region_standings

COMMENT ON TABLE region_standings IS
  'Pre-computed seeding probabilities and scenario data for each school, recalculated '
  'after every game week. Unweighted odds treat all remaining outcomes as equally likely. '
  'Weighted odds apply a naive win-probability estimate from current scoring margins.';

COMMENT ON COLUMN region_standings.school IS
  'School name; FK to schools(school, season).';
COMMENT ON COLUMN region_standings.season IS
  'Season year; FK to schools(school, season).';
COMMENT ON COLUMN region_standings.as_of_date IS
  'Pipeline run date this snapshot was written. Rows are appended, never overwritten; query with as_of_date <= X to get historical odds.';
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


-- team_ratings

COMMENT ON TABLE team_ratings IS
  'Materialized Elo ratings and RPI for each school, recomputed on every pipeline '
  'run and written alongside region_standings to guarantee consistency. '
  'One row per school per season; overwritten (not appended) each run.';

COMMENT ON COLUMN team_ratings.school IS
  'FK to schools(school). Canonical school name.';
COMMENT ON COLUMN team_ratings.season IS
  'Four-digit season year. Part of the primary key.';
COMMENT ON COLUMN team_ratings.as_of_date IS
  'Pipeline run date these ratings were computed. Part of the primary key; '
  'query with as_of_date DESC to get the most recent ratings for a school.';
COMMENT ON COLUMN team_ratings.elo IS
  'Elo rating after processing all completed games for the season in chronological '
  'order. Starting rating blends the prior-season final Elo with the classification '
  'prior (1A=1000, 7A=1300, step 50) using EloConfig.carryover_factor (default 0.50). '
  'First-season teams (no prior row) start at the classification prior. '
  'Updates use a margin-of-victory multiplier (FiveThirtyEight-style).';
COMMENT ON COLUMN team_ratings.rpi IS
  'Rating Percentage Index: 0.25*WP + 0.50*OWP + 0.25*OOWP. '
  'Stored for display context only; does not affect win probability calculations. '
  'NULL when the team has fewer than 3 completed games.';
COMMENT ON COLUMN team_ratings.games_played IS
  'Number of completed, scored games processed when computing these ratings.';
COMMENT ON COLUMN team_ratings.computed_at IS
  'Timestamp of the pipeline run that produced these ratings. '
  'Should match the computed_at of the corresponding region_standings rows.';


-- region_scenarios

COMMENT ON TABLE region_scenarios IS
  'Pre-computed scenario data for each season/class/region, updated by the Prefect '
  'pipeline after each game-result batch. Avoids re-running the tiebreaker engine '
  'and boolean minimizer on every frontend request.';

COMMENT ON COLUMN region_scenarios.season IS
  'Four-digit season year. Part of the primary key.';
COMMENT ON COLUMN region_scenarios.class IS
  'MHSAA classification (1-7). Part of the primary key.';
COMMENT ON COLUMN region_scenarios.region IS
  'Region number within the classification. Part of the primary key.';
COMMENT ON COLUMN region_scenarios.as_of_date IS
  'Pipeline run date this scenario snapshot was written. Used with as_of_date DESC index to retrieve the latest or a historical snapshot for a given region.';
COMMENT ON COLUMN region_scenarios.computed_at IS
  'Timestamp when the pipeline wrote this snapshot. More precise than as_of_date for auditing run order.';

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


-- region_computation_state

COMMENT ON TABLE region_computation_state IS
  'Tracks the margin-sensitivity mode and background-job status for each region. '
  'One row per season/class/region. Updated by the Prefect pipeline after each '
  'game-result batch. Used by the frontend to decide whether to show a '
  '"refining scenarios…" indicator while the background upgrade runs.';


COMMENT ON COLUMN region_computation_state.season IS
  'Four-digit season year. Part of the primary key.';
COMMENT ON COLUMN region_computation_state.class IS
  'MHSAA classification (1-7). Part of the primary key.';
COMMENT ON COLUMN region_computation_state.region IS
  'Region number within the classification. Part of the primary key.';
COMMENT ON COLUMN region_computation_state.as_of_date IS
  'Pipeline run date this computation-state row was written. Part of the primary key so each pipeline run produces its own snapshot alongside the matching region_scenarios row.';
COMMENT ON COLUMN region_computation_state.r_remaining IS
  'Number of unplayed region games at the time of last computation. '
  'Determines which tier applies: ≤4 synchronous, 5-6 two-phase, ≥7 win/loss-only.';
COMMENT ON COLUMN region_computation_state.margin_sensitive IS
  'TRUE if the currently stored scenario_atoms and odds reflect full margin-sensitive '
  'computation. FALSE when only win/loss enumeration has been run (initial phase for R=5-6, '
  'or permanently for R≥7).';
COMMENT ON COLUMN region_computation_state.margin_compute_status IS
  'Pipeline lifecycle state. See table comment for the full state machine. '
  'not_needed: R≤4, always synchronous. '
  'pending/running/complete: R=5-6 two-phase upgrade lifecycle. '
  'skipped: R≥7, win/loss-only permanently.';
COMMENT ON COLUMN region_computation_state.computed_at IS
  'Timestamp of the most recent computation (win/loss or margin-sensitive).';
COMMENT ON COLUMN region_computation_state.margin_computed_at IS
  'Timestamp when the margin-sensitive upgrade completed. NULL until complete.';

-- playoff_formats

COMMENT ON TABLE playoff_formats IS
  'Bracket format template for each season/class combination. '
  'Defines bracket size and round count; slot-level matchups live in playoff_format_slots.';

COMMENT ON COLUMN playoff_formats.season IS
  'Four-digit season year this format applies to. Part of the unique key with class.';
COMMENT ON COLUMN playoff_formats.class IS
  'MHSAA classification (1-7). 1A-4A use 8-region 32-team brackets; '
  '5A-7A use 4-region 16-team brackets.';
COMMENT ON COLUMN playoff_formats.num_regions IS
  '4 for classes 5A-7A, 8 for classes 1A-4A.';
COMMENT ON COLUMN playoff_formats.seeds_per_region IS
  'Number of playoff qualifiers per region. Always 4 under current MHSAA rules.';
COMMENT ON COLUMN playoff_formats.num_rounds IS
  '4 for 16-team brackets (5A-7A), 5 for 32-team brackets (1A-4A).';
COMMENT ON COLUMN playoff_formats.notes IS
  'Optional human-readable label for this format (e.g. "7A — 16-team bracket"). '
  'Informational only; not used by the engine.';


-- playoff_format_slots

COMMENT ON TABLE playoff_format_slots IS
  'First-round matchup slots for a given playoff format. '
  'Adjacent slot pairs (1,2), (3,4), … feed the same round-2 game, '
  'forming an implicit bracket tree.';

COMMENT ON COLUMN playoff_format_slots.format_id IS
  'FK to playoff_formats(id). Cascades on delete so removing a format removes all its slots.';
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