-- Past looks edited on /moderate: a look added there (source 'moderator'), which the looks pipeline
-- leaves alone, and overrides of a look's seasons and approximate flag. color_variants follows the
-- effective hex colors (the API works them out again when a hex override changes).
ALTER TABLE school_looks ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'file';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_looks_source_check') THEN
    ALTER TABLE school_looks ADD CONSTRAINT school_looks_source_check CHECK (source IN ('file', 'moderator'));
  END IF;
END $$;

CREATE OR REPLACE VIEW school_looks_effective AS
SELECT
  id, school,
  -- (A season override may be blank: as far back as known, or still in use.)
  CASE WHEN overrides ? 'first_season' THEN NULLIF(overrides->>'first_season', '')::int ELSE first_season END AS first_season,
  CASE WHEN overrides ? 'last_season'  THEN NULLIF(overrides->>'last_season',  '')::int ELSE last_season  END AS last_season,
  COALESCE(overrides->>'mascot',              mascot)              AS mascot,
  COALESCE(overrides->>'primary_color',       primary_color)       AS primary_color,
  COALESCE(overrides->>'secondary_color',     secondary_color)     AS secondary_color,
  COALESCE(overrides->>'primary_color_hex',   primary_color_hex)   AS primary_color_hex,
  COALESCE(overrides->>'secondary_color_hex', secondary_color_hex) AS secondary_color_hex,
  color_variants,
  COALESCE((overrides->>'approximate')::boolean, approximate) AS approximate,
  note, overrides, source
FROM school_looks;

COMMENT ON COLUMN school_looks.source IS
  'file: from backend/data/school_looks.csv (the pipeline keeps it the file''s); moderator: added on /moderate (the pipeline leaves it).';
