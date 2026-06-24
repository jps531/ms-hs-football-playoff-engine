-- Identity data (mascot, primary_color, secondary_color) for schools absent
-- from — or not matchable by — the MHSAA school directory pipeline.
--
-- Run automatically by the MHSAA School Identity Data Flow after the
-- directory scrape completes.  Safe to re-run (COALESCE(NULLIF(...))
-- leaves already-populated fields untouched).

-- West Bolivar: not present in MHSAA school directory
UPDATE schools SET
    mascot              = COALESCE(NULLIF('Eagles', ''),           mascot),
    primary_color       = COALESCE(NULLIF('Navy', ''),             primary_color),
    secondary_color     = COALESCE(NULLIF('Red, White', ''),       secondary_color),
    primary_color_hex   = COALESCE(NULLIF('#001F5B', ''),          primary_color_hex),
    secondary_color_hex = COALESCE(NULLIF('#CC0000, #FFFFFF', ''), secondary_color_hex)
WHERE school = 'West Bolivar';

-- Hazlehurst: entry exists in directory but does not match pipeline
-- (school type in Knack may not be "High School" or "Attendance Center")
UPDATE schools SET
    mascot              = COALESCE(NULLIF('Indians', ''),   mascot),
    primary_color       = COALESCE(NULLIF('Maroon', ''),    primary_color),
    secondary_color     = COALESCE(NULLIF('White', ''),     secondary_color),
    primary_color_hex   = COALESCE(NULLIF('#800000', ''),   primary_color_hex),
    secondary_color_hex = COALESCE(NULLIF('#FFFFFF', ''),   secondary_color_hex)
WHERE school = 'Hazlehurst';

-- West Point: directory lists mascot as "Greenwave"; school goes by "Green Wave"
-- (two words, no trailing S). Colors come from the directory correctly.
UPDATE schools SET
    mascot = COALESCE(NULLIF('Green Wave', ''), mascot)
WHERE school = 'West Point';

-- Leake: 2026 consolidation of Leake County (1A Region 5) and Leake Central (4A Region 5).
-- Inherits Leake Central's mascot and colors (same school identity).
-- COALESCE leaves fields untouched if Leake ever gets its own MHSAA directory entry.
UPDATE schools s SET
    mascot              = COALESCE(NULLIF(src.mascot, ''),              s.mascot),
    primary_color       = COALESCE(NULLIF(src.primary_color, ''),       s.primary_color),
    secondary_color     = COALESCE(NULLIF(src.secondary_color, ''),     s.secondary_color),
    primary_color_hex   = COALESCE(NULLIF(src.primary_color_hex, ''),   s.primary_color_hex),
    secondary_color_hex = COALESCE(NULLIF(src.secondary_color_hex, ''), s.secondary_color_hex)
FROM schools_effective src
WHERE s.school = 'Leake' AND src.school = 'Leake Central';
