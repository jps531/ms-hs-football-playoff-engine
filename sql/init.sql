CREATE TABLE IF NOT EXISTS schools (
  school          TEXT NOT NULL,
  class           INTEGER NOT NULL,
  region          INTEGER NOT NULL,
  city            TEXT,
  homepage        TEXT,
  primary_color   TEXT,
  secondary_color TEXT,
  PRIMARY KEY (school, class, region)
);