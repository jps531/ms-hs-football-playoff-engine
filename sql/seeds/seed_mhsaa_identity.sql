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
