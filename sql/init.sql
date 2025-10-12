CREATE TABLE IF NOT EXISTS schools (
  school          TEXT NOT NULL UNIQUE,
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
  PRIMARY KEY (school)
);

CREATE TABLE IF NOT EXISTS games (
  school          TEXT NOT NULL,
  date            TEXT NOT NULL,
  location        TEXT NOT NULL CHECK (location IN ('home', 'away', 'neutral')),
  opponent        TEXT NOT NULL,
  points_for      INTEGER,
  points_against  INTEGER,
  result          TEXT CHECK (result IN ('W', 'L', 'T')),
  region_game     BOOLEAN NOT NULL DEFAULT 0,
  season          INTEGER NOT NULL,
  round           TEXT,
  kickoff_time    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (school) REFERENCES schools(school) ON DELETE CASCADE,
  PRIMARY KEY (school, date)
);