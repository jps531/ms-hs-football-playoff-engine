CREATE TABLE IF NOT EXISTS schools (
  school          TEXT NOT NULL,
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
  PRIMARY KEY (school, class, region)
);