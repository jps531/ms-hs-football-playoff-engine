-- A school's past looks (mascot and colors by season): the same as sql/init.sql.
-- ---------------------------------------------------------------------------
-- A school's past looks: mascot and colors by season
-- ---------------------------------------------------------------------------
-- schools holds a school's look now; a row here holds the look it had for a span of seasons before
-- (first_season NULL: as far back as known; last_season NULL: still). /teams?season= gives a season's
-- look from here when a row covers it. Loaded from backend/data/school_looks.csv (school_looks_pipeline);
-- overrides (moderators') win over the file, as on schools. A season with a look here and no logo in
-- team_logos covering it has no logo (never a logo the school didn't use then).

CREATE TABLE IF NOT EXISTS school_looks (
  id                  SERIAL  PRIMARY KEY,
  school              TEXT    NOT NULL REFERENCES schools(school),
  first_season        INTEGER,
  last_season         INTEGER,
  mascot              TEXT,
  primary_color       TEXT,
  secondary_color     TEXT,
  primary_color_hex   TEXT,
  secondary_color_hex TEXT,
  color_variants      JSONB,
  approximate         BOOLEAN NOT NULL DEFAULT FALSE,
  note                TEXT,
  overrides           JSONB   NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT school_looks_span CHECK (first_season IS NULL OR last_season IS NULL OR first_season <= last_season)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_school_looks_school_first
  ON school_looks (school, COALESCE(first_season, 0));

CREATE OR REPLACE VIEW school_looks_effective AS
SELECT
  id, school, first_season, last_season,
  COALESCE(overrides->>'mascot',              mascot)              AS mascot,
  COALESCE(overrides->>'primary_color',       primary_color)       AS primary_color,
  COALESCE(overrides->>'secondary_color',     secondary_color)     AS secondary_color,
  COALESCE(overrides->>'primary_color_hex',   primary_color_hex)   AS primary_color_hex,
  COALESCE(overrides->>'secondary_color_hex', secondary_color_hex) AS secondary_color_hex,
  color_variants, approximate, note, overrides
FROM school_looks;

COMMENT ON TABLE school_looks IS
  'A school''s past looks (mascot and colors) for spans of seasons; schools holds its look now. '
  'Loaded from backend/data/school_looks.csv; overrides win, as on schools.';
COMMENT ON COLUMN school_looks.first_season IS 'The look''s first season; NULL: as far back as known.';
COMMENT ON COLUMN school_looks.last_season IS 'The look''s last season; NULL: still in use.';
COMMENT ON COLUMN school_looks.approximate IS 'TRUE when the hex colors are standard shades for the named colors, not the school''s exact ones.';
