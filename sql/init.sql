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
  home            TEXT,
  away            TEXT,
  home_region     INTEGER,
  home_seed       INTEGER,
  away_region     INTEGER,
  away_seed       INTEGER,
  next_game_id    BIGINT,
  FOREIGN KEY (bracket_id) REFERENCES brackets(id) ON DELETE CASCADE,
  FOREIGN KEY (home) REFERENCES schools(school),
  FOREIGN KEY (away) REFERENCES schools(school),
  UNIQUE (bracket_id, round, game_number)
);