-- Independents: a school that played a season without a region (backend/helpers/region_files.py).
-- Its school_seasons row has no region, and no class when it had none that season. A region needs
-- a class. Every query that picks a class or region (standings, region games, brackets) leaves
-- independents out by itself, since NULL equals nothing.
ALTER TABLE school_seasons ALTER COLUMN class DROP NOT NULL;
ALTER TABLE school_seasons ALTER COLUMN region DROP NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_seasons_region_needs_class') THEN
    ALTER TABLE school_seasons
      ADD CONSTRAINT school_seasons_region_needs_class CHECK (region IS NULL OR class IS NOT NULL);
  END IF;
END $$;

COMMENT ON COLUMN school_seasons.class IS
  'MHSAA classification 1-7 (1A smallest enrollment, 7A largest). NULL for an independent '
  'that had no class that season.';
COMMENT ON COLUMN school_seasons.region IS
  'Region number within the classification for this season (1-indexed). NULL for an '
  'independent: a school that played that season without a region.';
