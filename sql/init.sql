CREATE TABLE IF NOT EXISTS schools (
  school TEXT NOT NULL,
  class  INTEGER NOT NULL,
  region INTEGER NOT NULL,
  city   TEXT,
  PRIMARY KEY (school, class, region)
);