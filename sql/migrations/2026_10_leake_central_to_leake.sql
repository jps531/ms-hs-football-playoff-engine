-- Apply to an existing database (init.sql only runs when the database is first
-- created). Safe to run more than once: a second run finds nothing to rename.
--
--   docker compose --env-file .env.local --profile local-db exec -T db \
--     psql -v ON_ERROR_STOP=1 -U postgres -d mshsfootball < sql/migrations/2026_10_leake_central_to_leake.sql
--
-- Leake County (1A-5) and Leake Central (4A-5) consolidated into Leake (5A-2)
-- for 2026. AHSFHS and the MHSAA region page still say "Leake Central", so the
-- 2026 season was stored under that name. The pipelines now file it under
-- "Leake" from 2026 on (SCHOOL_RENAMES in backend/helpers/data_helpers.py);
-- this moves the 2026 rows already stored. 2025 and earlier are untouched, so
-- Leake Central and Leake County keep their own history.
--
-- Renamed in place, not deleted and recomputed, so every stored snapshot keeps
-- working, including the morning snapshots on dates without games that a
-- backfill doesn't rewrite. region_standings_archive isn't touched: it records
-- what was published, under the name it was published with, and renaming a
-- row isn't a new publication, so its write trigger is off for the rename.
--
-- After running it, run the daily update (or region-scenarios-data-pipeline
-- then share-assets) for 2026 so today's numbers carry Leake Central's 2025
-- Elo rating forward (see docs/operations/SEASON_SETUP.md).

BEGIN;

-- The school row (and its identity, as seed_mhsaa_identity.sql and
-- seed_private_school_locations.sql give it) if it isn't there yet.
INSERT INTO schools (school) VALUES ('Leake') ON CONFLICT (school) DO NOTHING;
UPDATE schools s SET
    mascot              = COALESCE(NULLIF(s.mascot, ''),              src.mascot),
    primary_color       = COALESCE(NULLIF(s.primary_color, ''),       src.primary_color),
    secondary_color     = COALESCE(NULLIF(s.secondary_color, ''),     src.secondary_color),
    primary_color_hex   = COALESCE(NULLIF(s.primary_color_hex, ''),   src.primary_color_hex),
    secondary_color_hex = COALESCE(NULLIF(s.secondary_color_hex, ''), src.secondary_color_hex),
    city                = COALESCE(s.city,      src.city),
    zip                 = COALESCE(s.zip,       src.zip),
    latitude            = COALESCE(s.latitude,  src.latitude),
    longitude           = COALESCE(s.longitude, src.longitude)
FROM schools_effective src
WHERE s.school = 'Leake' AND src.school = 'Leake Central';
-- color_variants (the clamped colors the generic helmet is drawn in) is
-- computed from the two hex colors alone (backend/helpers/color_variants.py),
-- so when Leake's colors are Leake Central's, so are its variants.
UPDATE schools s SET color_variants = src.color_variants
FROM schools src, schools_effective le, schools_effective lce
WHERE s.school = 'Leake' AND src.school = 'Leake Central'
  AND le.school = 'Leake' AND lce.school = 'Leake Central'
  AND src.color_variants IS NOT NULL
  AND le.primary_color_hex   IS NOT DISTINCT FROM lce.primary_color_hex
  AND le.secondary_color_hex IS NOT DISTINCT FROM lce.secondary_color_hex
  AND s.color_variants IS DISTINCT FROM src.color_variants;

-- Refuse to merge two sets of rows rather than guess which one is right.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM games a JOIN games b ON a.date = b.date
        WHERE a.school = 'Leake' AND b.school = 'Leake Central' AND a.season >= 2026 AND b.season >= 2026
    ) THEN
        RAISE EXCEPTION 'Leake and Leake Central both have 2026 games on the same date; resolve those by hand first';
    END IF;
    IF EXISTS (
        SELECT 1 FROM team_ratings a JOIN team_ratings b USING (season, as_of_date)
        WHERE a.school = 'Leake' AND b.school = 'Leake Central' AND a.season >= 2026
    ) THEN
        RAISE EXCEPTION 'Leake and Leake Central both have 2026 ratings for the same date; resolve those by hand first';
    END IF;
    IF EXISTS (
        SELECT 1 FROM region_standings a JOIN region_standings b USING (season, as_of_date)
        WHERE a.school = 'Leake' AND b.school = 'Leake Central' AND a.season >= 2026
    ) THEN
        RAISE EXCEPTION 'Leake and Leake Central both have 2026 standings for the same date; resolve those by hand first';
    END IF;
    IF EXISTS (SELECT 1 FROM user_attended_games WHERE school = 'Leake Central' AND date >= DATE '2026-01-01') THEN
        RAISE EXCEPTION 'user_attended_games references Leake Central 2026 games; move those by hand first';
    END IF;
END $$;

-- The season: Leake takes Leake Central's 2026 class and region (an existing
-- Leake row, e.g. from docs/operations/SEASON_SETUP.md, is brought in line and made active).
INSERT INTO school_seasons (school, season, class, region, is_active)
SELECT 'Leake', season, class, region, TRUE
FROM school_seasons WHERE school = 'Leake Central' AND season >= 2026
ON CONFLICT (school, season) DO UPDATE SET class = EXCLUDED.class, region = EXCLUDED.region, is_active = TRUE;

-- Its games, and every other school's games against it. Score corrections
-- (games.overrides) move with their rows.
UPDATE games SET school = 'Leake' WHERE school = 'Leake Central' AND season >= 2026;
UPDATE games SET opponent = 'Leake' WHERE opponent = 'Leake Central' AND season >= 2026;

-- Ratings and standings.
UPDATE team_ratings SET school = 'Leake' WHERE school = 'Leake Central' AND season >= 2026;
ALTER TABLE region_standings DISABLE TRIGGER region_standings_archive_write;
UPDATE region_standings SET school = 'Leake' WHERE school = 'Leake Central' AND season >= 2026;
ALTER TABLE region_standings ENABLE TRIGGER region_standings_archive_write;

-- The name inside stored scenarios, insights and seed pairs. "Leake Central"
-- appears nowhere else in these (no other school's name contains it).
UPDATE region_scenarios SET
    remaining_games    = replace(remaining_games::text,    'Leake Central', 'Leake')::jsonb,
    scenario_atoms     = replace(scenario_atoms::text,     'Leake Central', 'Leake')::jsonb,
    complete_scenarios = replace(complete_scenarios::text, 'Leake Central', 'Leake')::jsonb,
    key_insights       = replace(key_insights::text,       'Leake Central', 'Leake')::jsonb
WHERE season >= 2026
  AND (remaining_games::text LIKE '%Leake Central%' OR scenario_atoms::text LIKE '%Leake Central%'
       OR complete_scenarios::text LIKE '%Leake Central%' OR key_insights::text LIKE '%Leake Central%');
UPDATE region_seed_pairs SET
    pairs          = replace(pairs::text,          'Leake Central', 'Leake')::jsonb,
    pairs_weighted = replace(pairs_weighted::text, 'Leake Central', 'Leake')::jsonb
WHERE season >= 2026 AND (pairs::text LIKE '%Leake Central%' OR pairs_weighted::text LIKE '%Leake Central%');

-- Nothing refers to Leake Central's 2026 season now.
DELETE FROM school_seasons WHERE school = 'Leake Central' AND season >= 2026;

COMMIT;
