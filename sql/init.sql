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
  date            TEXT NOT NULL,
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
  scenarios_1st   JSONB NOT NULL DEFAULT '{}'::JSONB,
  scenarios_2nd   JSONB NOT NULL DEFAULT '{}'::JSONB,
  scenarios_3rd   JSONB NOT NULL DEFAULT '{}'::JSONB,
  scenarios_4th   JSONB NOT NULL DEFAULT '{}'::JSONB,
  odds_playoffs   REAL NOT NULL DEFAULT 0.0,
  clinched        BOOLEAN NOT NULL DEFAULT FALSE,
  eliminated      BOOLEAN NOT NULL DEFAULT FALSE,
  coin_flip_needed BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (school, season),
  FOREIGN KEY (school, season) REFERENCES schools(school, season)
);


CREATE TABLE IF NOT EXISTS brackets (
  id              BIGSERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  season          INTEGER NOT NULL,
  class           INTEGER NOT NULL,
  source          TEXT
);


CREATE TABLE IF NOT EXISTS bracket_teams (
  bracket_id      BIGINT NOT NULL,
  school          TEXT NOT NULL,
  season          INTEGER NOT NULL,
  seed            INTEGER NOT NULL,
  region          INTEGER NOT NULL,
  FOREIGN KEY (bracket_id) REFERENCES brackets(id) ON DELETE CASCADE,
  FOREIGN KEY (school, season) REFERENCES schools(school, season),
  PRIMARY KEY (bracket_id, school)
);


CREATE TABLE IF NOT EXISTS bracket_games (
  id              BIGSERIAL PRIMARY KEY,
  bracket_id      BIGINT NOT NULL,
  round           TEXT NOT NULL,
  game_number     INTEGER NOT NULL,
  season          INTEGER NOT NULL,
  home            TEXT,
  away            TEXT,
  home_region     INTEGER,
  home_seed       INTEGER,
  away_region     INTEGER,
  away_seed       INTEGER,
  next_game_id    BIGINT,
  FOREIGN KEY (bracket_id) REFERENCES brackets(id) ON DELETE CASCADE,
  FOREIGN KEY (home, season) REFERENCES schools(school, season),
  FOREIGN KEY (away, season) REFERENCES schools(school, season),
  UNIQUE (bracket_id, round, game_number)
);