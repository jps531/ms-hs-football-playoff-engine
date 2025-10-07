CREATE TABLE IF NOT EXISTS football_regions (
  school TEXT NOT NULL,
  class  INTEGER NOT NULL,
  region INTEGER NOT NULL,
  PRIMARY KEY (school, class, region)
);